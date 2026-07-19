import json
import shutil
import subprocess
import sys
import ctypes

from settings_page import SettingsPage

from pathlib import Path

from PyQt6.QtGui import QPainter, QPainterPath, QPixmap, QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QProcess
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QStackedWidget,
)

from ffmpeg_runner import (
    build_upscale_command,
    create_output_path,
)

# --- FUNCTIONS ---

def read_video_properties(file_path):
    """Use FFprobe to read properties from the selected video."""

    ffprobe_path = shutil.which("ffprobe")

    if ffprobe_path is None:
        raise FileNotFoundError(
            "FFprobe could not be found. Make sure FFmpeg is installed "
            "and added to PATH."
        )

    command = [
        ffprobe_path,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        (
            "stream=width,height,avg_frame_rate,codec_name:"
            "format=duration,size"
        ),
        "-of", "json",
        file_path,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
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
    ffmpeg_path = shutil.which("ffmpeg")

    if ffmpeg_path is None:
        raise FileNotFoundError(
            "FFmpeg could not be found."
        )

    command = [
        ffmpeg_path,
        "-v", "error",
        "-ss", "1",
        "-i", file_path,
        "-frames:v", "1",
        "-f", "image2pipe",
        "-vcodec", "png",
        "pipe:1",
    ]

    result = subprocess.run(
        command,
        capture_output=True,
    )

    if result.returncode != 0 or not result.stdout:
        ffmpeg_error = result.stderr.decode(
            errors="replace"
        )

        raise ValueError(
            f"FFmpeg could not create a video thumbnail:\n"
            f"{ffmpeg_error}"
        )

    thumbnail = QPixmap()

    if not thumbnail.loadFromData(result.stdout):
        raise ValueError(
            "The thumbnail image could not be loaded."
        )

    return thumbnail

# --- CLASSES ---

class DropArea(QFrame): # -- DROP AREA --
    file_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.setObjectName("dropArea")
        self.setAcceptDrops(True)
        self.setMinimumHeight(250)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.label = QLabel("Drag file or click to browse")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.thumbnail = None

        # This means the label will not intercept mouse clicks.
        self.label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        layout = QVBoxLayout(self)
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
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_file_browser()

        super().mousePressEvent(event)

    def open_file_browser(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a video",
            "",
            (
                "Video files (*.mp4 *.mov *.mkv *.avi *.webm);;"
                "All files (*.*)"
            ),
        )

        if file_path:
            self.select_file(file_path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
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
        try:
            self.thumbnail = create_video_thumbnail(file_path)
            self.display_thumbnail()

        except (FileNotFoundError, ValueError) as error:
            self.thumbnail = None
            self.label.setText(Path(file_path).name)
            print(f"Could not create thumbnail: {error}")

        self.file_selected.emit(file_path)

    def display_thumbnail(self):
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

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform
        )

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

        if self.thumbnail is not None:
            self.display_thumbnail()    


class MainWindow(QMainWindow): # -- MAIN WINDOW --
    def __init__(self):
        super().__init__()

        self.selected_video = None
        
        self.setWindowTitle("ffupscale")
        self.resize(693, 407)

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
        main_layout.setContentsMargins(30,20,30,30,)
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
        self.current_output_path = None

        self.ffmpeg_process.readyReadStandardError.connect(
            self.read_ffmpeg_output
        )

        self.ffmpeg_process.finished.connect(
            self.render_finished
        )

        self.ffmpeg_process.errorOccurred.connect(
            self.process_error
        )

        # Container that stores both screens
        self.pages = QStackedWidget()
        self.pages.addWidget(self.file_page)
        self.pages.addWidget(self.settings_page)

        self.setCentralWidget(self.pages)

        self.continue_button.clicked.connect(self.open_settings)

        self.settings_page.back_requested.connect(
            self.open_file_page
        )

        self.settings_page.render_requested.connect(
            self.start_render
        )

    def video_selected(self, file_path):
        self.selected_video = None
        self.continue_button.setEnabled(False)

        try:
            properties = read_video_properties(file_path)

            file_size_mb = (
                properties["file_size"] / (1024 * 1024)
            )

            self.resolution_value.setText(
                f"{properties['width']} × {properties['height']}"
            )

            self.fps_value.setText(
                f"{properties['fps']:.2f} FPS"
            )

            self.duration_value.setText(
                format_duration(properties["duration"])
            )

            self.codec_value.setText(
                properties["codec"].upper()
            )

            self.format_value.setText(
                properties["format"]
            )

            self.file_size_value.setText(
                f"{file_size_mb:.2f} MB"
            )

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
            self.show_error(
                f"Could not understand the video information:\n{error}"
            )

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
        if self.selected_video is None:
            self.show_error("Select a video first.")
            return

        if (
            self.ffmpeg_process.state()
            != QProcess.ProcessState.NotRunning
        ):
            self.show_error(
                "A video is already being rendered."
            )
            return

        try:
            input_path = Path(self.selected_video)
            output_path = create_output_path(
                input_path
            )

            width, height = settings["resolution"]

            ffmpeg_path, arguments = build_upscale_command(
                input_path=input_path,
                output_path=output_path,
                width=width,
                height=height,
                quality=settings["quality"],
                fps=settings["fps"],
            )

            self.current_output_path = output_path
            self.ffmpeg_log = ""

            self.settings_page.render_button.setEnabled(
                False
            )

            self.settings_page.back_button.setEnabled(
                False
            )

            self.settings_page.render_button.setText(
                "Rendering..."
            )

            print("Starting FFmpeg:")
            print(
                subprocess.list2cmdline(
                    [ffmpeg_path, *arguments]
                )
            )

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
        output = (
            self.ffmpeg_process
            .readAllStandardError()
        )

        text = bytes(output).decode(
            errors="replace"
        )

        self.ffmpeg_log += text
        self.ffmpeg_log = self.ffmpeg_log[-100_000:]
        
        print(text, end="")

    def render_finished(
        self,
        exit_code,
        exit_status,
    ):
        self.reset_render_button()

        if (exit_code == 0
           and self.current_output_path is not None
           and self.current_output_path.is_file()):
            QMessageBox.information(
                self,
                "Render complete",
                (
                    "The video was rendered successfully."
                    f"\n\n{self.current_output_path}"
                ),
            )

        else:
            error_message = (
                f"FFmpeg exited with code {exit_code}."
            )

            if self.ffmpeg_log:
                error_lines = (
                    self.ffmpeg_log.strip().splitlines()
                )

                final_lines = error_lines[-10:]

                error_message += (
                    "\n\n"
                    + "\n".join(final_lines)
                )

            self.show_error(error_message)

    def process_error(self, process_error):
        if (
            process_error
            == QProcess.ProcessError.FailedToStart
        ):
            self.reset_render_button()

            self.show_error(
                "FFmpeg could not be started."
            )

    def reset_render_button(self):
        self.settings_page.render_button.setEnabled(
            True
        )

        self.settings_page.render_button.setText(
            "Render"
        )

        self.settings_page.back_button.setEnabled(
            True
        )

if __name__ == "__main__":
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "kianyng.ffupscale"
        )

    app = QApplication(sys.argv)

    icon_path = (
        Path(__file__).resolve().parent.parent
        / "assets"
        / "icon.ico"
    )

    app_icon = QIcon(str(icon_path))
    app.setWindowIcon(app_icon)

    window = MainWindow()
    window.setWindowIcon(app_icon)
    window.show()

    sys.exit(app.exec())