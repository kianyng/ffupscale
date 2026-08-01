from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QSlider,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QCheckBox,
)

from ffmpeg_runner import (
    calculate_minimum_target_size_mb,
)


# -- Settings Page --

class SettingsPage(QWidget):
    """Collect encoding settings and report user actions to MainWindow."""

    # MainWindow owns navigation and FFmpeg, so this page communicates by signal.
    back_requested = pyqtSignal()
    render_requested = pyqtSignal(dict)
    cancel_requested = pyqtSignal()
    queue_requested = pyqtSignal(dict)

    def __init__(self):
        super().__init__()

        # -- Page State --

        self.is_rendering = False
        self.input_path = None
        self.video_duration = None
        self.source_fps = None

        # -- Page Header --

        title = QLabel("Upscale settings")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
        """)

        self.video_name = QLabel("No video selected")
        self.video_name.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # -- Resolution Settings --

        self.resolution_box = QComboBox()
        # Item data holds the actual dimensions used by FFmpeg.
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

        self.custom_width.valueChanged.connect(
            self.update_minimum_target_size
        )

        self.custom_height.valueChanged.connect(
            self.update_minimum_target_size
        )

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

        self.fps_box.currentIndexChanged.connect(
            self.update_custom_fps_visibility
        )

        self.fps_box.currentIndexChanged.connect(
            self.update_minimum_target_size
        )

        self.custom_fps.valueChanged.connect(
            self.update_minimum_target_size
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

        # -- Quality Settings --

        # The UI presents higher values as better quality. The FFmpeg backend
        # translates this value for the selected CPU or hardware encoder.
        self.quality_slider = QSlider(
            Qt.Orientation.Horizontal
        )
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

        self.quality_value = QLabel(
            str(self.quality_slider.value())
        )
        self.quality_value.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.quality_value.setMinimumWidth(25)

        self.quality_slider.valueChanged.connect(
            self.update_quality_display
        )

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
        quality_controls_layout.addWidget(
            self.quality_value
        )

        quality_help = QLabel(
            "1: lowest quality · 30: balanced · 51: best quality"
        )
        quality_help.setStyleSheet("""
            color: #999999;
            font-size: 11px;
        """)

        quality_widget_layout = QVBoxLayout()
        quality_widget_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        quality_widget_layout.setSpacing(4)
        quality_widget_layout.addLayout(
            quality_controls_layout
        )
        quality_widget_layout.addWidget(
            quality_help
        )

        self.quality_widget = QWidget()
        self.quality_widget.setLayout(
            quality_widget_layout
        )

        # -- Target File Size Settings --

        self.target_size_box = QDoubleSpinBox()
        self.target_size_box.setRange(1.0, 100000.0)
        self.target_size_box.setValue(100.0)
        self.target_size_box.setDecimals(1)
        self.target_size_box.setSingleStep(10.0)
        self.target_size_box.setSuffix(" MB")

        self.minimum_size_label = QLabel(
            "Estimated minimum: —"
        )

        self.minimum_size_label.setStyleSheet("""
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

        target_size_layout.addWidget(
            self.target_size_box
        )

        target_size_layout.addWidget(
            self.minimum_size_label
        )

        target_size_layout.addStretch()

        self.target_size_widget = QWidget()
        self.target_size_widget.setLayout(
            target_size_layout
        )

        self.target_size_box.setToolTip(
            "The finished file will be approximately this size."
        )

        self.target_size_label = QLabel(
            "Target size:"
        )

        self.quality_label = QLabel(
            "Quality:"
        )

        # -- Encoder Settings --

        # Hardware encoders are supplied after background detection finishes.
        self.hardware_encoders = {}

        self.gpu_encoding_checkbox = QCheckBox(
            "Use GPU encoding"
        )
        self.gpu_encoding_checkbox.setEnabled(False)
        self.gpu_encoding_checkbox.setToolTip(
            "Checking for supported hardware encoders."
        )

        self.gpu_status = QLabel(
            "Detecting GPU encoding support..."
        )
        self.gpu_status.setStyleSheet("""
            color: #999999;
            font-size: 11px;
        """)

        self.encoder_box = QComboBox()

        self.encoder_box.currentIndexChanged.connect(
            self.update_minimum_target_size
        )

        self.gpu_encoding_checkbox.toggled.connect(
            self.update_encoder_options
        )

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

        # -- Output Settings --

        # Output folder
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setReadOnly(True)
        self.output_folder_edit.setPlaceholderText(
            "Select an output folder"
        )

        self.output_browse_button = QPushButton(
            "Browse"
        )
        self.output_browse_button.clicked.connect(
            self.browse_output_folder
        )

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
        self.output_folder_widget.setLayout(
            output_folder_layout
        )

        # Output filename
        self.output_filename_edit = QLineEdit()
        self.output_filename_edit.setPlaceholderText(
            "video_upscaled.mp4"
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

        self.output_folder_edit.textChanged.connect(
            self.update_output_path_preview
        )
        self.output_filename_edit.textChanged.connect(
            self.update_output_path_preview
        )

        # -- Settings Form --

        settings_form = QFormLayout()
        settings_form.setVerticalSpacing(20)
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

        self.resolution_box.currentIndexChanged.connect(
            self.update_minimum_target_size
        )

        settings_form.addRow(
            "Frame rate:",
            self.fps_box,
        )

        settings_form.addRow(
            self.custom_fps_label,
            self.custom_fps,
        )

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

        settings_form.addRow(
            "Output folder:",
            self.output_folder_widget,
        )

        settings_form.addRow(
            "Output filename:",
            self.output_filename_edit,
        )

        settings_form.addRow(
            "Output path:",
            self.output_path_preview,
        )

        # Put the settings form inside its own widget so QScrollArea can
        # manage it. QScrollArea accepts a widget rather than a layout.
        settings_content = QWidget()

        settings_content_layout = QVBoxLayout(
            settings_content
        )
        settings_content_layout.setContentsMargins(
            0,
            0,
            10,
            0,
        )

        settings_content_layout.addLayout(
            settings_form
        )
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

        self.settings_scroll.setWidget(
            settings_content
        )

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

        self.settings_scroll.viewport().setAutoFillBackground(
            False
        )

        # -- Page Actions --

        self.back_button = QPushButton("Back")

        self.back_button.clicked.connect(self.back_requested.emit)

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

        self.queue_button = QPushButton(
            "Add to queue"
        )

        self.queue_button.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: bold;
                padding: 8px;
            }
        """)

        self.queue_button.clicked.connect(
            self.request_queue
        )

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
        layout.setSpacing(20)

        layout.addWidget(title)
        layout.addWidget(self.video_name)

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
        self.update_rate_control_visibility()

    # -- Video and Output Selection --

    def set_video(
        self,
        file_path,
        duration=None,
        source_fps=None,
    ):
        """Display the input and suggest an output location."""

        new_input_path = Path(file_path)
        video_changed = (
            new_input_path != self.input_path
        )

        self.input_path = new_input_path
        self.video_name.setText(
            new_input_path.name
        )

        self.video_duration = duration
        self.source_fps = source_fps

        # Preserve the user's choices when returning to the settings page for
        # the same video, but create fresh defaults for a newly selected video.
        if (
            video_changed
            or not self.output_folder_edit.text()
        ):
            self.output_folder_edit.setText(
                str(new_input_path.parent)
            )

            self.output_filename_edit.setText(
                f"{new_input_path.stem}_upscaled.mp4"
            )

        self.update_output_path_preview()
        self.update_minimum_target_size()

    def browse_output_folder(self):
        """Ask the user where the rendered video should be saved."""

        starting_folder = (
            self.output_folder_edit.text()
        )

        selected_folder = (
            QFileDialog.getExistingDirectory(
                self,
                "Select output folder",
                starting_folder,
            )
        )

        if selected_folder:
            self.output_folder_edit.setText(
                selected_folder
            )

    def update_output_path_preview(self):
        """Display the output path without validating it yet."""

        folder_text = (
            self.output_folder_edit.text().strip()
        )
        filename = (
            self.output_filename_edit.text().strip()
        )

        if not folder_text or not filename:
            self.output_path_preview.setText("—")
            return

        output_path = (
            Path(folder_text) / filename
        )

        self.output_path_preview.setText(
            str(output_path)
        )

    def get_output_path(self):
        """Return a validated MP4 output path."""

        if self.input_path is None:
            raise ValueError(
                "No input video has been selected."
            )

        folder_text = (
            self.output_folder_edit.text().strip()
        )

        if not folder_text:
            raise ValueError(
                "Select an output folder."
            )

        output_folder = Path(folder_text)

        if not output_folder.is_dir():
            raise ValueError(
                "The selected output folder does not exist."
            )

        filename = (
            self.output_filename_edit.text().strip()
        )

        if not filename:
            raise ValueError(
                "Enter an output filename."
            )

        invalid_characters = '<>:"/\\|?*'

        if any(
            character in filename
            for character in invalid_characters
        ):
            raise ValueError(
                "The output filename contains a character "
                "that Windows does not allow."
            )

        filename_path = Path(filename)

        if not filename_path.suffix:
            filename = f"{filename}.mp4"

            # Keep the visible filename consistent with the actual one.
            self.output_filename_edit.setText(
                filename
            )

        elif filename_path.suffix.lower() != ".mp4":
            raise ValueError(
                "The output filename must use the .mp4 extension."
            )

        output_path = output_folder / filename

        if (
            output_path.resolve()
            == self.input_path.resolve()
        ):
            raise ValueError(
                "The output file cannot overwrite the input video."
            )

        if output_path.exists():
            raise ValueError(
                "A file already exists at the selected output path. "
                "Choose another filename."
            )

        return output_path

    # -- Setting Values and Visibility --

    def update_rate_control_visibility(self):
        """Show controls for the selected rate-control mode."""

        target_size_selected = (
            self.rate_control_box.currentData()
            == "target_size"
        )

        self.quality_label.setVisible(
            not target_size_selected
        )
        self.quality_widget.setVisible(
            not target_size_selected
        )

        self.target_size_label.setVisible(
            target_size_selected
        )
        self.target_size_widget.setVisible(
            target_size_selected
        )

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

    def update_quality_display(self, value):
        """Display the currently selected CRF value."""

        self.quality_value.setText(
            str(value)
        )


    def update_minimum_target_size(
        self,
        _value=None,
    ):
        """Update the estimated minimum for the current settings."""

        if (
            self.video_duration is None
            or self.source_fps is None
        ):
            self.minimum_size_label.setText(
                "Estimated minimum: —"
            )
            return

        try:
            width, height = self.get_resolution()

        except ValueError:
            self.minimum_size_label.setText(
                "Estimated minimum: —"
            )
            return

        selected_fps = self.get_fps()

        effective_fps = (
            selected_fps
            if selected_fps is not None
            else self.source_fps
        )

        encoder = self.encoder_box.currentData()

        minimum_size = (
            calculate_minimum_target_size_mb(
                duration=self.video_duration,
                width=width,
                height=height,
                fps=effective_fps,
                encoder=encoder,
            )
        )

        if minimum_size is None:
            self.minimum_size_label.setText(
                "Estimated minimum: not available"
            )
            return

        self.minimum_size_label.setText(
            f"Estimated minimum: {minimum_size:.1f} MB"
        )


    def get_fps(self):
        """Return None to preserve FPS, or the selected numeric value."""

        selected_fps = self.fps_box.currentData()

        if selected_fps == "original":
            return None

        if selected_fps == "custom":
            return self.custom_fps.value()

        return selected_fps

    def get_resolution(self):
        """Return validated output dimensions from the preset or custom inputs."""

        preset_resolution = self.resolution_box.currentData()

        if preset_resolution is not None:
            return preset_resolution

        width = self.custom_width.value()
        height = self.custom_height.value()

        if width % 2 != 0 or height % 2 != 0:
            raise ValueError("Width and height must both be even numbers.")

        return width, height

    def get_settings(self):
        """Build the settings dictionary consumed by the FFmpeg backend."""

        width, height = self.get_resolution()

        rate_control = (
            self.rate_control_box.currentData()
        )

        target_size_mb = None

        if rate_control == "target_size":
            target_size_mb = (
                self.target_size_box.value()
            )

            if target_size_mb <= 0:
                raise ValueError(
                    "Target file size must be greater than zero."
                )

        return {
            "resolution": (width, height),
            "fps": self.get_fps(),
            "rate_control": rate_control,
            "quality": self.quality_slider.value(),
            "target_size_mb": target_size_mb,
            "encoder": self.encoder_box.currentData(),
            "preset": self.preset_box.currentData(),
            "output_path": self.get_output_path(),
        }

    # -- Render Requests and Progress --

    def request_render(self):
        """Treat the primary button as Render or Cancel based on page state."""

        if self.is_rendering:
            self.cancel_requested.emit()
            return

        try:
            settings = self.get_settings()
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
        self.back_button.setEnabled(
            not rendering
        )
        self.queue_button.setEnabled(
            not rendering
        )

        if rendering:
            self.render_button.setText(
                "Cancel"
            )
            self.render_button.setEnabled(True)

            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p%")
            self.progress_bar.show()

        else:
            self.render_button.setText(
                "Render"
            )
            self.render_button.setEnabled(True)

    def set_cancelling(self):
        """Prevent repeated cancellation requests while FFmpeg is stopping."""

        self.render_button.setText("Cancelling...")
        self.render_button.setEnabled(False)

    def set_progress(self, percentage):
        """Clamp FFmpeg progress to the range accepted by QProgressBar."""

        percentage = max(0, min(100, int(percentage)))
        self.progress_bar.setValue(percentage)

    # -- Hardware Encoder Options --

    def set_hardware_encoders(self, encoders):
        """Store detected hardware encoders and update the GPU controls."""

        self.hardware_encoders = encoders

        if not encoders:
            self.gpu_encoding_checkbox.setChecked(
                False
            )
            self.gpu_encoding_checkbox.setEnabled(
                False
            )
            self.gpu_encoding_checkbox.setToolTip(
                "No usable GPU encoder was detected."
            )
            self.gpu_status.setText(
                "No supported GPU encoder detected"
            )

        else:
            vendor_names = {
                "nvidia": "NVIDIA",
                "amd": "AMD",
                "intel": "Intel",
            }

            detected_vendors = [
                vendor_names.get(vendor, vendor.title())
                for vendor in encoders
            ]

            vendor_text = ", ".join(detected_vendors)

            self.gpu_encoding_checkbox.setEnabled(
                True
            )
            self.gpu_encoding_checkbox.setToolTip(
                f"Use the detected {vendor_text} GPU encoder."
            )
            self.gpu_status.setText(
                f"{vendor_text} hardware encoding available"
            )

        self.update_encoder_options()


    def update_encoder_options(self):
        """Show CPU or detected hardware encoders."""

        previous_encoder = (
            self.encoder_box.currentData()
        )

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

        use_gpu = (
            self.gpu_encoding_checkbox.isChecked()
            and bool(self.hardware_encoders)
        )

        if use_gpu:
            vendor_names = {
                "nvidia": "NVIDIA NVENC",
                "amd": "AMD AMF",
                "intel": "Intel Quick Sync",
            }

            for vendor, codecs in (
                self.hardware_encoders.items()
            ):
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
        for index in range(
            self.encoder_box.count()
        ):
            encoder = self.encoder_box.itemData(index)

            encoder_codec = (
                "h265"
                if encoder in {
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
        self.update_minimum_target_size()
