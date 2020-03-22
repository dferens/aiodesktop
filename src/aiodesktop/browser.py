import argparse
import json
import logging
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import List, Dict, Optional

from . import compat


logger = logging.getLogger(__name__)

CHROME_HOST = 'https://storage.googleapis.com/chromium-browser-snapshots'


def _get_chrome_zip_name() -> str:
    zip_name = {
        compat.MAC: 'chrome-mac',
        compat.LINUX: 'chrome-linux',
        compat.WINDOWS: 'chrome-win',
    }[compat.get_short_os()]
    return zip_name


def _get_chrome_build_url(revision: int) -> str:
    directory = {
        compat.MAC: 'Mac',
        compat.LINUX: 'Linux_x64',
        compat.WINDOWS: 'Win_x64',
    }[compat.get_short_os()]
    zip_dir_name = _get_chrome_zip_name()
    url = '/'.join([
        CHROME_HOST,
        directory,
        str(revision),
        f'{zip_dir_name}.zip',
    ])
    return url


def _get_chromium_bin_path(path: Path) -> Path:
    rel_bin_path = {
        compat.MAC: 'Chromium.app/Contents/MacOS/Chromium',
        compat.LINUX: 'chrome',
        compat.WINDOWS: 'chrome.exe',
    }[compat.get_short_os()]
    return path / _get_chrome_zip_name() / rel_bin_path


def get_chrome_revisions() -> List[int]:
    """
    Uses http://omahaproxy.appspot.com/ to obtain latest chrome revision.
    """
    url = 'https://omahaproxy.appspot.com/all.json'
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())

    assert isinstance(data, list), data
    json_os_string = {
        compat.MAC: 'mac',
        compat.LINUX: 'linux',
        compat.WINDOWS: 'win64',
    }[compat.get_short_os()]
    os_versions: List[Dict[str, str]] = next(
        versions['versions'] for versions in data
        if versions['os'] == json_os_string
    )
    revisions = [int(v['branch_base_position']) for v in os_versions]
    return revisions


def _does_url_exist(url: str) -> bool:
    req = urllib.request.Request(url, method='HEAD')
    try:
        with urllib.request.urlopen(req) as resp:
            resp.read()
            return resp.status == 200
    except urllib.error.HTTPError:
        return False


def _make_download_reporter(interval: float):
    last_time = -1

    def reporter(block_num: int, block_size: int, size: int):
        nonlocal last_time
        now = time.time()
        done_amount = min(block_num * block_size / size, 1)
        should_print = (
            (last_time == -1) or
            (now - last_time) > interval or
            done_amount == 1
        )
        if should_print:
            logger.info('done %.2f %%', done_amount * 100)
            last_time = now

    return reporter


def _fix_chrome_permissions(path: Path):
    bin_path = _get_chromium_bin_path(path)
    assert bin_path.exists() and bin_path.is_file()
    bin_path.chmod(
        # Make binary executable
        bin_path.stat().st_mode | stat.S_IEXEC
    )
    if compat.get_short_os() == compat.MAC:
        # [0322/162430.100064:FATAL:double_fork_and_exec.cc(126)] execvp
        # aiodesktop/chrome-mac/Chromium.app/Contents/Frameworks/Chromium
        # Framework.framework/Versions/81.0.4044.0/Helpers/
        # chrome_crashpad_handler: Permission denied (13)
        bins_dir = path / _get_chrome_zip_name() / 'Chromium.app/Contents/Frameworks'
        subprocess.run(f'chmod -R +x {bins_dir}', shell=True)


def _download_chromium(rev: int, extract_path: Path) -> Path:
    temp_path = Path(tempfile.mkdtemp(dir=extract_path, suffix='.temp'))

    try:
        zip_file_path = temp_path / 'archive.zip'
        download_url = _get_chrome_build_url(rev)
        logger.info('downloading %s to %s', download_url, zip_file_path)
        urllib.request.urlretrieve(
            url=download_url,
            filename=zip_file_path,
            reporthook=_make_download_reporter(interval=1)
        )
        with zipfile.ZipFile(zip_file_path, 'r') as zip_fp:
            zip_fp.extractall(extract_path)

        bin_path = _get_chromium_bin_path(extract_path)
        _fix_chrome_permissions(extract_path)
        return bin_path
    finally:
        shutil.rmtree(temp_path)


