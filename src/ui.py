import json
import shutil
import subprocess
import sys

from pathlib import Path

from PyQt6.QtGui import QPainter, QPainterPath, QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
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
)


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
class DropArea(QFrame):
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("ffupscale")
        self.resize(700, 500)

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

        # Put the drop area and properties beside each other
        content_layout = QHBoxLayout()
        content_layout.setSpacing(30)

        content_layout.addWidget(
            self.drop_area,
            stretch=2,
        )
        content_layout.addLayout(
            properties_layout,
            stretch=1,
        )

        # Main window layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(30, 20, 30, 30)
        main_layout.setSpacing(20)

        main_layout.addWidget(title)
        main_layout.addLayout(content_layout)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)

        self.setCentralWidget(central_widget)

    def video_selected(self, file_path):
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

            print(f"Selected video: {file_path}")
            print(properties)

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

    def show_error(self, message):
        QMessageBox.critical(
            self,
            "Could not read video",
            message,
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())