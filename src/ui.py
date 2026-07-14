import sys
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)


class DropArea(QFrame):
    file_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.setObjectName("dropArea")
        self.setAcceptDrops(True)
        self.setMinimumHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.label = QLabel("Drag file or click to browse")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self.label)

        self.setStyleSheet("""
            QFrame#dropArea {
                border: 3px dashed #999999;
                border-radius: 12px;
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
            "Video files (*.mp4 *.mov *.mkv *.avi *.webm);;All files (*.*)",
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
            return

        file_path = urls[0].toLocalFile()

        if Path(file_path).is_file():
            self.select_file(file_path)
            event.acceptProposedAction()

    def select_file(self, file_path):
        self.label.setText(Path(file_path).name)
        self.file_selected.emit(file_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("ffupscale")
        self.resize(800, 500)

        title = QLabel("ffupscale")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""font-size: 40px; font-weight: bold; color: white;""")
        
        self.drop_area = DropArea()
        self.drop_area.file_selected.connect(self.video_selected)

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)

        layout.addWidget(title)
        layout.addWidget(self.drop_area)

        central_widget = QWidget()
        central_widget.setLayout(layout)

        self.setCentralWidget(central_widget)

    def video_selected(self, file_path):
        print(f"Selected video: {file_path}")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())