# PyInstaller spec for Video Frames app
# Build with: pyinstaller VideoFrames.spec --noconfirm

block_cipher = None


import os
import shutil

# Resolve the static ffmpeg shipped with the imageio-ffmpeg pip package and
# copy it into vendor/bin/ffmpeg so PyInstaller bundles it under a stable name.
def _stage_bundled_ffmpeg():
    try:
        import imageio_ffmpeg
    except ImportError as e:
        raise SystemExit(
            "imageio-ffmpeg is required for a portable build. "
            "Run: pip install -r requirements.txt"
        ) from e
    src = imageio_ffmpeg.get_ffmpeg_exe()
    if not src or not os.path.exists(src):
        raise SystemExit(f"imageio-ffmpeg did not return a usable binary: {src!r}")
    dst_dir = os.path.join('vendor', 'bin')
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, 'ffmpeg')
    if (not os.path.exists(dst)) or os.path.getsize(dst) != os.path.getsize(src):
        shutil.copy2(src, dst)
        os.chmod(dst, 0o755)
    return dst

_FFMPEG_PATH = _stage_bundled_ffmpeg()
_FFMPEG_BINARIES = [(_FFMPEG_PATH, 'bin')]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_FFMPEG_BINARIES,
    datas=[
        ('assets/AppIcon.icns', 'assets'),
        ('assets/AppIcon_1024.png', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'PIL',
        'scipy',
        'pandas',
        'pytest',
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
    name='VideoFrames',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='VideoFrames',
)

app = BUNDLE(
    coll,
    name='Video Frames.app',
    icon='assets/AppIcon.icns',
    bundle_identifier='com.com2us.videoframes',
    info_plist={
        'CFBundleName': 'Video Frames',
        'CFBundleDisplayName': 'Video Frames',
        'CFBundleShortVersionString': '0.1.0',
        'CFBundleVersion': '0.1.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
        'NSHumanReadableCopyright': 'Copyright © 2026',
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'Video File',
                'CFBundleTypeRole': 'Viewer',
                'LSItemContentTypes': [
                    'public.movie',
                    'public.video',
                    'public.mpeg-4',
                    'com.apple.quicktime-movie',
                ],
            }
        ],
    },
)
