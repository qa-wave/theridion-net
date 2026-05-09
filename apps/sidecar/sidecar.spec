# PyInstaller spec for the Theridion sidecar.
#
# zeep, pydantic, fastapi, and uvicorn all do dynamic imports that
# PyInstaller's static analysis can miss. We collect everything from
# them up-front so the bundle isn't missing modules at runtime.
#
# Build with:  uv run pyinstaller sidecar.spec --clean --noconfirm

# ruff: noqa: F821  -- spec-file globals are injected by PyInstaller.

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
for pkg in ("zeep", "fastapi", "uvicorn", "pydantic", "lxml", "httpx"):
    pkg_datas, pkg_bins, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_bins
    hiddenimports += pkg_hidden

# uvicorn loads its loop / protocol / lifespan implementations through
# importlib at startup; PyInstaller misses those without explicit hints.
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]


a = Analysis(
    ["scripts/sidecar_entry.py"],
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
    name="theridion-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # macOS code signing dislikes UPX-compressed binaries.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # we read stdout from the parent process; must be a console binary.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
