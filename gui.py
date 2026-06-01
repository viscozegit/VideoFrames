"""PyQt6 GUI: main window, quality dialog, progress dialog."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

import config
from extractor import (
    ExtractorError,
    FrameExtractor,
    VideoInfo,
    estimate_output_bytes,
    is_supported_video,
    probe_video,
)


def _format_bytes(n: int) -> str:
    if n <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024.0
        i += 1
    return f"{f:.1f} {units[i]}"


class QualityDialog(QDialog):
    """Shows video metadata + JPG quality slider before extraction."""

    def __init__(self, info: VideoInfo, initial_quality: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle("JPG 품질 설정")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        title = QLabel(info.path.name)
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        meta_lines = [
            f"길이: {info.duration_hms}  ({info.total_frames:,} 프레임 @ {info.fps:.2f} fps)",
            f"해상도: {info.width} × {info.height}",
            f"코덱: {info.codec}",
        ]
        meta = QLabel("\n".join(meta_lines))
        meta.setStyleSheet("color: #555;")
        layout.addWidget(meta)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #ddd;")
        layout.addWidget(sep)

        # Quality slider
        q_row = QHBoxLayout()
        q_row.addWidget(QLabel("JPG 품질:"))
        self.value_label = QLabel(str(initial_quality))
        self.value_label.setStyleSheet("font-weight: 600; min-width: 28px;")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        q_row.addStretch(1)
        q_row.addWidget(self.value_label)
        layout.addLayout(q_row)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(100)
        self.slider.setValue(initial_quality)
        self.slider.setTickInterval(10)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.valueChanged.connect(self._on_quality_changed)
        layout.addWidget(self.slider)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("낮음"))
        scale_row.addStretch(1)
        scale_row.addWidget(QLabel("높음"))
        layout.addLayout(scale_row)

        self.estimate_label = QLabel()
        self.estimate_label.setStyleSheet("color: #555;")
        layout.addWidget(self.estimate_label)
        self._update_estimate(initial_quality)

        self.remember_checkbox = QCheckBox("이 품질 값을 다음에도 사용")
        layout.addWidget(self.remember_checkbox)

        buttons = QDialogButtonBox()
        cancel_btn = buttons.addButton("취소", QDialogButtonBox.ButtonRole.RejectRole)
        start_btn = buttons.addButton("변환 시작", QDialogButtonBox.ButtonRole.AcceptRole)
        start_btn.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_quality_changed(self, value: int) -> None:
        self.value_label.setText(str(value))
        self._update_estimate(value)

    def _update_estimate(self, quality: int) -> None:
        est = estimate_output_bytes(self.info, quality)
        self.estimate_label.setText(f"예상 용량: 약 {_format_bytes(est)}")

    @property
    def quality(self) -> int:
        return self.slider.value()

    @property
    def remember(self) -> bool:
        return self.remember_checkbox.isChecked()


class ExtractWorker(QThread):
    """Runs the extractor on a background thread."""

    progress = pyqtSignal(int)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, extractor: FrameExtractor, parent=None):
        super().__init__(parent)
        self.extractor = extractor

    def run(self) -> None:
        try:
            self.extractor.run(on_progress=self.progress.emit)
        except ExtractorError as e:
            self.failed.emit(str(e))
            return
        except Exception as e:
            self.failed.emit(f"예상치 못한 오류: {e}")
            return
        if not self.extractor.cancelled:
            self.finished_ok.emit()


class ProgressDialog(QDialog):
    def __init__(self, info: VideoInfo, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle("변환 중...")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        title = QLabel(info.path.name)
        title.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(title)

        self.bar = QProgressBar()
        self.bar.setMinimum(0)
        self.bar.setMaximum(max(info.total_frames, 1))
        self.bar.setValue(0)
        layout.addWidget(self.bar)

        self.status_label = QLabel(f"0 / {info.total_frames:,} 프레임")
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        self._cancel_requested = False

    def update_progress(self, current_frame: int) -> None:
        total = self.info.total_frames or 1
        current = min(current_frame, total)
        self.bar.setValue(current)
        self.status_label.setText(f"{current:,} / {total:,} 프레임")

    def _on_cancel(self) -> None:
        self._cancel_requested = True
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("취소 중...")

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested

    def closeEvent(self, event) -> None:  # noqa: N802
        # Treat window close as cancel; we'll handle cleanup in caller.
        if not self._cancel_requested:
            self._cancel_requested = True
        event.accept()


class DropZone(QLabel):
    """Centered drop-zone label that emits a signal when a file is dropped."""

    file_dropped = pyqtSignal(Path)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("📂\n\n비디오 파일을 여기로 드래그\n\n또는 아래 버튼으로 선택")
        self.setStyleSheet(
            """
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 12px;
                padding: 40px;
                color: #555;
                background-color: #fafafa;
                font-size: 14px;
            }
            QLabel[dragHover="true"] {
                border-color: #0a84ff;
                background-color: #eaf3ff;
                color: #0a84ff;
            }
            """
        )
        font = QFont()
        font.setPointSize(14)
        self.setFont(font)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragHover", True)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("dragHover", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self.setProperty("dragHover", False)
        self.style().unpolish(self)
        self.style().polish(self)
        urls = event.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        self.file_dropped.emit(path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video to JPG Frames")
        self.setMinimumSize(520, 420)
        self.settings = config.load()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        header = QLabel("Video to JPG Frames")
        header.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(header)

        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self.handle_file)
        layout.addWidget(self.drop_zone, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        pick_btn = QPushButton("파일 선택...")
        pick_btn.clicked.connect(self._pick_file)
        btn_row.addWidget(pick_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        hint = QLabel("지원 포맷: mp4, mov, m4v, avi, mkv, webm, flv, wmv, mpg, mpeg, ts")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        self._worker: Optional[ExtractWorker] = None
        self._progress_dialog: Optional[ProgressDialog] = None
        self._current_extractor: Optional[FrameExtractor] = None

    def _pick_file(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "비디오 파일 선택",
            str(Path.home()),
            "비디오 파일 (*.mp4 *.mov *.m4v *.avi *.mkv *.webm *.flv *.wmv *.mpg *.mpeg *.ts);;모든 파일 (*)",
        )
        if path_str:
            self.handle_file(Path(path_str))

    def handle_file(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, "오류", f"파일을 찾을 수 없습니다:\n{path}")
            return
        if path.is_dir():
            QMessageBox.warning(self, "오류", "폴더가 아닌 비디오 파일을 끌어주세요.")
            return
        if not is_supported_video(path):
            QMessageBox.warning(
                self,
                "지원하지 않는 형식",
                f"이 파일 형식은 지원되지 않습니다: {path.suffix}\n\n"
                "지원: mp4, mov, m4v, avi, mkv, webm, flv, wmv, mpg, mpeg, ts",
            )
            return

        try:
            info = probe_video(path)
        except ExtractorError as e:
            QMessageBox.critical(self, "비디오 읽기 실패", str(e))
            return

        if info.total_frames <= 0:
            QMessageBox.warning(
                self,
                "비디오 정보 없음",
                "프레임 수를 확인할 수 없습니다. 다른 파일로 시도해주세요.",
            )
            return

        # Quality dialog
        dialog = QualityDialog(info, int(self.settings.get("jpg_quality", 90)), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        quality = dialog.quality
        if dialog.remember:
            self.settings["jpg_quality"] = quality
            self.settings["remember_quality"] = True
            config.save(self.settings)

        # Resolve output folder (handle conflicts)
        output_dir = self._resolve_output_dir(path)
        if output_dir is None:
            return

        base_name = path.stem
        extractor = FrameExtractor(info, output_dir, base_name, quality)
        self._current_extractor = extractor

        progress = ProgressDialog(info, self)
        self._progress_dialog = progress

        worker = ExtractWorker(extractor, self)
        self._worker = worker

        worker.progress.connect(progress.update_progress)
        worker.finished_ok.connect(lambda: self._on_finished(output_dir))
        worker.failed.connect(self._on_failed)

        # Poll for cancel from the dialog
        from PyQt6.QtCore import QTimer
        cancel_timer = QTimer(self)
        cancel_timer.setInterval(150)

        def check_cancel():
            if progress.cancel_requested and not extractor.cancelled:
                extractor.cancel()
            if not worker.isRunning():
                cancel_timer.stop()
                progress.close()

        cancel_timer.timeout.connect(check_cancel)
        cancel_timer.start()

        worker.start()
        progress.exec()

    def _resolve_output_dir(self, video_path: Path) -> Optional[Path]:
        parent = video_path.parent
        base = video_path.stem
        candidate = parent / base
        if not candidate.exists():
            return candidate

        msg = QMessageBox(self)
        msg.setWindowTitle("폴더가 이미 존재")
        msg.setText(f"이미 '{base}' 폴더가 있습니다.")
        msg.setInformativeText("어떻게 처리할까요?")
        overwrite_btn = msg.addButton("덮어쓰기", QMessageBox.ButtonRole.DestructiveRole)
        rename_btn = msg.addButton("다른 이름으로", QMessageBox.ButtonRole.AcceptRole)
        cancel_btn = msg.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(rename_btn)
        msg.exec()
        clicked = msg.clickedButton()

        if clicked is cancel_btn:
            return None
        if clicked is overwrite_btn:
            return candidate
        # Rename: find next available {base}_N
        n = 2
        while True:
            alt = parent / f"{base}_{n}"
            if not alt.exists():
                return alt
            n += 1

    def _on_finished(self, output_dir: Path) -> None:
        if self._progress_dialog:
            self._progress_dialog.close()
        # Count produced files for the completion message
        try:
            count = sum(1 for _ in output_dir.glob("*.jpg"))
        except OSError:
            count = 0

        msg = QMessageBox(self)
        msg.setWindowTitle("변환 완료")
        msg.setText(f"{count:,}개의 프레임을 추출했습니다.")
        msg.setInformativeText(str(output_dir))
        open_btn = msg.addButton("폴더 열기", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("닫기", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(open_btn)
        msg.exec()
        if msg.clickedButton() is open_btn:
            subprocess.run(["open", str(output_dir)])

    def _on_failed(self, message: str) -> None:
        if self._progress_dialog:
            self._progress_dialog.close()
        QMessageBox.critical(self, "변환 실패", message)


def _resolve_app_icon() -> Optional[QIcon]:
    """Locate the bundled app icon — dev (repo/assets) and PyInstaller (_MEIPASS)."""
    import sys
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / "AppIcon.icns")
        candidates.append(Path(meipass) / "assets" / "AppIcon_1024.png")
    here = Path(__file__).resolve().parent
    candidates.append(here / "assets" / "AppIcon.icns")
    candidates.append(here / "assets" / "AppIcon_1024.png")
    for path in candidates:
        if path.exists():
            return QIcon(str(path))
    return None


def run() -> int:
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("Video Frames")
    icon = _resolve_app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    window = MainWindow()
    if icon is not None:
        window.setWindowIcon(icon)
    window.show()
    return app.exec()
