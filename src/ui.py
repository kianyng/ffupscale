import json
import subprocess
from pathlib import Path

from PyQt6.QtCore import QProcess, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ffmpeg_runner import (
    build_upscale_command,
    create_output_path,
)
from settings_page import SettingsPage

from ffmpeg_manager import (
    find_ffmpeg,
    find_ffprobe,
)

# Prevent FFmpeg and FFprobe from opening console windows on Windows.
SUBPROCESS_FLAGS = getattr(
    subprocess,
    "CREATE_NO_WINDOW",
    0,
)

# Video inspection helpers


def read_video_properties(file_path):
    """Use FFprobe to read properties from the selected video."""

    ffprobe_path = find_ffprobe()

    if ffprobe_path is None:
        raise FileNotFoundError(
            "FFprobe could not be found. Make sure FFmpeg is installed "
            "and added to PATH."
        )

    command = [
        ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        ("stream=width,height,avg_frame_rate,codec_name:" "format=duration,size"),
        "-of",
        "json",
        file_path,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        creationflags=SUBPROCESS_FLAGS,
    )

    data = json.loads(result.stdout)

    if not data.get("streams"):
        raise ValueError("The selected file does not contain a video stream.")

    video_stream = data["streams"][0]
    video_format = data["format"]

    frame_rate_fraction = video_stream.get("avg_frame_rate", "0/1")
    numerator, denominator = frame_rate_fraction.split("/")

    if float(denominator) != 0:
        frame_rate = float(numerator) / float(denominator)
    else:
        frame_rate = 0

    return {
        "width": video_stream.get("width", 0),
        "height": video_stream.get("height", 0),
        "fps": frame_rate,
        "duration": float(video_format.get("duration", 0)),
        "codec": video_stream.get("codec_name", "Unknown"),
        "format": Path(file_path).suffix.removeprefix(".").upper(),
        "file_size": int(video_format.get("size", 0)),
    }


def format_duration(duration_seconds):
    """Convert a duration in seconds into hours, minutes and seconds."""

    total_seconds = round(duration_seconds)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02}:{seconds:02}"

    return f"{minutes}:{seconds:02}"


def create_video_thumbnail(file_path):
    """Extract a PNG frame one second into the selected video."""

    ffmpeg_path = find_ffmpeg()

    if ffmpeg_path is None:
        raise FileNotFoundError("FFmpeg could not be found.")

    command = [
        ffmpeg_path,
        "-v",
        "error",
        "-ss",
        "1",
        "-i",
        file_path,
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        creationflags=SUBPROCESS_FLAGS,
    )

    if result.returncode != 0 or not result.stdout:
        ffmpeg_error = result.stderr.decode(errors="replace")

        raise ValueError(
            f"FFmpeg could not create a video thumbnail:\n" f"{ffmpeg_error}"
        )

    thumbnail = QPixmap()

    if not thumbnail.loadFromData(result.stdout):
        raise ValueError("The thumbnail image could not be loaded.")

    return thumbnail


# User interface


