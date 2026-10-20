import subprocess
import tempfile
import threading
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ffmpeg_manager import hidden_process_flags
from ffmpeg_runner import (
    calculate_estimated_quality_size_mb,
    calculate_minimum_target_size_mb,
    calculate_recommended_target_size_mb,
    calculate_gif_palette_colors,
    build_upscale_command,
    get_audio_stream_codecs,
)


QUALITY_ESTIMATE_SAMPLE_DURATION = 1.0
QUALITY_ESTIMATE_MAX_SAMPLED_DURATION = 3.0


def format_video_duration(duration_seconds):
    """Format a duration as hours, minutes, and seconds."""

    total_seconds = round(duration_seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02}:{seconds:02}"

    return f"{minutes}:{seconds:02}"


class QualityEstimateWorker(QThread):
    """Estimate output size by encoding short video samples in the background."""

    estimate_ready = pyqtSignal(int, object, int, float)
    estimate_failed = pyqtSignal(int, object, str)

    def __init__(
        self,
        generation,
        estimate_key,
        settings,
        parent=None,
    ):
        super().__init__(parent)
        self.generation = generation
        self.estimate_key = estimate_key
        self.settings = settings
        self.cancel_requested = threading.Event()
        self.process_lock = threading.Lock()
        self.active_process = None
        self.result_emitted = False

    def cancel(self):
        """Request cancellation and stop the currently running FFmpeg process."""

        self.cancel_requested.set()

        with self.process_lock:
            process = self.active_process

        if process is not None and process.poll() is None:
            try:
                process.terminate()

            except ProcessLookupError:
                pass

    def run(self):
        try:
            estimated_size = self.estimate_output_size()

        except (
            OSError,
            ValueError,
            subprocess.SubprocessError,
            TypeError,
            KeyError,
            RuntimeError,
        ) as error:
            if not self.cancel_requested.is_set():
                self.result_emitted = True
                self.estimate_failed.emit(
                    self.generation,
                    self.estimate_key,
                    str(error),
                )

        else:
            if (
                estimated_size is not None
                and not self.cancel_requested.is_set()
            ):
                self.result_emitted = True
                self.estimate_ready.emit(
                    self.generation,
                    self.estimate_key,
                    self.settings["quality"],
                    estimated_size,
                )

    def estimate_output_size(self):
        """Encode up to three representative segments and extrapolate their size."""

        settings = self.settings
        duration = settings["trim_end"] - settings["trim_start"]

        if duration <= 0:
            raise ValueError("The selected video range has no duration.")

        if duration <= QUALITY_ESTIMATE_MAX_SAMPLED_DURATION:
            sample_ranges = [
                (
                    settings["trim_start"],
                    settings["trim_end"],
                )
            ]

        else:
            sample_duration = QUALITY_ESTIMATE_SAMPLE_DURATION
            start_offsets = (
                0.0,
                (duration - sample_duration) / 2,
                duration - sample_duration,
            )
            sample_ranges = [
                (
                    settings["trim_start"] + offset,
                    settings["trim_start"] + offset + sample_duration,
                )
                for offset in start_offsets
            ]

        input_path = settings["input_path"]
        output_format = settings["output_format"]
        audio_stream_codecs = (
            get_audio_stream_codecs(input_path)
            if output_format != "gif"
            else None
        )

        sampled_bytes = 0
        sampled_duration = 0.0

        with tempfile.TemporaryDirectory(
            prefix="ffupscale-estimate-"
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)

            for index, (sample_start, sample_end) in enumerate(sample_ranges):
                if self.cancel_requested.is_set():
                    return None

                sample_duration = sample_end - sample_start
                output_path = (
                    temporary_path / f"sample_{index}.{output_format}"
                )

                ffmpeg_path, arguments = build_upscale_command(
                    input_path=input_path,
                    output_path=output_path,
                    width=settings["width"],
                    height=settings["height"],
                    quality=settings["quality"],
                    fps=settings["fps"],
                    encoder=settings["encoder"],
                    preset=settings["preset"],
                    rate_control="quality",
                    duration=settings["source_duration"],
                    source_fps=settings["source_fps"],
                    trim_start=sample_start,
                    trim_end=sample_end,
                    merge_audio_tracks=settings["merge_audio_tracks"],
                    output_format=output_format,
                    gif_dither=settings["gif_dither"],
                    audio_stream_codecs=audio_stream_codecs,
                )

                arguments[0:0] = ["-v", "error"]
                if self.cancel_requested.is_set():
                    return None

                error_log_path = (
                    temporary_path / f"sample_{index}.log"
                )

                with error_log_path.open("wb") as error_log:
                    process = subprocess.Popen(
                        [ffmpeg_path, *arguments],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=error_log,
                        creationflags=(
                            hidden_process_flags()
                            | getattr(
                                subprocess,
                                "BELOW_NORMAL_PRIORITY_CLASS",
                                0,
                            )
                        ),
                    )

                    with self.process_lock:
                        self.active_process = process
                        cancelled = self.cancel_requested.is_set()

                    if cancelled:
                        self._terminate_process(process)

                    while not cancelled and process.poll() is None:
                        if self.cancel_requested.wait(0.1):
                            self._terminate_process(process)
                            cancelled = True

                    with self.process_lock:
                        if self.active_process is process:
                            self.active_process = None

                    if cancelled:
                        return None

                error_output = error_log_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

                if process.returncode != 0:
                    raise ValueError(
                        "FFmpeg could not estimate the output size."
                        + (
                            f"\n\n{error_output.strip()}"
                            if error_output.strip()
                            else ""
                        )
                    )

                sampled_bytes += output_path.stat().st_size
                sampled_duration += sample_duration

        return (
            sampled_bytes
            / sampled_duration
            * duration
            / 1_000_000
        )

    @staticmethod
    def _terminate_process(process):
        """Stop a sample encode promptly when it is cancelled."""

        if process.poll() is None:
            try:
                process.terminate()

            except ProcessLookupError:
                pass

        try:
            process.wait(timeout=1.0)

        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


# -- Settings Page --


