# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 — 图书馆预约系统 Windows 版
用法: pyinstaller library_win.spec
输出: dist/library_seat_booker.exe
"""

import os
import sys

block_cipher = None

project_dir = SPECPATH

# 收集 ddddocr 的 ONNX 模型文件（必须在 Analysis 之前）
from PyInstaller.utils.hooks import collect_data_files
ddddocr_datas = collect_data_files('ddddocr', includes=['**/*.onnx'])

a = Analysis(
    [os.path.join(project_dir, 'library_gui.py')],
    pathex=[project_dir],
    binaries=[],
    datas=[
        (os.path.join(project_dir, 'config.json'), '.'),
    ] + ddddocr_datas,
    hiddenimports=[
        'libseat_bot',
        'requests',
        'Crypto.Cipher',
        'Crypto.Util.Padding',
        'bs4',
        'ddddocr',
        'cv2',
        'numpy',
        'PIL',
        'onnxruntime',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'pandas', 'scipy', 'IPython',
        'jupyter', 'notebook', 'tkinter.test',
        'torch', 'torchvision', 'torchaudio',
        'tensorflow', 'keras',
        'paddle', 'paddlepaddle',
        'sklearn', 'scikit-learn',
        'transformers', 'tokenizers',
        'pyarrow', 'altair',
        'grpc', 'grpcio',
        'sqlalchemy', 'psycopg2', 'psycopg_binary',
        'numba', 'llvmlite',
        'sentry_sdk', 'opentelemetry',
        'gevent', 'zope',
        'rich', 'pygments',
        'uvicorn', 'fastapi', 'starlette',
        'websockets', 'anyio',
        'jsonschema', 'pydantic',
        'dns', 'nacl',
        'lxml.isoschematron', 'lxml.objectify',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='library_seat_booker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # 不显示控制台窗口
    windowed=True,          # GUI 应用
    icon=os.path.join(project_dir, 'assets', 'icon.ico') if os.path.exists(os.path.join(project_dir, 'assets', 'icon.ico')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='library_seat_booker',
)
