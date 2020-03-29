import asyncio
import inspect
import json
import logging
import os.path
import socket
import time
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Awaitable, Tuple, Callable, List, Optional, Union

import aiohttp
import pkg_resources
from aiohttp import web

from .compat import asyncio_create_task
from .resources import Bundle, Resource


logger = logging.getLogger(__name__)

Message = Dict[str, Any]


class AIODesktopError(Exception): ...


class Client:
    """
    Abstraction to communicate with json.
    """

    def __init__(self, json_impl):
        self.ws = web.WebSocketResponse()
        self._json_impl = json_impl

    async def prepare(self, request: web.Request):
        await self.ws.prepare(request)

    async def send(self, data: Message):
        await self.ws.send_str(self._json_impl.dumps(data))

    async def close(self):
        await self.ws.close()

    def __aiter__(self) -> 'Client':
        return self

    async def __anext__(self) -> Message:
        msg = await self.ws.__anext__()
        assert isinstance(msg, aiohttp.WSMessage)
        assert msg.type == aiohttp.WSMsgType.TEXT
        return self._json_impl.loads(msg.data)


def _get_free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('localhost', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


JS_INLINE = '''\
<script>
    (function() {
        var s = document.createElement('script');
        s.type = 'text/javascript';
        s.src = '%(script_url)s';
        window.__aiodesktop__ = {ws:'%(ws_url)s',fn:'%(init_function)s'};
        document.head.appendChild(s);
    })();
</script>
'''


class Invoker:
    """
    Proxy object for js functions.
    """

    class Fn:
        __slots__ = ('_fn', '_name')

        def __init__(self, fn, name: str):
            self._fn = fn
            self._name = name

        def __repr__(self):
            return f'<js function {self._name!r}>'

        def __call__(self, *args) -> Awaitable:
            return self._fn(self._name, args)

    def __init__(self, fn: Callable[[str, Tuple], Any]):
        self._fn = fn

    def __getattr__(self, item: str) -> Fn:
        """
        Return JS function.
        """
        return self.Fn(self._fn, item)


Package = Tuple[str, str, str]  # (url, file_name, dir)

_MARKER_ATTR = '_aiodesktop_exposed'


def expose(fn: Callable[[Any], Awaitable]):
    """
    Allow async python method to be called from JS.
    """
    assert inspect.iscoroutinefunction(fn), \
        f'only async handlers can be exposed: {fn!r}'
    setattr(fn, _MARKER_ATTR, True)
    return fn


def is_method_exposed(fn: Callable[[Any], Awaitable]) -> bool:
    return getattr(fn, _MARKER_ATTR, False)


class Server:

    @property
    def js(self) -> Invoker:
        """
        Return object to perform calls to JS functions.
        """
        return Invoker(self._call_func)

    @property
    def app(self) -> web.Application:
        """
        Return inner aiohttp application.
        """
        return self._app

    @property
    def bundle(self) -> Bundle:
        """
        Return object for managing bundled files.
        """
        return self._bundle

    @property
    def netloc(self) -> str:
        """
        Return network location string like "127.0.0.1:8000"
        """
        _, host, port = self._setup_info
        return f'{host}:{port}'

    @property
    def start_uri(self) -> str:
        """
        Return full uri to the initial page.
        """
        scheme, host, port = self._setup_info
        url = self.reverse_url(name='index')
        # <scheme>://<netloc>/<path>;<params>?<query>#<fragment>
        _parts = (scheme, self.netloc, url, '', '', '')
        out = urllib.parse.urlunparse(_parts)
        return out

    def __init__(self, *,
                 bundle: Bundle,
                 index_html: Union[str, Resource],
                 app: web.Application = None,
                 init_js_function: str = 'onConnect',
                 wait_for_reconnect=True,
                 json_impl=json,
                 reconnect_timeout_sec=1.0,
                 ):
        """
        :param bundle: server requires bundle to store own files
        :param index_html: path to `index.html` or a string with html
        :param init_js_function: function to be called in JS on client connect
        :param wait_for_reconnect: server will close on client disconnect
        :param reconnect_timeout_sec: (single mode) wait for client to reconnect
        :param json_impl: library to perform JSON de/serialization
        """
        if not isinstance(bundle, Bundle):
            raise AIODesktopError(
                f'Parameter {bundle} must be {Bundle!r} instance'
            )

        if not isinstance(index_html, (str, Resource)):
            raise AIODesktopError(
                f'Parameter `index_html` can be either a html string '
                f'or a {Resource!r} instance, not a {index_html!r}'
            )

        self._bundle = bundle
        self._client: Optional[Client] = None
        self._lost_on: Optional[float] = None
        self._pending_returns: Dict[int, asyncio.Future] = {}
        self._packages: List[Package] = []
        self._index_html = index_html
        self._setup_info: Optional[str, str, int] = None  # scheme, host, port
        self._init_js_function = init_js_function
        self._wait_for_reconnect = wait_for_reconnect
        self._json_impl = json_impl
        self._reconnect_timeout_sec = reconnect_timeout_sec
        self._id_src = 0

        #
        # App setup
        #
        self._app = web.Application() if app is None else app
        self._app.add_routes([
            web.get('/', self._index_handler, name='index'),
            web.get('/__ws__/', self._ws_lifecycle, name='private-ws'),
        ])
        r_main = self._bundle.add(
            pkg_resources.resource_filename('aiodesktop', 'static'),
            mount='aiodesktop'
        )
        self.serve_resource('/__private__/', r_main, name='private-static')

        @self._app.on_startup.append
        async def _on_startup(_: web.Application):
            await self.on_startup()

        @self._app.on_shutdown.append
        async def _on_shutdown(_: web.Application):
            await self.on_shutdown()

    def serve_resource(self, url_prefix: str, r: Resource, *, name: str = None):
        """
        Serve resource files on given url, example:

            >>> server = Server()
            >>> r1 = Bundle().add('some/directory')
            >>> server.serve_resource('/static', r1)  # GET /static/directory/

        """
        assert isinstance(r, Resource), f'{r!r} must be resource'
        dir_prefix = urllib.parse.urljoin(url_prefix + '/', str(r.mount))
        target_path = r.abspath

        if target_path.is_file():
            # aiohttp only supports serving directories

            async def handler(_: web.Request):
                return web.FileResponse(target_path)

            self._app.router.add_get(dir_prefix, handler, name=name)
            logger.debug(
                'added custom file route: %r -> %r',
                dir_prefix, target_path
            )
        else:
            route = web.static(dir_prefix, target_path, name=name)
            self._app.add_routes([route])
            logger.debug(
                'added static directory route: %r -> %r',
                dir_prefix, target_path
            )

    def reverse_url(self, name: str, **kwargs) -> str:
        """
        Get url from view name and kwargs.
        """
        router = self._app.router[name]
        return str(router.url_for(**kwargs))

    def require_packages(self, packages: Dict[str, str], save_dir: str):
        """
            >>> server = Server()
            ... server.require_packages({
            ...  'https://code.jquery.com/jquery-3.4.1.js': 'jquery.js',
            ... }, save_dir='./vendor')
        """
        assert Path(save_dir).exists(), f'Directory {save_dir!r} does not exist'
        for url, file_name in packages.items():
            assert url.startswith('http'), f'Variable {url!r} must be a url'
            self._packages.append((url, file_name, save_dir))

    def run(self, *, scheme='http', host='127.0.0.1', port=None, **kwargs):
        """
        Launch server (this will block)
        """
        self._ensure_packages()

        port = _get_free_port() if port is None else port
        self._setup_info = (scheme, host, port)
        web.run_app(self.app, host=host, port=port, **kwargs)

    async def on_startup(self):
        """
        Called on server startup.
        """

    async def on_shutdown(self):
        """
        Called on server shutdown.
        """
        logger.debug('sending close')
        await self._send({'type': 'close'}, safe=True)

    async def on_connect(self, client: Client) -> None:
        """
        Called when new client connects.
        """
        logger.debug('received ws connection')

        if self._client is None:
            self._client = client
            self._lost_on = None
        else:
            raise NotImplementedError('multiple clients not supported')

    async def stop(self):
        """
        Stop server from the loop.
        """
        await self.app.shutdown()

    async def on_message(self, client: Client, msg: Message) -> None:
        """
        Called on new websocket message.
        """
        if msg['type'] == 'call':
            # JS calls our function
            await self._on_call(msg['id'], msg['name'], msg['args'])
        elif msg['type'] == 'return':
            # JS returns us value
            await self._on_return(msg['id'], msg['ret'])
        else:
            await self.on_custom_message(client, msg)

    async def on_custom_message(self, _: Client, msg: Message) -> None:
        logger.error(f'received unknown message: {msg!r}')

    async def on_disconnect(self, _: Client) -> None:
        """
        Called when client disconnects.
        """
        logger.debug('closed ws connection')
        self._client = None

        if self._wait_for_reconnect:
            self._lost_on = this_lost_on = time.perf_counter()
            wait_for = self._reconnect_timeout_sec

            def after_sleep(_: asyncio.Task):
                if self._client is None and self._lost_on == this_lost_on:
                    logger.debug(f'client did not reconnect in {wait_for} sec')
                    raise KeyboardInterrupt

            wait_task = asyncio_create_task(asyncio.sleep(wait_for))
            wait_task.add_done_callback(after_sleep)

    def _ensure_packages(self):
        def get_path(p: Package) -> str:
            url, file_name, d = p
            return os.path.join(d, file_name)

        missing_packages = [
            p for p in self._packages
            if not os.path.exists(get_path(p))
        ]

        async def download(session: aiohttp.ClientSession, u: str):
            async with session.get(u) as resp:
                return await resp.text()

        async def download_batch(urls: List[str]) -> List[str]:
            async with aiohttp.ClientSession() as session:
                tasks = [download(session, u) for u in urls]
                return await asyncio.gather(*tasks)

        if missing_packages:
            logger.info('downloading missing packages')
            package_texts = asyncio.get_event_loop().run_until_complete(
                download_batch([u for u, file_name, d in missing_packages])
            )
            for p, text in zip(missing_packages, package_texts):
                file_path = get_path(p)
                logger.info('writing file %r', file_path)
                with open(file_path, 'wt') as fp:
                    fp.write(text)

    def _build_insert_code(self):
        return JS_INLINE % dict(
            script_url=self.reverse_url(
                name='private-static',
                filename='aiodesktop.js',
            ),
            ws_url=self.reverse_url('private-ws'),
            init_function=self._init_js_function,
        )

    def _patch_html(self, html: str) -> str:
        try:
            insert_pos = html.rindex('</html>')
        except ValueError:
            raise AIODesktopError(
                f'Could not patch html, is given string valid? {html!r}'
            )
        else:
            insert_code = self._build_insert_code()
            out = html[:insert_pos] + insert_code + html[insert_pos:]
            return out

    async def _index_handler(self, _: web.Request):
        if isinstance(self._index_html, Resource):
            with open(str(self._index_html.abspath), 'rt') as fp:
                base_html = fp.read()
        else:
            base_html = self._index_html

        html = self._patch_html(base_html)
        return web.Response(text=html, content_type='text/html')

    async def _send(self, data: Message, safe=False):
        if self._client is None and safe:
            return
        else:
            await self._client.send(data)

    async def _ws_lifecycle(self, request: web.Request):
        client = Client(self._json_impl)
        await client.prepare(request)

        # Do not `await`, otherwise it will block async for loop
        asyncio_create_task(self.on_connect(client))

        async for msg in client:
            assert isinstance(msg, dict), msg
            logger.debug('received ws message: %r', msg)
            # Process each message in separate task, do not `await` it
            asyncio_create_task(self.on_message(client, msg))

        await self.on_disconnect(client)

    #
    # Calls from JS
    #

    async def _on_call(self, call_id: str, name: str, args):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                'accepted call #%s: %s(%s)',
                call_id, name, ', '.join(map(str, args))
            )

        error: Optional[Tuple[Exception, str]] = None

        try:
            fn = getattr(self, name)
        except AttributeError as e:
            error = e, f'method not found: {name!r}'
        else:
            if not is_method_exposed(fn):
                e = ValueError('')
                error = e, f'method {name!r} is not exposed with {expose!r}'
            else:
                try:
                    coroutine = fn(*args)
                except TypeError as e:
                    sign = inspect.signature(fn)
                    call_str = f'{name}{sign!s} with args {tuple(args)}: {e!r}'
                    error = e, f'failed to invoke {call_str}'
                else:
                    # noinspection PyBroadException
                    try:
                        ret = await coroutine
                    except Exception as e:
                        error = e, f'exception occurred inside fn: {e!r}'
                    else:
                        logger.debug(
                            'sending return #%s: %.100r... (cut to 100 chars)',
                            call_id, ret
                        )
                        await self._send({
                            'type': 'return',
                            'id': call_id,
                            'ret': ret
                        })

        if error:
            exc, error_text = error
            logger.debug('sending error #%s: %s', call_id, error)
            await self._send({
                'type': 'error',
                'id': call_id,
                'error': error_text
            })
            raise exc

    #
    # Calls to JS
    #

    def _new_id(self):
        self._id_src += 1
        return self._id_src

    async def _call_func(self, name: str, args: Tuple[Any, ...]):
        call_id = self._new_id()
        future = asyncio.Future()
        self._pending_returns[call_id] = future
        logger.debug('sending call #%s %r (%r)', call_id, name, args)
        await self._send({
            'type': 'call',
            'id': call_id,
            'name': name,
            'args': args
        })
        ret = await future
        return ret

    async def _on_return(self, call_id: int, ret):
        logger.debug('accepted return #%s: %r', call_id, ret)
        future = self._pending_returns.pop(call_id)
        future.set_result(ret)
