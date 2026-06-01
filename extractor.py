"""FFmpeg-backed video → JPG frame extraction."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass
class VideoInfo:
    path: Path
    width: int
    height: int
    fps: float
    duration_sec: float
    total_frames: int
    codec: str

    @property
    def duration_hms(self) -> str:
        s = int(self.duration_sec)
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


class ExtractorError(Exception):
    pass


_COMMON_BIN_DIRS = [
    "/opt/homebrew/bin",   # Apple Silicon Homebrew
    "/usr/local/bin",      # Intel Homebrew / MacPorts
    "/opt/local/bin",      # MacPorts
    "/usr/bin",
]


def _bundled_bin_dirs() -> list[Path]:
    """Locations to search for ffmpeg binaries shipped with this app."""
    here = Path(__file__).resolve().parent
    dirs: list[Path] = []
    # PyInstaller-bundled .app: binaries live under sys._MEIPASS/bin
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(Path(meipass) / "bin")
    # Source checkout: vendor/bin alongside the package
    dirs.append(here / "vendor" / "bin")
    return dirs


def _imageio_ffmpeg_path() -> Optional[str]:
    """Fall back to the ffmpeg shipped with the imageio-ffmpeg pip package (dev only)."""
    try:
        import imageio_ffmpeg  # type: ignore
    except ImportError:
        return None
    try:
        path = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    return path if path and Path(path).exists() else None


def _locate_binary(name: str) -> Optional[str]:
    # 1) Bundled with this app (preferred — works on any Mac, no install needed)
    for d in _bundled_bin_dirs():
        candidate = d / name
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    # 2) imageio-ffmpeg pip package (dev workflow)
    if name == "ffmpeg":
        p = _imageio_ffmpeg_path()
        if p:
            return p
    # 3) User's PATH
    path = shutil.which(name)
    if path:
        return path
    # 4) Common system locations not always on PATH (e.g., GUI launches)
    for d in _COMMON_BIN_DIRS:
        candidate = Path(d) / name
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return None


def find_ffmpeg() -> str:
    path = _locate_binary("ffmpeg")
    if not path:
        raise ExtractorError(
            "ffmpeg를 찾을 수 없습니다.\n"
            "이 앱은 보통 ffmpeg를 내장하고 있어야 합니다. "
            "개발 환경이라면 `pip install imageio-ffmpeg`로 설치하거나 "
            "vendor/bin/ffmpeg에 정적 바이너리를 두세요."
        )
    return path


def probe_video(video_path: Path) -> VideoInfo:
    """Return metadata for `video_path` by parsing ffmpeg's stderr header dump.

    Using ffmpeg-only probing (no ffprobe) keeps the bundled-binary surface
    minimal — only one binary needs to ship with the app.
    """
    ffmpeg = find_ffmpeg()
    # ffmpeg -i with no output spec exits non-zero, but prints stream metadata
    # to stderr — that's what we want.
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(video_path)],
        capture_output=True,
        text=True,
    )
    stderr = result.stderr or ""

    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if not dur_match:
        raise ExtractorError(
            f"비디오를 읽을 수 없습니다:\n{stderr[-500:].strip() or '알 수 없는 오류'}"
        )
    h, m, s = dur_match.groups()
    duration_sec = int(h) * 3600 + int(m) * 60 + float(s)

    video_line_match = re.search(r"Stream #\d+:\d+[^\n]*?Video:[^\n]+", stderr)
    if not video_line_match:
        raise ExtractorError("비디오 스트림을 찾을 수 없습니다.")
    video_line = video_line_match.group(0)

    codec_match = re.search(r"Video:\s*([^\s,]+)", video_line)
    codec = codec_match.group(1) if codec_match else "unknown"

    res_match = re.search(r"\b(\d{2,5})x(\d{2,5})\b", video_line)
    width = int(res_match.group(1)) if res_match else 0
    height = int(res_match.group(2)) if res_match else 0

    # Prefer "tbr" (real frame rate) over "fps" when both appear, since fps is
    # sometimes rounded. ffmpeg prints them like "30 fps, 30 tbr".
    fps = 0.0
    tbr_match = re.search(r"(\d+(?:\.\d+)?)\s*tbr\b", video_line)
    if tbr_match:
        fps = float(tbr_match.group(1))
    else:
        fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps\b", video_line)
        if fps_match:
            fps = float(fps_match.group(1))

    total_frames = int(round(fps * duration_sec)) if fps and duration_sec else 0

    return VideoInfo(
        path=video_path,
        width=width,
        height=height,
        fps=fps,
        duration_sec=duration_sec,
        total_frames=total_frames,
        codec=codec,
    )


def quality_to_qscale(quality: int) -> int:
    """Map JPG quality (1-100) to ffmpeg mjpeg -q:v (2 best ↔ 31 worst)."""
    q = max(1, min(100, int(quality)))
    return round(2 + (31 - 2) * (100 - q) / 99)


def estimate_output_bytes(info: VideoInfo, quality: int) -> int:
    """Rough estimate of total JPG size for all frames at the given quality."""
    if not info.total_frames or not info.width or not info.height:
        return 0
    pixels = info.width * info.height
    # Empirical bytes-per-pixel for JPG at varying quality (very rough)
    bpp = 0.05 + (quality / 100.0) * 0.45
    per_frame = pixels * bpp
    return int(per_frame * info.total_frames)


class FrameExtractor:
    """Runs ffmpeg as a child process and reports progress."""

    def __init__(self, info: VideoInfo, output_dir: Path, base_name: str, quality: int):
        self.info = info
        self.output_dir = output_dir
        self.base_name = base_name
        self.quality = quality
        self._process: Optional[subprocess.Popen] = None
        self._cancelled = False

    def run(self, on_progress: Optional[Callable[[int], None]] = None) -> None:
        """Run ffmpeg synchronously; invoke `on_progress(current_frame)` as it advances."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg = find_ffmpeg()
        pattern = str(self.output_dir / f"{self.base_name}_%06d.jpg")
        qscale = quality_to_qscale(self.quality)

        cmd = [
            ffmpeg,
            "-nostdin",
            "-loglevel", "info",
            "-i", str(self.info.path),
            "-q:v", str(qscale),
            "-vsync", "passthrough",
            "-progress", "pipe:1",
            "-y",
            pattern,
        ]

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        frame_re = re.compile(r"^frame=(\d+)")
        assert self._process.stdout is not None
        for line in self._process.stdout:
            if self._cancelled:
                break
            line = line.strip()
            m = frame_re.match(line)
            if m and on_progress:
                on_progress(int(m.group(1)))

        if self._cancelled:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            return

        return_code = self._process.wait()
        if return_code != 0:
            stderr = self._process.stderr.read() if self._process.stderr else ""
            raise ExtractorError(f"ffmpeg 변환 실패 (code {return_code}):\n{stderr[-1000:]}")

    def cancel(self) -> None:
        self._cancelled = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass

    @property
    def cancelled(self) -> bool:
        return self._cancelled


SUPPORTED_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv",
    ".webm", ".flv", ".wmv", ".mpg", ".mpeg", ".ts",
}


def is_supported_video(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS
