# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for AI Verification Engine.

用 collect_all() 批量收集所有依赖的子模块、数据文件和二进制文件，
彻底避免运行时缺 version.txt / 模板 / cmap 等数据文件的问题。

用法：
    pyinstaller --noconfirm AI-Verification-Engine.spec
"""
from PyInstaller.utils.hooks import collect_all

# 需要完整收集的包：这些包在运行时会读取自己的数据文件
# （version.txt、前端资源、模板、cmap、样式表等），
# PyInstaller 默认的静态 import 分析可能漏掉非 .py 文件。
COLLECT_PACKAGES = [
    # ---- gradio 核心及其直接依赖 ----
    'gradio',
    'gradio_client',
    'safehttpx',
    'groovy',
    'huggingface_hub',
    # ---- Web 框架 ----
    'fastapi',
    'starlette',
    'uvicorn',
    'pydantic',
    'pydantic_core',
    'jsonschema',
    'rfc3987',
    # ---- HTTP / 异步 ----
    'httpx',
    'httpcore',
    'anyio',
    'websockets',
    'aiofiles',
    'requests',
    'urllib3',
    # ---- 模板 / 文本处理 ----
    'jinja2',
    'markupsafe',
    'markdown_it',
    'pygments',
    'rich',
    # ---- 文档解析 ----
    'pdfplumber',
    'pdfminer',
    'docx',
    # ---- 其他 ----
    'python_multipart',
    'orjson',
    'yaml',
    'click',
    'typer',
    'packaging',
]

datas = []
binaries = []
hiddenimports = []

print("Collecting package data files ...")
for pkg in COLLECT_PACKAGES:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
        print(f"  [OK] {pkg:25s} -> {len(pkg_datas):4d} data files")
    except Exception as e:
        print(f"  [SKIP] {pkg:25s} -> {e}")

# 项目自带的数据目录
datas += [
    ('rules', 'rules'),
    ('samples', 'samples'),
    ('config', 'config'),
    ('docs', 'docs'),
]

# uvicorn 运行时动态导入的模块（静态分析抓不到）
hiddenimports += [
    'uvicorn.logging',
    'uvicorn.loops.auto',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan.on',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AI-Verification-Engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
