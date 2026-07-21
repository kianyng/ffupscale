import shutil
import sys
from pathlib import Path


def bundled_bin_directory():
    """
    Return the directory containing the bundled FFmpeg programs.
    """

    if getattr(sys, "frozen", False):
        # PyInstaller makes bundled files available beneath _MEIPASS.
        base_directory = Path(sys._MEIPASS)
        return base_directory / "bin"

    # Location used when running directly from the repository.
    return (
        Path(__file__).resolve().parent.parent
        / "vendor"
        / "ffmpeg"
        / "bin"
    )


def find_program(name):
    """
    Look for a bundled executable first, then check system PATH.
    """

    executable_name = (
        f"{name}.exe"
        if sys.platform == "win32"
        else name
    )

    bundled_path = (
        bundled_bin_directory()
        / executable_name
    )

    if bundled_path.is_file():
        return str(bundled_path)

    return shutil.which(name)


def find_ffmpeg():
    """Return the FFmpeg path or raise a helpful error."""

    ffmpeg_path = find_program("ffmpeg")

    if ffmpeg_path is None:
        raise FileNotFoundError(
            "FFmpeg could not be found."
        )

    return ffmpeg_path


def find_ffprobe():
    """Return the FFprobe path or raise a helpful error."""

    ffprobe_path = find_program("ffprobe")

    if ffprobe_path is None:
        raise FileNotFoundError(
            "FFprobe could not be found."
        )

    return ffprobe_path


def ffmpeg_is_available():
    """Return whether both FFmpeg programs are available."""

    return (
        find_program("ffmpeg") is not None
        and find_program("ffprobe") is not None
    )