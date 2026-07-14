import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QFrame,
    QVBoxLayout,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("ffupscale")
        self.resize(800, 500)

        title = QLabel("ffupscale")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 40px; font-weight: bold;")

        drop_label = QLabel("Drag a video here")
        drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_label.setStyleSheet("""QLabel {border: 2px dashed #777;border-radius: 10px;padding: 80px;font-size: 20px;}""")

        select_button = QPushButton("Select video")

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(drop_label)
        layout.addWidget(select_button)

        central_widget = QWidget()
        central_widget.setLayout(layout)

        self.setCentralWidget(central_widget)


app = QApplication(sys.argv)

window = MainWindow()
window.show()

sys.exit(app.exec())