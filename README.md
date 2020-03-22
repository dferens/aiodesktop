# aiodesktop

[![Latest version on
PyPi](https://badge.fury.io/py/aiodesktop.svg)](https://badge.fury.io/py/aiodesktop)
[![Supported Python
versions](https://img.shields.io/pypi/pyversions/aiodesktop.svg)](https://pypi.org/project/aiodesktop/)
[![CircleCI](https://circleci.com/gh/dferens/aiodesktop/tree/master.svg?style=svg)](https://circleci.com/gh/dferens/aiodesktop/tree/master.svg?style=svg)


A set of tools which simplify building cross-platform desktop apps with Python, JavaScript, HTML & CSS.

## Features

In contrast to typical desktop GUI frameworks such as [tkinter](https://docs.python.org/3/library/tk.html#tkinter), [wxPython](https://www.wxpython.org/), [PyQt](https://docs.python.org/3/faq/gui.html#qt) or [Kivy](https://kivy.org/):
* does not define own widgets/layout system ([Kivy](https://kivy.org/doc/stable/guide/lang.html), [Qt](https://www.riverbankcomputing.com/static/Docs/PyQt5/designer.html), [wx](https://stackoverflow.com/questions/31384089/how-am-i-supposed-to-use-wxformbuilder-python-gui-code-in-my-applications)), simply use a browser as a platform which already provides those things
    * reuse time-saving libraries like [React](https://reactjs.org/), [Bootstrap](https://getbootstrap.com/) or [Highcharts](https://www.highcharts.com/)
    * reuse technologies like [WebRTC](https://webrtc.org/), [WebGL](https://webglsamples.org/), [WebAssembly](https://webassembly.org/)
    * access platform features such as [cameras](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices), [geolocation](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API) and [others](https://developer.mozilla.org/en-US/docs/Web/API)
* your app is client-server and cross-platform by design, different devices may use it simultaneously

Compared to existing alternatives such as [Eel](https://github.com/samuelhwilliams/Eel), [async-eel](https://github.com/namuyan/async-Eel) and [guy](https://github.com/manatlan/guy):
* runs on **asyncio** instead of threads or gevent greenlets
* highly customizable **aiohttp** server
* no global state / singleton API


## Install

Install from pypi with `pip`:

```shell
pip install aiodesktop
```

## Hello, World!

```python
import aiodesktop

class Server(aiodesktop.Server):
    async def on_startup(self):
        aiodesktop.launch_chrome(self.start_url)
    
    # Use `expose` decorator to mark method as visible from JS
    @aiodesktop.expose
    async def get_string(self):
        # Use `await self.js.xxx()` to call JS functions from Python 
        return 'Hello, ' + await self.js.getWorld()

server = Server()
server.configure(
    init_js_function='onConnect',
    index_html='''<html><body><script>
    async function onConnect(server) {                        
        // Exposing JS function to python        
        server.expose({
            async getWorld() {
                return 'World!'
            }
        });        
        
        // Use `await server.py.xxx()` to call Python methods from JS
        document.body.innerHTML += await server.py.get_string(); 
    };
</script></body></html>''',
)
server.run()
```
