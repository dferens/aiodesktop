# -*- mode: python ; coding: utf-8 -*-
import os
import importlib
import sys; sys.path.append(os.getcwd())

block_cipher = None

resources = importlib.import_module('run').server.resources
a = Analysis(['run.py'],
             pathex=[os.getcwd()],
             binaries=[],
             datas=resources.get_pyinstaller_data(),
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='run',
          debug=not False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True )