class SettingsPage(QWidget):
    """Collect encoding settings and report user actions to MainWindow."""

    # MainWindow owns navigation and FFmpeg, so this page communicates by signal.
    back_requested = pyqtSignal()
    render_requested = pyqtSignal(dict)
    cancel_requested = pyqtSignal()
    queue_requested = pyqtSignal(dict)
    view_queue_requested = pyqtSignal()

    def __init__(self):
        super().__init__()

        # -- Page State --

        self.is_rendering = False
        self.input_path = None
        self.video_duration = None
        self.source_fps = None
        self.source_width = None
        self.source_height = None
        self.quality_estimate_generation = 0
        self.quality_estimate_worker = None
        self.pending_quality_estimate = None
        self.current_quality_estimate_key = None
        self.quality_estimate_cache = {}

        self.quality_estimate_timer = QTimer(self)
        self.quality_estimate_timer.setSingleShot(True)
        self.quality_estimate_timer.setInterval(400)
        self.quality_estimate_timer.timeout.connect(
            self.start_quality_estimate
        )

        application = QApplication.instance()

        if application is not None:
            application.aboutToQuit.connect(
                self.shutdown_quality_estimate
            )

        # -- Page Header --

        title = QLabel("Settings")
        title.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
        """)

        self.video_thumbnail = QLabel("No preview")
        self.video_thumbnail.setFixedSize(160, 91)
        self.video_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_thumbnail.setStyleSheet("""
            background-color: #242424;
            border-radius: 10px;
            color: #999999;
            font-size: 11px;
        """)

        self.video_resolution = QLabel("—")
        self.video_duration_label = QLabel("—")
        self.video_fps = QLabel("—")
        self.video_file_size = QLabel("—")

        video_metadata_layout = QHBoxLayout()
        video_metadata_layout.setContentsMargins(0, 0, 0, 0)
        video_metadata_layout.setSpacing(20)

        for label, value in (
            ("Resolution", self.video_resolution),
            ("Duration", self.video_duration_label),
            ("FPS", self.video_fps),
            ("File size", self.video_file_size),
        ):
            metadata_item = QVBoxLayout()
            metadata_item.setContentsMargins(0, 0, 0, 0)
            metadata_item.setSpacing(2)

            caption = QLabel(label)
            caption.setStyleSheet("""
                color: #999999;
                font-size: 11px;
            """)
            value.setStyleSheet("""
                font-size: 13px;
                font-weight: bold;
            """)

            metadata_item.addWidget(caption)
            metadata_item.addWidget(value)
            video_metadata_layout.addLayout(metadata_item)

        video_summary_layout = QVBoxLayout()
        video_summary_layout.setContentsMargins(0, 0, 0, 8)
        video_summary_layout.setSpacing(4)
        video_summary_layout.addWidget(title)
        video_summary_layout.addLayout(video_metadata_layout)

        video_summary_widget = QWidget()
        video_summary_widget.setLayout(video_summary_layout)

        self.view_queue_button = QPushButton("View queue")

        self.view_queue_button.setFixedWidth(110)

        self.view_queue_button.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                font-weight: bold;
                padding: 6px;
            }
        """)

        self.view_queue_button.clicked.connect(self.view_queue_requested.emit)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        header_layout.setSpacing(8)
        header_layout.addWidget(self.video_thumbnail)
        header_layout.addWidget(
            video_summary_widget,
            stretch=1,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )

        header_layout.addWidget(
            self.view_queue_button,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )

        self.video_name = QLabel("No video selected")
        self.video_name.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )

        header_section_layout = QVBoxLayout()
        header_section_layout.setContentsMargins(0, 0, 0, 0)
        header_section_layout.setSpacing(10)
        header_section_layout.addLayout(header_layout)
        header_section_layout.addWidget(self.video_name)

        # -- Trim Range --

        self.trim_checkbox = QCheckBox(
            "Render only part of the video"
        )

        self.trim_start_box = QDoubleSpinBox()
        self.trim_start_box.setRange(
            0.0,
            86_400.0,
        )
        self.trim_start_box.setDecimals(3)
        self.trim_start_box.setSingleStep(0.1)
        self.trim_start_box.setSuffix(" s")
        self.trim_start_box.setToolTip(
            "Position where the exported clip begins."
        )

        self.trim_end_box = QDoubleSpinBox()
        self.trim_end_box.setRange(
            0.0,
            86_400.0,
        )
        self.trim_end_box.setDecimals(3)
        self.trim_end_box.setSingleStep(0.1)
        self.trim_end_box.setSuffix(" s")
        self.trim_end_box.setToolTip(
            "Position where the exported clip ends."
        )

        self.trim_duration_label = QLabel(
            "Selected duration: —"
        )

        self.trim_duration_label.setStyleSheet("""
            color: #999999;
            font-size: 11px;
        """)

        self.reset_trim_button = QPushButton(
            "Reset to full video"
        )

        self.reset_trim_button.clicked.connect(
            self.reset_trim_range
        )

        self.trim_checkbox.toggled.connect(
            self.update_trim_controls
        )

        self.trim_start_box.valueChanged.connect(
            self.update_trim_summary
        )

        self.trim_end_box.valueChanged.connect(
            self.update_trim_summary
        )

        self.trim_start_box.valueChanged.connect(
            self.update_automatic_recommendation
        )

        self.trim_end_box.valueChanged.connect(
            self.update_automatic_recommendation
        )

        self.trim_checkbox.toggled.connect(
            self.update_automatic_recommendation
        )

        self.trim_checkbox.toggled.connect(
            self.update_quality_size_estimate
        )

        self.trim_start_box.valueChanged.connect(
            self.update_quality_size_estimate
        )

        self.trim_end_box.valueChanged.connect(
            self.update_quality_size_estimate
        )

        # -- Resolution Settings --

        self.resolution_box = QComboBox()
        # Item data holds the actual dimensions used by FFmpeg.

        self.resolution_box.addItem(
            "Same as source",
            "source",
        )

        self.resolution_box.addItem(
            "1280 × 720",
            (1280, 720),
        )

        self.resolution_box.addItem(
            "1920 × 1080",
            (1920, 1080),
        )

        self.resolution_box.addItem(
            "2560 × 1440",
            (2560, 1440),
        )

        self.resolution_box.addItem(
            "3840 × 2160",
            (3840, 2160),
        )

        self.resolution_box.addItem(
            "Custom",
            None,
        )

        self.custom_width = QSpinBox()
        self.custom_width.setRange(16, 16384)
        self.custom_width.setValue(1920)
        self.custom_width.setSuffix(" px")
        self.custom_width.setSingleStep(2)

        self.custom_height = QSpinBox()
        self.custom_height.setRange(16, 8640)
        self.custom_height.setValue(1080)
        self.custom_height.setSuffix(" px")
        self.custom_height.setSingleStep(2)

        self.custom_width.valueChanged.connect(self.update_target_size_estimate)

        self.custom_height.valueChanged.connect(self.update_target_size_estimate)

        custom_resolution_layout = QHBoxLayout()
        custom_resolution_layout.setContentsMargins(0, 0, 0, 0)
        custom_resolution_layout.setSpacing(3)

        multiply_label = QLabel("×")

        custom_resolution_layout.addWidget(self.custom_width)

        custom_resolution_layout.addWidget(multiply_label)

        custom_resolution_layout.addWidget(self.custom_height)

        custom_resolution_layout.addStretch()

        self.custom_resolution_widget = QWidget()
        self.custom_resolution_widget.setLayout(custom_resolution_layout)

        self.custom_resolution_label = QLabel("Custom resolution:")

        # -- Frame Rate Settings --

        self.fps_box = QComboBox()
        # String sentinels distinguish special options from numeric frame rates.
        self.fps_box.addItem(
            "Keep original",
            "original",
        )

        self.fps_box.addItem(
            "24 FPS",
            24,
        )

        self.fps_box.addItem(
            "30 FPS",
            30,
        )

        self.fps_box.addItem(
            "60 FPS",
            60,
        )

        self.fps_box.addItem(
            "120 FPS",
            120,
        )

        self.fps_box.addItem(
            "Custom",
            "custom",
        )

        self.custom_fps = QDoubleSpinBox()
        self.custom_fps.setRange(1.0, 240.0)
        self.custom_fps.setValue(60.0)
        self.custom_fps.setDecimals(3)
        self.custom_fps.setSingleStep(1.0)
        self.custom_fps.setSuffix(" FPS")

        self.custom_fps_label = QLabel("Custom frame rate:")

        self.fps_box.currentIndexChanged.connect(self.update_custom_fps_visibility)

        self.fps_box.currentIndexChanged.connect(self.update_target_size_estimate)

        self.custom_fps.valueChanged.connect(self.update_target_size_estimate)

        self.gif_dither_box = QComboBox()
        self.gif_dither_box.addItem("Sierra 2-4a (smooth)", "sierra2_4a")
        self.gif_dither_box.addItem("Bayer (ordered)", "bayer")
        self.gif_dither_box.addItem("None", "none")
        self.gif_dither_box.setToolTip(
            "Dithering can improve gradients and texture, but may increase "
            "GIF file size. Bayer and no dithering can produce smaller files."
        )
        self.gif_dither_box.currentIndexChanged.connect(
            self.update_quality_size_estimate
        )

        self.auto_resolution_checkbox = QCheckBox(
            "Automatically choose resolution and frame rate"
        )

        self.auto_resolution_checkbox.setChecked(
            True
        )

        self.auto_recommendation_label = QLabel(
            "Select Target file size under Size control "
            "to automatically choose settings."
        )

        self.auto_recommendation_label.setWordWrap(
            True
        )

        self.auto_recommendation_label.setStyleSheet("""
            color: #999999;
            font-size: 11px;
        """)

        self.auto_resolution_checkbox.toggled.connect(
            self.update_automatic_recommendation
        )

        self.auto_resolution_checkbox.toggled.connect(
            self.update_auto_resolution_controls
        )
        self.auto_resolution_checkbox.toggled.connect(
            self.update_target_size_estimate
        )

        # -- Rate Control Settings --

        self.rate_control_box = QComboBox()

        self.rate_control_box.addItem(
            "Quality",
            "quality",
        )

        self.rate_control_box.addItem(
            "Target file size",
            "target_size",
        )

        self.rate_control_box.currentIndexChanged.connect(
            self.update_rate_control_visibility
        )
        self.rate_control_box.currentIndexChanged.connect(
            self.update_target_size_estimate
        )
        self.rate_control_box.currentIndexChanged.connect(
            self.update_automatic_recommendation
        )
        self.rate_control_box.currentIndexChanged.connect(
            self.update_auto_resolution_controls
        )

        # -- Quality Settings --

        # The UI presents higher values as better quality. The FFmpeg backend
        # translates this value for the selected CPU or hardware encoder.
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 51)
        self.quality_slider.setValue(30)
        self.quality_slider.setSingleStep(1)
        self.quality_slider.setPageStep(5)

        self.quality_slider.setToolTip(
            "Higher values produce higher quality and larger files."
        )

        self.quality_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background-color: #3a3a3a;
                height: 6px;
                border-radius: 3px;
            }

            QSlider::sub-page:horizontal {
                background-color: #3b82f6;
                height: 6px;
                border-radius: 3px;
            }

            QSlider::add-page:horizontal {
                background-color: #3a3a3a;
                height: 6px;
                border-radius: 3px;
            }

            QSlider::handle:horizontal {
                background-color: #ffffff;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }

            QSlider::handle:horizontal:hover {
                background-color: #dbeafe;
            }

            QSlider::handle:horizontal:pressed {
                background-color: #3b82f6;
            }
        """)

        self.quality_value = QLabel(str(self.quality_slider.value()))
        self.quality_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quality_value.setMinimumWidth(25)

        self.quality_slider.valueChanged.connect(self.update_quality_display)

        quality_controls_layout = QHBoxLayout()
        quality_controls_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        quality_controls_layout.setSpacing(10)

        quality_controls_layout.addWidget(
            self.quality_slider,
            stretch=1,
        )
        quality_controls_layout.addWidget(self.quality_value)

        self.quality_help = QLabel(
            "1: lowest quality · 30: balanced · 51: best quality"
        )
        self.quality_help.setStyleSheet("""
            color: #999999;
            font-size: 11px;
        """)

        self.quality_size_label = QLabel("Estimated size: —")
        self.quality_size_label.setStyleSheet("""
            color: #999999;
            font-size: 11px;
        """)
        self.quality_size_label.setToolTip(
            "A rough estimate based on the selected codec, resolution, "
            "frame rate and quality. Actual size varies with video content."
        )

        quality_widget_layout = QVBoxLayout()
        quality_widget_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        quality_widget_layout.setSpacing(4)
        quality_widget_layout.addLayout(quality_controls_layout)
        quality_widget_layout.addWidget(self.quality_size_label)
        quality_widget_layout.addWidget(self.quality_help)

        self.quality_widget = QWidget()
        self.quality_widget.setLayout(quality_widget_layout)

        # -- Target File Size Settings --

        self.target_size_box = QDoubleSpinBox()
        self.target_size_box.setRange(1.0, 100000.0)
        self.target_size_box.setValue(100.0)
        self.target_size_box.setDecimals(3)
        self.target_size_box.setSingleStep(10.0)
        self.target_size_box.setSuffix(" MB")

        self.target_size_estimate_label = QLabel(
            "Estimated size for recommended quality: —"
        )

        self.target_size_estimate_label.setStyleSheet("""
            color: #999999;
            font-size: 11px;
        """)

        target_size_layout = QHBoxLayout()
        target_size_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        target_size_layout.setSpacing(10)

        target_size_layout.addWidget(self.target_size_box)

        target_size_layout.addWidget(self.target_size_estimate_label)

        target_size_layout.addStretch()

        self.target_size_widget = QWidget()
        self.target_size_widget.setLayout(target_size_layout)

        self.target_size_box.setToolTip(
            "The finished file will be approximately this size."
        )
        self.target_size_box.valueChanged.connect(
            self.update_automatic_recommendation
        )

        self.target_size_label = QLabel("Target size:")

        self.quality_label = QLabel("Quality:")
        self.gif_dither_label = QLabel("GIF dithering:")

        # Create the format selector before encoder initialization, which
        # refreshes quality estimates during construction.
        self.output_format_box = QComboBox()
        self.output_format_box.addItem("MP4", "mp4")
        self.output_format_box.addItem("GIF", "gif")
        self.output_format_box.addItem("MKV", "mkv")
        self.output_format_box.currentIndexChanged.connect(
            self.update_output_format
        )

        # -- Encoder Settings --

        # Hardware encoders are supplied after background detection finishes.
        self.hardware_encoders = {}

        self.gpu_encoding_checkbox = QCheckBox("Use GPU encoding")
        self.gpu_encoding_checkbox.setEnabled(False)
        self.gpu_encoding_checkbox.setToolTip(
            "Checking for supported hardware encoders."
        )

        self.gpu_status = QLabel("Detecting GPU encoding support...")
        self.gpu_status.setStyleSheet("""
            color: #999999;
            font-size: 11px;
        """)

        self.encoder_box = QComboBox()

        self.encoder_box.currentIndexChanged.connect(
            self.update_target_size_estimate
        )

        self.encoder_box.currentIndexChanged.connect(
            self.update_automatic_recommendation
        )

        self.gpu_encoding_checkbox.toggled.connect(self.update_encoder_options)

        # Start with CPU encoders while detection runs.
        self.update_encoder_options()

        self.preset_box = QComboBox()

        self.preset_box.addItem(
            "Fast",
            "fast",
        )

        self.preset_box.addItem(
            "Medium",
            "medium",
        )

        self.preset_box.addItem(
            "Slow — better compression",
            "slow",
        )

        self.preset_box.setCurrentIndex(1)
        self.preset_box.currentIndexChanged.connect(
            self.update_quality_size_estimate
        )

        # -- Output Settings --

        # Output folder
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setReadOnly(True)
        self.output_folder_edit.setPlaceholderText("Select an output folder")

        self.output_browse_button = QPushButton("Browse")
        self.output_browse_button.clicked.connect(self.browse_output_folder)

        output_folder_layout = QHBoxLayout()
        output_folder_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        output_folder_layout.setSpacing(8)
        output_folder_layout.addWidget(
            self.output_folder_edit,
            stretch=1,
        )
        output_folder_layout.addWidget(
            self.output_browse_button,
        )

        self.output_folder_widget = QWidget()
        self.output_folder_widget.setLayout(output_folder_layout)

        # Output filename
        self.output_filename_edit = QLineEdit()
        self.output_filename_edit.setPlaceholderText(
            f"video_upscaled.{self.output_format_box.currentData()}"
        )

        # Show the complete location that will be passed to FFmpeg.
        self.output_path_preview = QLabel("—")
        self.output_path_preview.setWordWrap(True)
        self.output_path_preview.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.output_path_preview.setStyleSheet("""
            color: #999999;
            font-size: 11px;
        """)

        self.output_folder_edit.textChanged.connect(self.update_output_path_preview)
        self.output_filename_edit.textChanged.connect(self.update_output_path_preview)

        # -- Advanced Settings --

        self.merge_audio_tracks_checkbox = QCheckBox(
            "Merge all audio tracks into one"
        )
        self.merge_audio_tracks_checkbox.toggled.connect(
            self.update_quality_size_estimate
        )
        self.merge_audio_tracks_checkbox.setToolTip(
            "Mixes all audio tracks together into one track, which can help "
            "when sharing the video on platforms that play only one track."
        )

        # -- Settings Form --

        settings_form = QFormLayout()
        self.settings_form = settings_form
        self.section_dividers = []
        settings_form.setVerticalSpacing(20)
        settings_form.addRow(
            "Trim:",
            self.trim_checkbox,
        )

        settings_form.addRow(
            "Start:",
            self.trim_start_box,
        )

        settings_form.addRow(
            "End:",
            self.trim_end_box,
        )

        trim_information_layout = QHBoxLayout()
        trim_information_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        trim_information_layout.setSpacing(10)

        trim_information_layout.addWidget(
            self.trim_duration_label
        )

        trim_information_layout.addStretch()

        trim_information_layout.addWidget(
            self.reset_trim_button
        )

        self.trim_information_widget = QWidget()
        self.trim_information_widget.setLayout(
            trim_information_layout
        )

        settings_form.addRow(
            "",
            self.trim_information_widget,
        )
        settings_form.addRow(self.create_section_divider())
        settings_form.addRow(
            "Resolution:",
            self.resolution_box,
        )

        settings_form.addRow(
            self.custom_resolution_label,
            self.custom_resolution_widget,
        )

        self.resolution_box.currentIndexChanged.connect(
            self.update_custom_resolution_visibility
        )

        self.resolution_box.currentIndexChanged.connect(self.update_target_size_estimate)

        settings_form.addRow(
            "Frame rate:",
            self.fps_box,
        )

        settings_form.addRow(
            self.custom_fps_label,
            self.custom_fps,
        )

        settings_form.addRow(
            self.gif_dither_label,
            self.gif_dither_box,
        )

        settings_form.addRow(
            "",
            self.auto_resolution_checkbox,
        )

        settings_form.addRow(
            "",
            self.auto_recommendation_label,
        )

        settings_form.addRow(self.create_section_divider())
        settings_form.addRow(
            "Size control:",
            self.rate_control_box,
        )

        settings_form.addRow(
            self.quality_label,
            self.quality_widget,
        )

        settings_form.addRow(
            self.target_size_label,
            self.target_size_widget,
        )

        settings_form.addRow(self.create_section_divider())
        settings_form.addRow(
            "",
            self.gpu_encoding_checkbox,
        )

        settings_form.addRow(
            "GPU support:",
            self.gpu_status,
        )

        settings_form.addRow(
            "Encoder:",
            self.encoder_box,
        )

        settings_form.addRow(
            "Encoding speed:",
            self.preset_box,
        )

        settings_form.addRow(self.create_section_divider())
        settings_form.addRow(
            "Output folder:",
            self.output_folder_widget,
        )

        settings_form.addRow(
            "Output filename:",
            self.output_filename_edit,
        )

        settings_form.addRow(
            "Output format:",
            self.output_format_box,
        )

        settings_form.addRow(
            "Output path:",
            self.output_path_preview,
        )

        settings_form.addRow(self.create_section_divider())
        advanced_heading = QLabel("Advanced")
        self.advanced_heading = advanced_heading
        advanced_heading.setStyleSheet("""
            font-weight: bold;
        """)

        settings_form.addRow(
            advanced_heading,
            self.merge_audio_tracks_checkbox,
        )

        # Put the settings form inside its own widget so QScrollArea can
        # manage it. QScrollArea accepts a widget rather than a layout.
        settings_content = QWidget()

        settings_content_layout = QVBoxLayout(settings_content)
        settings_content_layout.setContentsMargins(
            0,
            0,
            10,
            0,
        )

        settings_content_layout.addLayout(settings_form)
        settings_content_layout.addStretch()

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)

        # The settings only need to scroll vertically.
        self.settings_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.settings_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.settings_scroll.setWidget(settings_content)

        # Remove the default border and background so the scroll area blends
        # into the existing settings page.
        self.settings_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }

            QScrollArea > QWidget > QWidget {
                background: transparent;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0px;
            }

            QScrollBar::handle:vertical {
                background-color: #555555;
                min-height: 30px;
                border-radius: 4px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: #6b7280;
            }

            QScrollBar::handle:vertical:pressed {
                background-color: #3b82f6;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
                border: none;
            }

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        self.settings_scroll.viewport().setAutoFillBackground(False)

        # -- Page Actions --

        self.back_button = QPushButton("Back")

        self.back_button.clicked.connect(self.request_back)

        self.back_button.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: bold;
                padding: 8px;
            }
        """)

        self.render_button = QPushButton("Render")

        self.render_button.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: bold;
                padding: 8px;
            }
        """)

        self.render_button.clicked.connect(self.request_render)

        self.queue_button = QPushButton("Add to queue")

        self.queue_button.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: bold;
                padding: 8px;
            }
        """)

        self.queue_button.clicked.connect(self.request_queue)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.hide()

        button_layout = QHBoxLayout()

        button_layout.addWidget(
            self.back_button,
            stretch=1,
        )

        button_layout.addWidget(
            self.queue_button,
            stretch=1,
        )

        button_layout.addWidget(
            self.render_button,
            stretch=1,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 30)
        layout.setSpacing(10)

        layout.addLayout(header_section_layout)

        # The form expands into the available space and becomes scrollable
        # when the window is not tall enough.
        layout.addWidget(
            self.settings_scroll,
            stretch=1,
        )

        # Rendering controls remain visible outside the scrollable section.
        layout.addWidget(self.progress_bar)
        layout.addLayout(button_layout)

        self.update_custom_resolution_visibility()
        self.update_custom_fps_visibility()
        self.update_auto_resolution_controls()
        self.update_rate_control_visibility()
        self.update_format_visibility()
        self.update_quality_display(self.quality_slider.value())
        self.update_target_size_estimate()
        self.update_trim_controls()

    # -- Video and Output Selection --

    def set_video(
        self,
        file_path,
        duration=None,
        source_fps=None,
        source_width=None,
        source_height=None,
        file_size=None,
        thumbnail=None,
    ):
        """Display the input and suggest an output location."""

        new_input_path = Path(file_path)

        video_changed = new_input_path != self.input_path

        self.input_path = new_input_path

        self.video_name.setText(new_input_path.name)

        if thumbnail is not None and not thumbnail.isNull():
            self.video_thumbnail.setPixmap(thumbnail)
        else:
            self.video_thumbnail.clear()
            self.video_thumbnail.setText("No preview")

        self.video_resolution.setText(
            (
                f"{source_width} × {source_height}"
                if source_width is not None and source_height is not None
                else "—"
            )
        )
        self.video_duration_label.setText(
            (
                format_video_duration(duration)
                if duration is not None
                else "—"
            )
        )
        self.video_fps.setText(
            f"{source_fps:.2f} FPS"
            if source_fps is not None
            else "—"
        )
        self.video_file_size.setText(
            f"{file_size / 1_000_000:.2f} MB"
            if file_size is not None
            else "—"
        )

        self.video_duration = duration
        self.source_fps = source_fps
        self.source_width = source_width
        self.source_height = source_height

        if file_size is not None and file_size > 0:
            if file_size >= 1000:
                self.target_size_box.setDecimals(3)
                maximum_target_size_mb = (
                    file_size // 1000 / 1000
                )
            else:
                self.target_size_box.setDecimals(6)
                maximum_target_size_mb = file_size / 1_000_000

            self.target_size_box.setRange(
                min(1.0, maximum_target_size_mb),
                maximum_target_size_mb,
            )
            self.target_size_box.setToolTip(
                "The finished file will be approximately this size. "
                "The target cannot exceed the input file size."
            )

        else:
            self.target_size_box.setRange(1.0, 100000.0)
            self.target_size_box.setToolTip(
                "The finished file will be approximately this size."
            )

        # QDoubleSpinBox displays milliseconds, so round down
        # to avoid placing the end slightly beyond the source.
        if duration is not None and duration > 0:
            displayed_duration = (
                int(float(duration) * 1000)
                / 1000
            )

            self.trim_checkbox.setEnabled(True)

            self.trim_start_box.setMaximum(
                displayed_duration
            )

            self.trim_end_box.setMaximum(
                displayed_duration
            )

            if video_changed:
                self.trim_checkbox.setChecked(False)
                self.trim_start_box.setValue(0.0)
                self.trim_end_box.setValue(
                    displayed_duration
                )

        else:
            self.trim_checkbox.setEnabled(False)
            self.trim_checkbox.setChecked(False)

        # Display the actual dimensions in the Same as source option.
        source_index = self.resolution_box.findData("source")

        if source_index >= 0 and source_width is not None and source_height is not None:
            self.resolution_box.setItemText(
                source_index,
                (f"Same as source  ({source_width} × {source_height})"),
            )

        # Preserve the user's choices when returning to the settings page
        # for the same video, but create defaults for a new video.
        if video_changed or not self.output_folder_edit.text():
            self.output_folder_edit.setText(str(new_input_path.parent))

            self.output_filename_edit.setText(
                f"{new_input_path.stem}_upscaled."
                f"{self.output_format_box.currentData()}"
            )

        self.update_output_path_preview()
        self.update_trim_controls()
        self.update_target_size_estimate()
        self.update_automatic_recommendation()

    def browse_output_folder(self):
        """Ask the user where the rendered video should be saved."""

        starting_folder = self.output_folder_edit.text()

        selected_folder = QFileDialog.getExistingDirectory(
            self,
            "Select output folder",
            starting_folder,
        )

        if selected_folder:
            self.output_folder_edit.setText(selected_folder)

    def update_output_path_preview(self):
        """Display the output path without validating it yet."""

        folder_text = self.output_folder_edit.text().strip()
        filename = self.output_filename_edit.text().strip()

        if not folder_text or not filename:
            self.output_path_preview.setText("—")
            return

        output_path = Path(folder_text) / filename

        self.output_path_preview.setText(str(output_path))

    def create_section_divider(self):
        """Create a short, inset divider between settings sections."""

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet("color: #444444;")

        divider_layout = QHBoxLayout()
        divider_layout.setContentsMargins(14, 7, 14, 7)
        divider_layout.addWidget(divider)

        widget = QWidget()
        widget.setLayout(divider_layout)
        self.section_dividers.append(widget)
        return widget

    def update_output_format(self):
        """Keep a recognized filename extension in sync with the format."""

        filename = self.output_filename_edit.text().strip()
        selected_format = self.output_format_box.currentData()

        if filename and selected_format:
            filename_path = Path(filename)

            if filename_path.suffix.lower() in {".mp4", ".gif", ".mkv"}:
                self.output_filename_edit.setText(
                    f"{filename_path.stem}.{selected_format}"
                )
            elif not filename_path.suffix:
                self.output_filename_edit.setText(
                    f"{filename}.{selected_format}"
                )

        self.output_filename_edit.setPlaceholderText(
            f"video_upscaled.{selected_format}"
        )

        self.update_format_visibility()
        self.update_output_path_preview()
        self.update_quality_display(self.quality_slider.value())
        self.update_target_size_estimate()

    def get_output_path(self):
        """Return a validated output path with the selected format extension."""

        if self.input_path is None:
            raise ValueError("No input video has been selected.")

        folder_text = self.output_folder_edit.text().strip()

        if not folder_text:
            raise ValueError("Select an output folder.")

        output_folder = Path(folder_text)

        if not output_folder.is_dir():
            raise ValueError("The selected output folder does not exist.")

        filename = self.output_filename_edit.text().strip()

        if not filename:
            raise ValueError("Enter an output filename.")

        output_format = self.output_format_box.currentData()
        expected_suffix = f".{output_format}"

        invalid_characters = '<>:"/\\|?*'

        if any(character in filename for character in invalid_characters):
            raise ValueError(
                "The output filename contains a character that Windows does not allow."
            )

        filename_path = Path(filename)

        if not filename_path.suffix:
            filename = f"{filename}{expected_suffix}"

            # Keep the visible filename consistent with the actual one.
            self.output_filename_edit.setText(filename)

        elif filename_path.suffix.lower() in {".mp4", ".gif", ".mkv"}:
            if filename_path.suffix.lower() != expected_suffix:
                filename = f"{filename_path.stem}{expected_suffix}"
                self.output_filename_edit.setText(filename)

        elif filename_path.suffix.lower() != expected_suffix:
            raise ValueError(
                f"The output filename must use the {expected_suffix} extension."
            )

        output_path = output_folder / filename

        if output_path.resolve() == self.input_path.resolve():
            raise ValueError("The output file cannot overwrite the input video.")

        return output_path


    # -- Trim Range --

    @staticmethod
    def format_timecode(seconds):
        """Format seconds as HH:MM:SS.mmm."""

        total_milliseconds = round(
            float(seconds) * 1000
        )

        total_seconds, milliseconds = divmod(
            total_milliseconds,
            1000,
        )

        hours, remainder = divmod(
            total_seconds,
            3600,
        )

        minutes, seconds = divmod(
            remainder,
            60,
        )

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds:02d}."
            f"{milliseconds:03d}"
        )

    def update_trim_controls(
        self,
        _checked=None,
    ):
        """Enable trim inputs only when trimming is selected."""

        trim_enabled = (
            self.trim_checkbox.isChecked()
            and self.video_duration is not None
        )

        self.trim_start_box.setEnabled(
            trim_enabled
        )

        self.trim_end_box.setEnabled(
            trim_enabled
        )

        self.reset_trim_button.setEnabled(
            trim_enabled
        )

        self.update_trim_summary()

    def update_trim_summary(
        self,
        _value=None,
    ):
        """Display the duration of the selected range."""

        if self.video_duration is None:
            self.trim_duration_label.setText(
                "Selected duration: —"
            )
            return

        if self.trim_checkbox.isChecked():
            selected_duration = (
                self.trim_end_box.value()
                - self.trim_start_box.value()
            )

        else:
            selected_duration = (
                self.video_duration
            )

        if selected_duration <= 0:
            self.trim_duration_label.setText(
                "Selected duration: invalid range"
            )

        else:
            timecode = self.format_timecode(
                selected_duration
            )

            self.trim_duration_label.setText(
                f"Selected duration: {timecode}"
            )

        self.update_target_size_estimate()

    def reset_trim_range(self):
        """Select the complete source video."""

        if self.video_duration is None:
            return

        displayed_duration = (
            int(float(self.video_duration) * 1000)
            / 1000
        )

        self.trim_start_box.setValue(0.0)

        self.trim_end_box.setValue(
            displayed_duration
        )

    def get_trim_range(self):
        """Return and validate the selected trim range."""

        if self.video_duration is None:
            raise ValueError(
                "The source video duration is unavailable."
            )

        if not self.trim_checkbox.isChecked():
            return 0.0, None

        trim_start = (
            self.trim_start_box.value()
        )

        trim_end = (
            self.trim_end_box.value()
        )

        if trim_start < 0:
            raise ValueError(
                "The trim start cannot be negative."
            )

        if trim_end <= trim_start:
            raise ValueError(
                "The trim end must be after the trim start."
            )

        if trim_end > self.video_duration:
            raise ValueError(
                "The trim end cannot exceed the video duration."
            )

        return trim_start, trim_end


    # -- Setting Values and Visibility --

    def update_rate_control_visibility(self):
        """Show controls for the selected rate-control mode."""

        target_size_selected = self.rate_control_box.currentData() == "target_size"

        self.rate_control_box.setVisible(True)
        self.quality_label.setVisible(not target_size_selected)
        self.quality_widget.setVisible(not target_size_selected)
        self.quality_size_label.setVisible(True)

        self.target_size_label.setVisible(target_size_selected)
        self.target_size_widget.setVisible(target_size_selected)

    def update_format_visibility(self):
        """Show only settings that apply to the selected output format."""

        is_gif = self.output_format_box.currentData() == "gif"

        self.auto_resolution_checkbox.setVisible(not is_gif)
        self.auto_recommendation_label.setVisible(not is_gif)
        self.gpu_encoding_checkbox.setVisible(not is_gif)
        self.gpu_status.setVisible(not is_gif)
        self.encoder_box.setVisible(not is_gif)
        self.preset_box.setVisible(not is_gif)
        self.merge_audio_tracks_checkbox.setVisible(not is_gif)
        self.advanced_heading.setVisible(not is_gif)
        self.gif_dither_label.setVisible(is_gif)
        self.gif_dither_box.setVisible(is_gif)

        for field in (
            self.gpu_status,
            self.encoder_box,
            self.preset_box,
        ):
            label = self.settings_form.labelForField(field)

            if label is not None:
                label.setVisible(not is_gif)

        for index, divider in enumerate(self.section_dividers):
            divider.setVisible(index < 2 or not is_gif)

        self.update_auto_resolution_controls()
        self.update_rate_control_visibility()

    def update_custom_resolution_visibility(self):
        """Show custom dimensions only when Custom is selected."""

        custom_selected = self.resolution_box.currentData() is None

        self.custom_resolution_label.setVisible(custom_selected)

        self.custom_resolution_widget.setVisible(custom_selected)

    def update_custom_fps_visibility(self):
        """Show the FPS input only when Custom is selected."""

        custom_selected = self.fps_box.currentData() == "custom"

        self.custom_fps_label.setVisible(custom_selected)

        self.custom_fps.setVisible(custom_selected)

    def update_auto_resolution_controls(self):
        """Disable manual resolution and frame-rate controls when automatic."""

        target_size_selected = (
            self.rate_control_box.currentData() == "target_size"
        )
        is_gif = self.output_format_box.currentData() == "gif"
        automatic_selection_active = (
            self.auto_resolution_checkbox.isChecked()
            and target_size_selected
            and not is_gif
        )
        manual_controls_enabled = not automatic_selection_active

        self.auto_resolution_checkbox.setEnabled(
            target_size_selected and not is_gif
        )
        self.resolution_box.setEnabled(manual_controls_enabled)
        self.custom_resolution_label.setEnabled(manual_controls_enabled)
        self.custom_resolution_widget.setEnabled(manual_controls_enabled)

        self.fps_box.setEnabled(manual_controls_enabled)
        self.custom_fps_label.setEnabled(manual_controls_enabled)
        self.custom_fps.setEnabled(manual_controls_enabled)


    def update_automatic_recommendation(
        self,
        _value=None,
    ):
        """Choose suitable resolution and FPS settings for the target size."""

        if self.output_format_box.currentData() == "gif":
            return

        if not self.auto_resolution_checkbox.isChecked():
            self.auto_recommendation_label.setText(
                "Automatic recommendations are disabled."
            )
            return

        if self.rate_control_box.currentData() != "target_size":
            self.auto_recommendation_label.setText(
                "Select Target file size under Size control "
                "to automatically choose settings."
            )
            return

        target_size = self.target_size_box.value()

        if (
            self.video_duration is None
            or self.source_width is None
            or self.source_height is None
            or self.source_fps is None
        ):
            self.auto_recommendation_label.setText(
                "Import a video to calculate recommended settings."
            )
            return

        try:
            trim_start, trim_end = self.get_trim_range()

        except ValueError:
            self.auto_recommendation_label.setText(
                "Select a valid trim range."
            )
            return

        duration = (
            trim_end - trim_start
            if trim_end is not None
            else self.video_duration
        )

        encoder = self.encoder_box.currentData()

        # -- Resolution Candidates --

        resolution_candidates = [
            {
                "data": "source",
                "width": self.source_width,
                "height": self.source_height,
            }
        ]

        seen_resolutions = {
            (
                self.source_width,
                self.source_height,
            )
        }

        for index in range(
            self.resolution_box.count()
        ):
            resolution = (
                self.resolution_box.itemData(index)
            )

            if not isinstance(resolution, tuple):
                continue

            width, height = resolution

            # Automatic presets should never upscale the source.
            if (
                width > self.source_width
                or height > self.source_height
            ):
                continue

            if resolution in seen_resolutions:
                continue

            seen_resolutions.add(resolution)

            resolution_candidates.append({
                "data": resolution,
                "width": width,
                "height": height,
            })

        # -- Frame Rate Candidates --

        fps_candidates = [
            {
                "data": "original",
                "fps": float(self.source_fps),
            }
        ]

        seen_frame_rates = {
            round(float(self.source_fps), 3)
        }

        for index in range(
            self.fps_box.count()
        ):
            fps = self.fps_box.itemData(index)

            if (
                isinstance(fps, bool)
                or not isinstance(fps, (int, float))
            ):
                continue

            fps = float(fps)

            # Automatic presets should never create extra frames.
            if fps > self.source_fps:
                continue

            rounded_fps = round(fps, 3)

            if rounded_fps in seen_frame_rates:
                continue

            seen_frame_rates.add(rounded_fps)

            fps_candidates.append({
                "data": self.fps_box.itemData(index),
                "fps": fps,
            })

        # -- Evaluate Every Combination --

        evaluated_candidates = []

        for resolution in resolution_candidates:
            for frame_rate in fps_candidates:
                estimated_size = (
                    calculate_recommended_target_size_mb(
                        duration=duration,
                        width=resolution["width"],
                        height=resolution["height"],
                        fps=frame_rate["fps"],
                        encoder=encoder,
                    )
                )

                if estimated_size is None:
                    continue

                evaluated_candidates.append({
                    "resolution_data": resolution["data"],
                    "width": resolution["width"],
                    "height": resolution["height"],
                    "fps_data": frame_rate["data"],
                    "fps": frame_rate["fps"],
                    "estimated_size": estimated_size,
                })

        if not evaluated_candidates:
            self.auto_recommendation_label.setText(
                "A recommendation is not available "
                "for the selected encoder."
            )
            return

        suitable_candidates = [
            candidate
            for candidate in evaluated_candidates
            if (
                candidate["estimated_size"] <= target_size
            )
        ]

        recommendation_available = bool(
            suitable_candidates
        )

        if suitable_candidates:
            # Use as much of the target budget as possible, then favor
            # higher frame rates and resolution.
            recommended = max(
                suitable_candidates,
                key=lambda candidate: (
                    candidate["estimated_size"],
                    candidate["fps"],
                    candidate["width"]
                    * candidate["height"],
                ),
            )

        else:
            # No option fits the target; choose the closest estimate.
            recommended = min(
                evaluated_candidates,
                key=lambda candidate: (
                    candidate["estimated_size"],
                    -candidate["fps"],
                    candidate["width"]
                    * candidate["height"],
                ),
            )

        # -- Apply the Selected Combination --

        resolution_index = (
            self.resolution_box.findData(
                recommended["resolution_data"]
            )
        )

        fps_index = self.fps_box.findData(
            recommended["fps_data"]
        )

        self.resolution_box.blockSignals(True)
        self.fps_box.blockSignals(True)

        try:
            if resolution_index >= 0:
                self.resolution_box.setCurrentIndex(
                    resolution_index
                )

            if fps_index >= 0:
                self.fps_box.setCurrentIndex(
                    fps_index
                )

        finally:
            self.resolution_box.blockSignals(False)
            self.fps_box.blockSignals(False)

        self.update_custom_resolution_visibility()
        self.update_custom_fps_visibility()
        self.update_target_size_estimate()

        width = recommended["width"]
        height = recommended["height"]
        fps = recommended["fps"]
        estimated_size = recommended["estimated_size"]

        if recommendation_available:
            self.auto_recommendation_label.setText(
                f"Recommended: {width} × {height} at "
                f"{fps:g} FPS"
            )

        else:
            self.auto_recommendation_label.setText(
                f"The {target_size:g} MB target is below the "
                f"estimated size for recommended quality "
                f"({estimated_size:.2f} MB) at the least demanding "
                f"available setting: {width} × {height} at "
                f"{fps:g} FPS."
            )


    def update_quality_display(self, value):
        """Display the selected video quality or GIF palette size."""

        if self.output_format_box.currentData() == "gif":
            colors = calculate_gif_palette_colors(value)
            self.quality_value.setText(str(colors))
            self.quality_label.setText("Maximum colors:")
            self.quality_help.setText(
                "Fewer colors create smaller GIFs; more colors preserve detail."
            )
            self.quality_slider.setToolTip(
                f"Use up to {colors} colors in the GIF palette. "
                "Higher values preserve more color detail and can increase "
                "file size."
            )

        else:
            self.quality_value.setText(str(value))
            self.quality_label.setText("Quality:")
            self.quality_help.setText(
                "1: lowest quality · 30: balanced · 51: best quality"
            )
            self.quality_slider.setToolTip(
                "Higher values produce higher quality and larger files."
            )

        self.update_quality_size_estimate()

    def update_target_size_estimate(
        self,
        _value=None,
    ):
        """Update the appropriate size estimate for current settings."""

        self.update_quality_size_estimate()

        if self.output_format_box.currentData() == "gif":
            if self.rate_control_box.currentData() == "target_size":
                self.target_size_estimate_label.setText(
                    "Palette colors are reduced to approach the target; "
                    "actual size depends on video content."
                )
                self.target_size_estimate_label.setToolTip(
                    "GIF has no bitrate control. ffupscale reduces the palette "
                    "to aim for the requested size; texture, motion and "
                    "dithering can make the final size differ."
                )
            else:
                self.target_size_estimate_label.setText(
                    "GIF size depends on resolution, frame rate, and content."
                )

            return

        automatic_selection = (
            self.auto_resolution_checkbox.isChecked()
        )
        if automatic_selection:
            estimate_function = calculate_recommended_target_size_mb
            estimate_label = "Estimated size for recommended quality"
        else:
            estimate_function = calculate_minimum_target_size_mb
            estimate_label = "Estimated minimum"

        if self.video_duration is None or self.source_fps is None:
            self.target_size_estimate_label.setText(
                f"{estimate_label}: —"
            )
            return

        try:
            width, height = self.get_resolution()
            trim_start, trim_end = (
                self.get_trim_range()
            )

        except ValueError:
            self.target_size_estimate_label.setText(
                f"{estimate_label}: —"
            )
            return

        effective_duration = (
            trim_end - trim_start
            if trim_end is not None
            else self.video_duration
        )

        selected_fps = self.get_fps()

        effective_fps = selected_fps if selected_fps is not None else self.source_fps

        encoder = self.encoder_box.currentData()

        estimated_size = estimate_function(
            duration=effective_duration,
            width=width,
            height=height,
            fps=effective_fps,
            encoder=encoder,
        )

        if estimated_size is None:
            self.target_size_estimate_label.setText(
                f"{estimate_label}: not available"
            )
            return

        self.target_size_estimate_label.setText(
            f"{estimate_label}: {estimated_size:.2f} MB"
        )

        if automatic_selection:
            tooltip = (
                "This uses the same quality-oriented estimate as automatic "
                "resolution and frame-rate selection. Actual file size and "
                "quality depend on the video content. An encoder's technical "
                "bitrate limit, when enforced, is checked separately at render."
            )
        else:
            tooltip = (
                "This is an estimated practical minimum for the selected "
                "resolution, frame rate and encoder. Actual requirements "
                "depend on video content. Enforced encoder limits are "
                "checked separately at render."
            )
        self.target_size_estimate_label.setToolTip(tooltip)

    def update_quality_size_estimate(self):
        """Show a cached estimate or queue a background sample encode."""

        self.quality_estimate_timer.stop()

        output_format = self.output_format_box.currentData()

        if self.rate_control_box.currentData() != "quality":
            self.cancel_quality_estimate()
            self.quality_size_label.setText("Estimated size: —")
            return

        if (
            self.input_path is None
            or self.video_duration is None
            or self.source_fps is None
        ):
            self.cancel_quality_estimate()
            self.quality_size_label.setText("Estimated size: —")
            return

        try:
            width, height = self.get_resolution()
            trim_start, trim_end = self.get_trim_range()

        except ValueError:
            self.cancel_quality_estimate()
            self.quality_size_label.setText("Estimated size: —")
            return

        selected_end = (
            trim_end
            if trim_end is not None
            else self.video_duration
        )
        selected_duration = selected_end - trim_start

        if selected_duration <= 0:
            self.cancel_quality_estimate()
            self.quality_size_label.setText(
                "Estimated size: unavailable"
            )
            return

        encoder = self.encoder_box.currentData()
        preset = self.preset_box.currentData()
        selected_fps = self.get_fps()
        quality = self.quality_slider.value()
        gif_dither = self.gif_dither_box.currentData()
        estimate_key = (
            output_format,
            str(self.input_path),
            self.video_duration,
            self.source_fps,
            trim_start,
            selected_end,
            width,
            height,
            selected_fps,
            encoder,
            preset,
            self.merge_audio_tracks_checkbox.isChecked(),
            (
                quality
                if output_format == "gif"
                else None
            ),
            (
                gif_dither
                if output_format == "gif"
                else None
            ),
        )
        settings = {
            "input_path": str(self.input_path),
            "output_format": output_format,
            "source_duration": self.video_duration,
            "source_fps": self.source_fps,
            "trim_start": trim_start,
            "trim_end": selected_end,
            "width": width,
            "height": height,
            "quality": quality,
            "fps": selected_fps,
            "gif_dither": gif_dither,
            "encoder": encoder,
            "preset": preset,
            "merge_audio_tracks": (
                self.merge_audio_tracks_checkbox.isChecked()
            ),
        }
        self.current_quality_estimate_key = estimate_key

        cached_estimate = self.quality_estimate_cache.get(
            estimate_key
        )

        if cached_estimate is not None:
            self._cancel_worker_for_different_estimate(estimate_key)
            self.pending_quality_estimate = None
            self.quality_size_label.setToolTip(
                self.quality_estimate_tooltip(output_format)
            )
            self._display_calibrated_quality_estimate(
                cached_estimate[0],
                cached_estimate[1],
                selected_duration,
                width,
                height,
                encoder,
            )
            return

        worker = self.quality_estimate_worker

        if (
            worker is not None
            and worker.estimate_key == estimate_key
            and not worker.cancel_requested.is_set()
        ):
            self.pending_quality_estimate = None
            self.quality_size_label.setText(
                "Estimated size: estimating..."
            )
            return

        self._cancel_worker_for_different_estimate(estimate_key)
        self.pending_quality_estimate = (
            estimate_key,
            settings,
        )
        self.quality_size_label.setText(
            "Estimated size: estimating..."
        )
        self.quality_estimate_timer.start()

    def _display_calibrated_quality_estimate(
        self,
        reference_size_mb,
        reference_quality,
        duration,
        width,
        height,
        encoder,
    ):
        """Apply the cached sample calibration to the current slider value."""

        if self.output_format_box.currentData() == "gif":
            self.display_quality_estimated_size(reference_size_mb)
            return

        effective_fps = self.get_fps()

        if effective_fps is None:
            effective_fps = self.source_fps

        reference_model_size = calculate_estimated_quality_size_mb(
            duration=duration,
            width=width,
            height=height,
            fps=effective_fps,
            encoder=encoder,
            quality=reference_quality,
        )
        current_model_size = calculate_estimated_quality_size_mb(
            duration=duration,
            width=width,
            height=height,
            fps=effective_fps,
            encoder=encoder,
            quality=self.quality_slider.value(),
        )

        if (
            reference_model_size is None
            or current_model_size is None
            or reference_model_size <= 0
        ):
            self.quality_size_label.setText(
                "Estimated size: unavailable"
            )
            return

        estimated_size = (
            reference_size_mb
            * current_model_size
            / reference_model_size
        )

        self.display_quality_estimated_size(estimated_size)

    def display_quality_estimated_size(self, estimated_size):
        """Display a byte-size estimate using the app's standard units."""

        if estimated_size >= 1000:
            formatted_size = f"{estimated_size / 1000:.2f} GB"

        else:
            formatted_size = f"{estimated_size:.1f} MB"

        self.quality_size_label.setText(
            f"Estimated size: {formatted_size}"
        )

    @staticmethod
    def quality_estimate_tooltip(output_format):
        """Explain the source and limitations of the sample-based estimate."""

        if output_format == "gif":
            return (
                "Estimated by encoding short GIF samples from the selected "
                "trim range with the chosen palette and dithering. GIF size "
                "varies with motion and content, so the final size may differ."
            )

        return (
            "Estimated by encoding short samples from this video. "
            "Actual size may vary with scenes not sampled."
        )

    def _cancel_worker_for_different_estimate(self, estimate_key):
        worker = self.quality_estimate_worker

        if (
            worker is not None
            and worker.isRunning()
            and worker.estimate_key != estimate_key
        ):
            self.quality_estimate_generation += 1
            worker.cancel()

    def start_quality_estimate(self):
        """Start the newest queued estimate when no older worker is running."""

        if self.quality_estimate_worker is not None:
            if self.quality_estimate_worker.isRunning():
                return

            self.quality_estimate_worker.deleteLater()
            self.quality_estimate_worker = None

        if self.pending_quality_estimate is None:
            return

        estimate_key, settings = self.pending_quality_estimate
        self.pending_quality_estimate = None
        self.quality_estimate_generation += 1

        worker = QualityEstimateWorker(
            generation=self.quality_estimate_generation,
            estimate_key=estimate_key,
            settings=settings,
            parent=self,
        )
        worker.estimate_ready.connect(
            self.handle_quality_estimate_ready
        )
        worker.estimate_failed.connect(
            self.handle_quality_estimate_failed
        )
        worker.finished.connect(
            self.handle_quality_estimate_finished
        )

        self.quality_estimate_worker = worker
        worker.start()

    def handle_quality_estimate_ready(
        self,
        generation,
        estimate_key,
        reference_quality,
        estimated_size,
    ):
        """Cache a sample result and display it if it is still current."""

        self.quality_estimate_cache[estimate_key] = (
            estimated_size,
            reference_quality,
        )

        if len(self.quality_estimate_cache) > 8:
            oldest_key = next(iter(self.quality_estimate_cache))
            self.quality_estimate_cache.pop(oldest_key)

        if (
            generation != self.quality_estimate_generation
            or estimate_key != self.current_quality_estimate_key
        ):
            return

        try:
            width, height = self.get_resolution()
            trim_start, trim_end = self.get_trim_range()

        except ValueError:
            return

        duration = (
            trim_end - trim_start
            if trim_end is not None
            else self.video_duration - trim_start
        )
        self.quality_size_label.setToolTip(
            self.quality_estimate_tooltip(estimate_key[0])
        )
        self._display_calibrated_quality_estimate(
            estimated_size,
            reference_quality,
            duration,
            width,
            height,
            self.encoder_box.currentData(),
        )

    def handle_quality_estimate_failed(
        self,
        generation,
        estimate_key,
        error_message,
    ):
        """Report sample-encoding failures without blocking settings use."""

        if (
            generation != self.quality_estimate_generation
            or estimate_key != self.current_quality_estimate_key
        ):
            return

        self.quality_size_label.setText(
            "Estimated size: unavailable"
        )
        self.quality_size_label.setToolTip(
            f"Could not estimate output size:\n{error_message}"
        )

    def handle_quality_estimate_finished(self):
        """Release a finished worker and start any newer pending estimate."""

        worker = self.sender()

        if worker is not self.quality_estimate_worker:
            return

        if (
            self.current_quality_estimate_key == worker.estimate_key
            and not worker.result_emitted
        ):
            self.quality_size_label.setText(
                "Estimated size: unavailable"
            )
            self.quality_size_label.setToolTip(
                "The sample estimate ended before returning a result. "
                "Check that FFmpeg can read and encode this video."
            )

        self.quality_estimate_worker = None
        worker.deleteLater()

        if (
            self.pending_quality_estimate is not None
            and not self.quality_estimate_timer.isActive()
        ):
            self.quality_estimate_timer.start(0)

    def cancel_quality_estimate(self):
        """Discard pending work and invalidate any result already in flight."""

        self.quality_estimate_timer.stop()
        self.pending_quality_estimate = None
        self.current_quality_estimate_key = None
        self.quality_estimate_generation += 1

        if self.quality_estimate_worker is not None:
            self.quality_estimate_worker.cancel()

    def request_back(self):
        """Stop background sampling before leaving the settings page."""

        self.cancel_quality_estimate()
        self.back_requested.emit()

    def shutdown_quality_estimate(self):
        """Stop and join the estimator before the application exits."""

        self.cancel_quality_estimate()
        worker = self.quality_estimate_worker

        if worker is not None and worker.isRunning():
            worker.wait()

    def get_fps(self):
        """Return None to preserve FPS, or the selected numeric value."""

        selected_fps = self.fps_box.currentData()

        if selected_fps == "original":
            return None

        if selected_fps == "custom":
            return self.custom_fps.value()

        return selected_fps

    def get_resolution(self):
        """Return validated output dimensions."""

        selected_resolution = self.resolution_box.currentData()

        if selected_resolution == "source":
            if self.source_width is None or self.source_height is None:
                raise ValueError("The source resolution is not available.")

            return (
                self.source_width,
                self.source_height,
            )

        if selected_resolution is not None:
            return selected_resolution

        # None represents the Custom option.
        width = self.custom_width.value()
        height = self.custom_height.value()

        if width % 2 != 0 or height % 2 != 0:
            raise ValueError("Width and height must both be even numbers.")

        return width, height

    def get_settings(self):
        """Build the settings dictionary consumed by the FFmpeg backend."""

        width, height = self.get_resolution()

        trim_start, trim_end = (
            self.get_trim_range()
        )

        rate_control = self.rate_control_box.currentData()

        target_size_mb = None

        if rate_control == "target_size":
            target_size_mb = self.target_size_box.value()

            if target_size_mb <= 0:
                raise ValueError("Target file size must be greater than zero.")

        return {
            "resolution": (width, height),
            "fps": self.get_fps(),
            "output_format": self.output_format_box.currentData(),
            "rate_control": rate_control,
            "quality": self.quality_slider.value(),
            "target_size_mb": target_size_mb,
            "gif_dither": self.gif_dither_box.currentData(),
            "encoder": self.encoder_box.currentData(),
            "preset": self.preset_box.currentData(),
            "output_path": self.get_output_path(),
            "trim_start": trim_start,
            "trim_end": trim_end,
            "merge_audio_tracks": (
                self.merge_audio_tracks_checkbox.isChecked()
                and self.output_format_box.currentData() != "gif"
            ),
        }

    # -- Render Requests and Progress --

    def request_render(self):
        """Treat the primary button as Render or Cancel based on page state."""

        if self.is_rendering:
            self.cancel_requested.emit()
            return

        try:
            settings = self.get_settings()
            self.cancel_quality_estimate()
            self.quality_size_label.setText("Estimated size: —")
            self.render_requested.emit(settings)

        except ValueError as error:
            QMessageBox.warning(
                self,
                "Invalid settings",
                str(error),
            )

    def request_queue(self):
        """Validate the settings and request a new queued job."""

        if self.is_rendering:
            return

        try:
            settings = self.get_settings()
            self.cancel_quality_estimate()
            self.quality_size_label.setText("Estimated size: —")
            self.queue_requested.emit(settings)

        except ValueError as error:
            QMessageBox.warning(
                self,
                "Invalid settings",
                str(error),
            )

    def set_rendering(self, rendering):
        """Update controls when an FFmpeg process starts or stops."""

        self.is_rendering = rendering
        self.back_button.setEnabled(not rendering)
        self.queue_button.setEnabled(not rendering)

        if rendering:
            self.render_button.setText("Cancel")
            self.render_button.setEnabled(True)

            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p%")
            self.progress_bar.show()

        else:
            self.render_button.setText("Render")
            self.render_button.setEnabled(True)
            self.progress_bar.setFormat("%p%")

    def set_cancelling(self):
        """Prevent repeated cancellation requests while FFmpeg is stopping."""

        self.render_button.setText("Cancelling...")
        self.render_button.setEnabled(False)

    def set_progress(self, percentage, remaining_time_text=None):
        """Update render progress and its estimated remaining time."""

        percentage = max(0, min(100, int(percentage)))
        self.progress_bar.setValue(percentage)
        if self.is_rendering:
            remaining_time_text = (
                remaining_time_text or "Estimating remaining time..."
            )
            self.progress_bar.setFormat(
                f"%p% · {remaining_time_text}"
            )

    # -- Hardware Encoder Options --

    def set_hardware_encoders(self, encoders):
        """Store detected hardware encoders and update the GPU controls."""

        self.hardware_encoders = encoders

        if not encoders:
            self.gpu_encoding_checkbox.setChecked(False)
            self.gpu_encoding_checkbox.setEnabled(False)
            self.gpu_encoding_checkbox.setToolTip("No usable GPU encoder was detected.")
            self.gpu_status.setText("No supported GPU encoder detected")

        else:
            vendor_names = {
                "nvidia": "NVIDIA",
                "amd": "AMD",
                "intel": "Intel",
            }

            detected_vendors = [
                vendor_names.get(vendor, vendor.title()) for vendor in encoders
            ]

            vendor_text = ", ".join(detected_vendors)

            self.gpu_encoding_checkbox.setEnabled(True)
            self.gpu_encoding_checkbox.setToolTip(
                f"Use the detected {vendor_text} GPU encoder."
            )
            self.gpu_status.setText(f"{vendor_text} hardware encoding available")

        self.update_encoder_options()

    def update_encoder_options(self):
        """Show CPU or detected hardware encoders."""

        previous_encoder = self.encoder_box.currentData()

        # Try to preserve whether the user selected H.264 or H.265.
        if previous_encoder in {
            "libx265",
            "hevc_nvenc",
            "hevc_amf",
            "hevc_qsv",
        }:
            previous_codec = "h265"
        else:
            previous_codec = "h264"

        self.encoder_box.blockSignals(True)
        self.encoder_box.clear()

        use_gpu = self.gpu_encoding_checkbox.isChecked() and bool(
            self.hardware_encoders
        )

        if use_gpu:
            vendor_names = {
                "nvidia": "NVIDIA NVENC",
                "amd": "AMD AMF",
                "intel": "Intel Quick Sync",
            }

            for vendor, codecs in self.hardware_encoders.items():
                vendor_label = vendor_names.get(
                    vendor,
                    vendor.title(),
                )

                if "h264" in codecs:
                    self.encoder_box.addItem(
                        f"H.264 — {vendor_label}",
                        codecs["h264"],
                    )

                if "h265" in codecs:
                    self.encoder_box.addItem(
                        f"H.265 — {vendor_label}",
                        codecs["h265"],
                    )

        else:
            self.encoder_box.addItem(
                "H.264 — CPU, best compatibility",
                "libx264",
            )

        # Restore the previously selected codec where possible.
        for index in range(self.encoder_box.count()):
            encoder = self.encoder_box.itemData(index)

            encoder_codec = (
                "h265"
                if encoder
                in {
                    "libx265",
                    "hevc_nvenc",
                    "hevc_amf",
                    "hevc_qsv",
                }
                else "h264"
            )

            if encoder_codec == previous_codec:
                self.encoder_box.setCurrentIndex(index)
                break

        self.encoder_box.blockSignals(False)
        self.update_target_size_estimate()
