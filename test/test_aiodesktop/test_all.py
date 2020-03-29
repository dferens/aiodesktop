import logging
import subprocess
import unittest
from pathlib import Path
from typing import Optional, Awaitable

import timeout_decorator
from aiohttp import web

import aiodesktop


FILES_DIR = Path(__file__).parent / 'files'


def launch_chrome_for_tests(url):
    return aiodesktop.launch_chrome(
        url,
        headless=True,
        search_installed=False,
    )


class TestServer(aiodesktop.Server):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.coroutine: Awaitable = None
        self.test_case = None
        self.app.router.add_get('/add', self.on_add)

    async def on_startup(self):
        self.test_case.chrome = launch_chrome_for_tests(self.start_uri)

    async def on_connect(self, client: aiodesktop.Client) -> None:
        await super().on_connect(client)
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
        if self.chrome is not None:
            self.chrome.terminate()

    @timeout_decorator.timeout(100000)
    def test_all(self):
        logging.basicConfig(level=logging.DEBUG)
        bundle = aiodesktop.Bundle()
        server = TestServer(
            bundle=bundle,
            index_html=bundle.add(FILES_DIR / 'index.html'),
            init_js_function='onConnect',
        )
        server.test_case = self

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