def _download_latest_chromium(path=None) -> Path:
    """
    Download latest chromium build current directory, return path to binary.
    """
    all_revisions = get_chrome_revisions()
    try:
        download_rev = next(
            rev
            for rev in sorted(all_revisions, reverse=True)
            if _does_url_exist(_get_chrome_build_url(rev))
        )
    except StopIteration:
        raise ValueError('Not able to find latest chrome zip')
    else:
        if path is None:
            extract_path = Path(os.getcwd())
        else:
            extract_path = Path(path)
            extract_path.mkdir(parents=True, exist_ok=True)

        _download_chromium(download_rev, extract_path)
        bin_path = _get_chromium_bin_path(extract_path)
        logger.info('chrome binary in %s', bin_path)
        return bin_path


def _find_chrome_on_mac() -> Optional[str]:
    name = 'Google Chrome.app'
    bin_path = 'Contents/MacOS/Google Chrome'
    default_dir = '/Applications'

    path = os.path.join(default_dir, name, bin_path)
    if os.path.exists(path):
        return Path(path)

    paths = subprocess.check_output(['mdfind', name]).decode().splitlines()
    dir_path = next(
        (p for p in paths if p.endswith(name)),
        None
    )

    if dir_path:
        return Path(os.path.join(dir_path, bin_path))

    return None


def _find_chrome_on_windows() -> Optional[Path]:
    # noinspection PyUnresolvedReferences
    import winreg
    reg_path = \
        r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe'

    for install_type in winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE:
        try:
            reg_key = winreg.OpenKey(install_type, reg_path, 0, winreg.KEY_READ)
            chrome_path = winreg.QueryValue(reg_key, None)
            reg_key.Close()
        except WindowsError:
            chrome_path = None
        else:
            break

    return Path(chrome_path)


def _find_chrome_on_linux() -> Optional[Path]:
    import whichcraft as wch
    chrome_names = [
        'chromium-browser',
        'chromium',
        'google-chrome',
        'google-chrome-stable'
    ]

    for name in chrome_names:
        chrome = wch.which(name)
        if chrome is not None:
            return Path(chrome)
    return None


def find_installed_chrome() -> Optional[Path]:
    return {
        compat.MAC: _find_chrome_on_mac,
        compat.LINUX: _find_chrome_on_linux,
        compat.WINDOWS: _find_chrome_on_windows,
    }[compat.get_short_os()]()


def ensure_local_chromium() -> Path:
    cache_path = Path(os.getcwd()) / '.downloads'
    cache_path.mkdir(parents=False, exist_ok=True)
    bin_path = _get_chromium_bin_path(cache_path)

    if not bin_path.exists():
        _download_latest_chromium(cache_path)

    assert bin_path.is_file(), bin_path
    return bin_path


def launch_chrome(
    start_url: str, *args: str,
    path=None,
    search_installed=True,
    fullscreen=False,
    headless=False,
    debug_port=None,
):
    """
    Start chrome process asynchronously.

    :param start_url: initial url to open
    :param args: additional args to `subprocess.Popen`
    :param path: path to chrome binary
    :param search_installed:
    :param fullscreen:
    :param headless: start without a window
    :param debug_port:
    """
    if path is None:
        if search_installed:
            path = find_installed_chrome()

        if path is None:
            path = ensure_local_chromium()

    full_args = [path]
    last_args = []

    if headless:
        assert not fullscreen
        # --repl makes it stay alive
        full_args.extend(['--headless', '--repl'])
        last_args.append(start_url)

        if sys.platform.startswith('win'):
            # https://developers.google.com/web/updates/2017/04/headless-chrome#cli
            full_args.append('--disable-gpu')
    else:
        full_args.append('--app=%s' % start_url)

    full_args.extend(args)

    if fullscreen:
        full_args.append('--start-fullscreen')

    if debug_port is not None:
        full_args.append('--remote-debugging-port={}'.format(debug_port))

    full_args.extend(last_args)
    return subprocess.Popen(
        full_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE
    )


def main():
    loglevel_aliases = dict(
        debug=logging.DEBUG,
        info=logging.INFO,
        warning=logging.WARNING,
        error=logging.ERROR,
        critical=logging.CRITICAL,
    )
    p = argparse.ArgumentParser()
    p.add_argument(
        '-l', '--loglevel', dest='loglevel',
        default='info', choices=list(loglevel_aliases)
    )
    subparsers = p.add_subparsers(dest='subparser_name')
    download_p = subparsers.add_parser('download')
    download_p.add_argument('--path', help='directory to store binary')
    parsed = p.parse_args()
    logging.basicConfig(level=loglevel_aliases[parsed.loglevel])

    if parsed.subparser_name == 'download':
        ensure_local_chromium()
    else:
        p.print_help()


if __name__ == '__main__':
    main()
