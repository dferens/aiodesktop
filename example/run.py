#!/usr/bin/env python
import logging
import ssl
from pathlib import Path

import aiodesktop


class Server(aiodesktop.Server):
    async def on_startup(self):
        aiodesktop.launch_chrome(
            self.start_uri,
            search_installed=False,
        )


logging.basicConfig(level=logging.DEBUG)

project_dir = Path(__file__).parent
static_dir = project_dir / 'static'

bundle = aiodesktop.Bundle()
r_index = bundle.add(project_dir / 'index.html')
r_dist = bundle.add(static_dir / 'dist')
r_cert = bundle.add(project_dir / 'cert')

server = Server(
    bundle=bundle,
    index_html=r_index,
)
server.serve_resource('/static', r_dist)

if __name__ == '__main__':
    ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_ctx.load_cert_chain(
        str(r_cert.abspath / 'domain.crt'),
        str(r_cert.abspath / 'domain.key'),
    )
    server.run(
        scheme='https',
        host='0.0.0.0',
        port=8000,
        ssl_context=ssl_ctx
    )
