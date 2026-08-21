# PyInstaller spec for ExamVariator desktop build (Windows).
# Build from backend_exam_variator/ AFTER building the frontend:
#   cd frontend_exam_variator && npm ci && npm run build
#   cd ../backend_exam_variator && pyinstaller exam_variator.spec --noconfirm

import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None

frontend_out = os.path.join("..", "frontend_exam_variator", "out")
if not os.path.isdir(frontend_out):
    raise SystemExit(
        "frontend_exam_variator/out not found - build the frontend first: "
        "cd ../frontend_exam_variator && npm ci && npm run build"
    )

datas = [(frontend_out, "frontend")]
binaries = []
hiddenimports = [
    # uvicorn's lazy imports are invisible to static analysis
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]

# litellm/groq/pymupdf4llm load data files and modules dynamically
for pkg in ("litellm", "groq", "pymupdf4llm"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h


a = Analysis(
    ["run_desktop.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy.tests"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ExamVariator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)