class DropArea(QFrame):
    """Clickable drag-and-drop target that previews the selected video."""

    file_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.setObjectName("dropArea")
        self.setAcceptDrops(True)

        # Keep a generous drop target before selection. Once a thumbnail is
        # available, the frame is resized to match the video's aspect ratio.
        self.empty_minimum_height = 250
        self.thumbnail_padding = 12
        self.setMinimumHeight(self.empty_minimum_height)

        size_policy = QSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.setSizePolicy(size_policy)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.label = QLabel("Drag file or click to browse")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.thumbnail = None

        # This means the label will not intercept mouse clicks.
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self.thumbnail_padding,
            self.thumbnail_padding,
            self.thumbnail_padding,
            self.thumbnail_padding,
        )
        layout.addWidget(self.label)

        self.setStyleSheet("""
            QFrame#dropArea {
                border: 2px dashed #999999;
                border-radius: 20px;
                background-color: #242424;
            }

            QFrame#dropArea:hover {
                border-color: #3b82f6;
                background-color: #292929;
            }

            QFrame#dropArea QLabel {
                border: none;
                background: transparent;
                color: white;
                font-size: 20px;
            }
        """)

    def mousePressEvent(self, event):
        """Open the file picker when the drop area is clicked."""

        if event.button() == Qt.MouseButton.LeftButton:
            self.open_file_browser()

        super().mousePressEvent(event)

    def open_file_browser(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a video",
            "",
            ("Video files (*.mp4 *.mov *.mkv *.avi *.webm);;" "All files (*.*)"),
        )

        if file_path:
            self.select_file(file_path)

    def dragEnterEvent(self, event):
        """Accept drag operations that contain local file URLs."""

        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Use the first valid local file in a drop operation."""

        urls = event.mimeData().urls()

        if not urls:
            event.ignore()
            return

        file_path = urls[0].toLocalFile()

        if Path(file_path).is_file():
            self.select_file(file_path)
            event.acceptProposedAction()
        else:
            event.ignore()

    def select_file(self, file_path):
        """Generate a thumbnail, then notify MainWindow of the selection."""

        self.label.setText("Loading video...")

        QApplication.processEvents()

        try:
            self.thumbnail = create_video_thumbnail(file_path)
            self.update_thumbnail_height()
            self.display_thumbnail()

        except (FileNotFoundError, ValueError) as error:
            self.thumbnail = None

            # Undo a previous thumbnail's fixed height if the new preview
            # could not be generated.
            self.setMinimumHeight(self.empty_minimum_height)
            self.setMaximumHeight(16777215)

            self.label.setText(Path(file_path).name)
            print(f"Could not create thumbnail: {error}")

        self.file_selected.emit(file_path)

    def thumbnail_height_for_width(self, width):
        """Return the frame height needed for the thumbnail and its padding."""

        if self.thumbnail is None or self.thumbnail.isNull():
            return self.empty_minimum_height

        content_width = max(
            1,
            width - (self.thumbnail_padding * 2),
        )

        content_height = round(
            content_width
            * self.thumbnail.height()
            / self.thumbnail.width()
        )

        return content_height + (self.thumbnail_padding * 2)

    def update_thumbnail_height(self):
        """Resize the drop frame to surround the thumbnail evenly."""

        if self.thumbnail is None or self.thumbnail.isNull():
            return

        target_height = self.thumbnail_height_for_width(
            self.width()
        )

        if self.height() != target_height:
            self.setFixedHeight(target_height)

        self.updateGeometry()

    def display_thumbnail(self):
        """Scale and clip the thumbnail to a rounded rectangle."""

        if self.thumbnail is None:
            return

        scaled_thumbnail = self.thumbnail.scaled(
            self.label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        rounded_thumbnail = QPixmap(scaled_thumbnail.size())
        rounded_thumbnail.fill(Qt.GlobalColor.transparent)

        painter = QPainter(rounded_thumbnail)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        clipping_path = QPainterPath()
        clipping_path.addRoundedRect(
            QRectF(rounded_thumbnail.rect()),
            12,
            12,
        )

        painter.setClipPath(clipping_path)
        painter.drawPixmap(0, 0, scaled_thumbnail)
        painter.end()

        self.label.setPixmap(rounded_thumbnail)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if self.thumbnail is None:
            return

        target_height = self.thumbnail_height_for_width(
            event.size().width()
        )

        # Changing the width may require a matching height change. The second
        # resize event redraws the pixmap after the layout has settled.
        if event.size().height() != target_height:
            self.setFixedHeight(target_height)
            return

        self.display_thumbnail()


class MainWindow(QMainWindow):
    """Coordinate video selection, navigation, and FFmpeg rendering."""

    def __init__(self):
        super().__init__()

        self.selected_video = None

        self.video_duration = 0.0

        self.setWindowTitle("ffupscale")
        self.resize(975, 555)

        # Application title
        title = QLabel("ffupscale")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""
            font-size: 40px;
            font-weight: bold;
        """)

        # Drag-and-drop area
        self.drop_area = DropArea()
        self.drop_area.file_selected.connect(self.video_selected)

        # Property value labels
        self.resolution_value = QLabel("—")
        self.fps_value = QLabel("—")
        self.duration_value = QLabel("—")
        self.codec_value = QLabel("—")
        self.format_value = QLabel("—")
        self.file_size_value = QLabel("—")

        # Arrange property names and their values
        properties_layout = QFormLayout()
        properties_layout.setHorizontalSpacing(20)
        properties_layout.setVerticalSpacing(15)

        properties_layout.addRow(
            "Resolution:",
            self.resolution_value,
        )
        properties_layout.addRow(
            "Frame rate:",
            self.fps_value,
        )
        properties_layout.addRow(
            "Duration:",
            self.duration_value,
        )
        properties_layout.addRow(
            "Codec:",
            self.codec_value,
        )
        properties_layout.addRow(
            "Format:",
            self.format_value,
        )
        properties_layout.addRow(
            "File size:",
            self.file_size_value,
        )

        # Continue button
        self.continue_button = QPushButton("Continue")
        self.continue_button.setEnabled(False)

        self.continue_button.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                font-weight: bold;
                padding: 8px;
            }
        """)

        # Right side: properties followed by Continue button
        right_layout = QVBoxLayout()
        right_layout.addLayout(properties_layout)
        right_layout.addStretch()
        right_layout.addWidget(self.continue_button)

        # Drop area on the left, information on the right
        content_layout = QHBoxLayout()
        content_layout.setSpacing(30)

        content_layout.addWidget(
            self.drop_area,
            stretch=2,
        )

        content_layout.addLayout(
            right_layout,
            stretch=1,
        )

        # Complete window layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(30, 20, 30, 30)
        main_layout.setSpacing(20)

        main_layout.addWidget(title)
        main_layout.addLayout(content_layout)

        # First screen
        self.file_page = QWidget()
        self.file_page.setLayout(main_layout)

        # Second screen, imported from settings_page.py
        self.settings_page = SettingsPage()

        self.ffmpeg_process = QProcess(self)
        self.ffmpeg_log = ""
        self.progress_buffer = ""
        self.current_output_path = None
        self.render_was_cancelled = False

        self.ffmpeg_process.readyReadStandardOutput.connect(self.read_ffmpeg_progress)

        self.ffmpeg_process.readyReadStandardError.connect(self.read_ffmpeg_output)

        self.ffmpeg_process.finished.connect(self.render_finished)

        self.ffmpeg_process.errorOccurred.connect(self.process_error)

        # Container that stores both screens
        self.pages = QStackedWidget()
        self.pages.addWidget(self.file_page)
        self.pages.addWidget(self.settings_page)

        self.setCentralWidget(self.pages)

        self.continue_button.clicked.connect(self.open_settings)

        self.settings_page.back_requested.connect(self.open_file_page)

        self.settings_page.render_requested.connect(self.start_render)

        self.settings_page.cancel_requested.connect(self.cancel_render)

    def video_selected(self, file_path):
        """Read video metadata and populate the summary page."""

        self.selected_video = None
        self.video_duration = 0.0
        self.continue_button.setEnabled(False)

        try:
            properties = read_video_properties(file_path)

            self.video_duration = properties["duration"]

            file_size_mb = properties["file_size"] / (1024 * 1024)

            self.resolution_value.setText(
                f"{properties['width']} × {properties['height']}"
            )

            self.fps_value.setText(f"{properties['fps']:.2f} FPS")

            self.duration_value.setText(format_duration(properties["duration"]))

            self.codec_value.setText(properties["codec"].upper())

            self.format_value.setText(properties["format"])

            self.file_size_value.setText(f"{file_size_mb:.2f} MB")

            self.selected_video = file_path

            print(f"Selected video: {file_path}")
            print(properties)

            self.continue_button.setEnabled(True)

        except FileNotFoundError as error:
            self.show_error(str(error))

        except subprocess.CalledProcessError as error:
            message = "FFprobe could not read the selected file."

            if error.stderr:
                message += f"\n\n{error.stderr}"

            self.show_error(message)

        except (
            json.JSONDecodeError,
            KeyError,
            ValueError,
            IndexError,
        ) as error:
            self.show_error(f"Could not understand the video information:\n{error}")

    def open_settings(self):
        if self.selected_video is None:
            self.show_error("Select a video first.")
            return

        self.settings_page.set_video(self.selected_video)

        self.pages.setCurrentWidget(self.settings_page)

    def open_file_page(self):
        self.pages.setCurrentWidget(self.file_page)

    def show_error(self, message):
        QMessageBox.critical(
            self,
            "Could not read video",
            message,
        )

    def start_render(self, settings):
        """Build the command and start FFmpeg asynchronously."""

        if self.selected_video is None:
            self.show_error("Select a video first.")
            return

        if self.ffmpeg_process.state() != QProcess.ProcessState.NotRunning:
            self.show_error("A video is already being rendered.")
            return

        try:
            input_path = Path(self.selected_video)
            output_path = create_output_path(input_path)

            width, height = settings["resolution"]

            ffmpeg_path, arguments = build_upscale_command(
                input_path=input_path,
                output_path=output_path,
                width=width,
                height=height,
                quality=settings["quality"],
                fps=settings["fps"],
                encoder=settings["encoder"],
                preset=settings["preset"],
            )

            self.current_output_path = output_path
            self.ffmpeg_log = ""
            self.progress_buffer = ""
            self.render_was_cancelled = False

            self.settings_page.set_rendering(True)

            print("Starting FFmpeg:")
            print(subprocess.list2cmdline([ffmpeg_path, *arguments]))

            self.ffmpeg_process.start(
                ffmpeg_path,
                arguments,
            )

        except (
            FileNotFoundError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            self.reset_render_button()
            self.show_error(str(error))

    def read_ffmpeg_output(self):
        """Collect FFmpeg diagnostics from stderr for error reporting."""

        output = self.ffmpeg_process.readAllStandardError()

        text = bytes(output).decode(errors="replace")

        self.ffmpeg_log += text
        # Bound memory use while retaining the most recent diagnostic output.
        self.ffmpeg_log = self.ffmpeg_log[-100_000:]

        print(text, end="")

    def read_ffmpeg_progress(self):
        """Parse FFmpeg's key=value progress stream from stdout."""

        output = self.ffmpeg_process.readAllStandardOutput()

        text = bytes(output).decode(errors="replace")

        self.progress_buffer += text

        # QProcess chunks may end mid-line, so preserve incomplete data.
        while "\n" in self.progress_buffer:
            line, self.progress_buffer = self.progress_buffer.split("\n", 1)

            line = line.strip()

            if "=" not in line:
                continue

            key, value = line.split("=", 1)

            if key == "out_time_us":
                try:
                    processed_seconds = int(value) / 1_000_000

                    if self.video_duration > 0:
                        percentage = processed_seconds / self.video_duration * 100

                        self.settings_page.set_progress(percentage)

                except ValueError:
                    pass

            elif key == "progress" and value == "end":
                self.settings_page.set_progress(100)

    def render_finished(
        self,
        exit_code,
        exit_status,
    ):
        """Restore controls and report cancellation, success, or failure."""

        was_cancelled = self.render_was_cancelled

        self.reset_render_button()

        if was_cancelled:
            QMessageBox.information(
                self,
                "Render cancelled",
                (
                    "Rendering was cancelled."
                    "\n\nA partial output file may remain at:"
                    f"\n{self.current_output_path}"
                ),
            )
            return

        if (
            exit_code == 0
            and self.current_output_path is not None
            and self.current_output_path.is_file()
        ):
            self.settings_page.set_progress(100)

            QMessageBox.information(
                self,
                "Render complete",
                (
                    "The video was rendered successfully."
                    f"\n\n{self.current_output_path}"
                ),
            )

        else:
            error_message = f"FFmpeg exited with code {exit_code}."

            if self.ffmpeg_log:
                error_lines = self.ffmpeg_log.strip().splitlines()

                final_lines = error_lines[-10:]

                error_message += "\n\n" + "\n".join(final_lines)

            self.show_error(error_message)

    def process_error(self, process_error):
        if process_error == QProcess.ProcessError.FailedToStart:
            self.reset_render_button()

            self.show_error("FFmpeg could not be started.")

    def reset_render_button(self):
        self.settings_page.set_rendering(False)

    def cancel_render(self):
        """Ask FFmpeg to stop cleanly and finalize the partial file."""

        if self.ffmpeg_process.state() == QProcess.ProcessState.NotRunning:
            return

        self.render_was_cancelled = True
        self.settings_page.set_cancelling()

        # FFmpeg listens for "q" and stops cleanly.
        self.ffmpeg_process.write(b"q\n")
