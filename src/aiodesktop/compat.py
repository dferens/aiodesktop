import asyncio
import sys
from typing import Coroutine


MAC = 'mac'
LINUX = 'linux'
WINDOWS = 'windows'


def get_short_os() -> str:
    plat = sys.platform

    if plat == 'darwin':
        return MAC
    elif plat.startswith('linux'):
        return LINUX
    elif plat.startswith('win'):
        return WINDOWS
    else:
        raise NotImplementedError(plat)


if sys.version_info >= (3, 7):
    asyncio_create_task = asyncio.create_task
else:
    def asyncio_create_task(c: Coroutine):
        return asyncio.ensure_future(c)
