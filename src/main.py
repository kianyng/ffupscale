import ctypes
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from ui import MainWindow


def resource_path(*parts):
    """
    Return an asset path that works during development
    and inside a PyInstaller executable.
    """

    if hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent.parent

    return base_path.joinpath(*parts)


def main():
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "kianyng.ffupscale"
        )

    app = QApplication(sys.argv)

    icon_path = resource_path(
        "assets",
        "icon.ico",
    )

    app.setWindowIcon(
        QIcon(str(icon_path))
    )

    window = MainWindow()
    window.setWindowIcon(
        QIcon(str(icon_path))
    )

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()