import subprocess
import unittest
from pathlib import Path
from typing import Optional, Awaitable

import timeout_decorator
from aiohttp import web

import aiodesktop


FILES_DIR = Path(__file__) / '..' / 'files'


def launch_chrome_for_tests(url):
    return aiodesktop.launch_chrome(
        url,
        headless=True,
        search_installed=False,
    )


class TestServer(aiodesktop.Server):
    def __init__(self, test_case):
        super().__init__()
        self.coroutine: Awaitable = None
        self.test_case = test_case

        self.app.router.add_get('/add', self.on_add)

    async def on_startup(self):
        self.test_case.chrome = launch_chrome_for_tests(self.start_url)

    async def on_connect(self, chan: aiodesktop.Channel) -> None:
        await super().on_connect(chan)
        await self.coroutine
        await self.stop()

    async def on_add(self, r: web.Request):
        a = int(r.query['a'])
        b = int(r.query['b'])
        c = a + b
        return web.Response(text=str(c))


class AllTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        aiodesktop.ensure_local_chromium()

    def setUp(self) -> None:
        self.chrome: Optional[subprocess.Popen] = None

    def tearDown(self) -> None:
        self.chrome.communicate(timeout=1)
        self.chrome.terminate()

    @timeout_decorator.timeout(10)
    def test_all(self):
        # import logging; logging.basicConfig(level=logging.DEBUG)
        server = TestServer(self)
        server.configure(
            index_html=server.resources.add(FILES_DIR / 'index.html'),
            init_js_function='onConnect',
        )
        completed = False

        async def test_coroutine():
            nonlocal completed

            # Test sync JS method
            self.assertEqual(
                await server.js.syncGetData(),
                {'data': {'list': [1, 2], 'string': 'test'}}
            )

            # Test async JS method
            self.assertEqual(
                await server.js.asyncGetData(),
                {'data': {'list': [1, 2], 'string': 'test'}}
            )

            completed = True

        server.coroutine = test_coroutine()

        server.run()
        self.assertTrue(completed)
