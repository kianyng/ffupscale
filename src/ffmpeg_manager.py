import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

# -- Hardware Encoder Definitions --

HARDWARE_ENCODERS = {
    "nvidia": {
        "h264": "h264_nvenc",
        "h265": "hevc_nvenc",
    },
    "amd": {
        "h264": "h264_amf",
        "h265": "hevc_amf",
    },
    "intel": {
        "h264": "h264_qsv",
        "h265": "hevc_qsv",
    },
}

# -- FFmpeg Paths --


def bundled_bin_directory():
    """
    Return the directory containing the bundled FFmpeg programs.
    """

    if getattr(sys, "frozen", False):
        # PyInstaller makes bundled files available beneath _MEIPASS.
        base_directory = Path(sys._MEIPASS)
        return base_directory / "bin"

    # Location used when running directly from the repository.
    return Path(__file__).resolve().parent.parent / "vendor" / "ffmpeg" / "bin"


def find_program(name):
    """
    Look for a bundled executable first, then check system PATH.
    """

    executable_name = f"{name}.exe" if sys.platform == "win32" else name

    bundled_path = bundled_bin_directory() / executable_name

    if bundled_path.is_file():
        return str(bundled_path)

    return shutil.which(name)


def find_ffmpeg():
    """Return the FFmpeg path or raise a helpful error."""

    ffmpeg_path = find_program("ffmpeg")

    if ffmpeg_path is None:
        raise FileNotFoundError("FFmpeg could not be found.")

    return ffmpeg_path


def find_ffprobe():
    """Return the FFprobe path or raise a helpful error."""

    ffprobe_path = find_program("ffprobe")

    if ffprobe_path is None:
        raise FileNotFoundError("FFprobe could not be found.")

    return ffprobe_path


def ffmpeg_is_available():
    """Return whether both FFmpeg programs are available."""

    return find_program("ffmpeg") is not None and find_program("ffprobe") is not None


# -- Process Helpers --


def hidden_process_flags():
    """Prevent FFmpeg subprocesses from opening a console on Windows."""

    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW

    return 0


# -- Hardware Encoder Detection --


@lru_cache(maxsize=1)
def get_compiled_video_encoders():
    """
    Return the video encoders included in the available FFmpeg build.

    This only shows what FFmpeg was compiled to support. It does not prove
    that the computer has the required GPU or driver.
    """

    ffmpeg_path = find_ffmpeg()

    result = subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-encoders",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        creationflags=hidden_process_flags(),
    )

    encoders = set()

    for line in result.stdout.splitlines():
        columns = line.split()

        if len(columns) < 2:
            continue

        flags = columns[0]
        encoder_name = columns[1]

        if flags.startswith("V"):
            encoders.add(encoder_name)

    return encoders


def encoder_is_usable(encoder):
    """
    Perform a one-frame test encode.

    An encoder can appear in `ffmpeg -encoders` but still fail because the
    required GPU, driver or hardware capability is unavailable.
    """

    ffmpeg_path = find_ffmpeg()

    arguments = [
        "-hide_banner",
        "-loglevel",
        "error",
        # Generate a tiny frame entirely in memory.
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=640x360:r=1",
        # Encode only one silent frame.
        "-frames:v",
        "1",
        "-an",
        "-c:v",
        encoder,
        "-pix_fmt",
        "yuv420p",
        # Discard the encoded result.
        "-f",
        "null",
        "-",
    ]

    try:
        result = subprocess.run(
            [ffmpeg_path, *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=15,
            creationflags=hidden_process_flags(),
        )

    except subprocess.TimeoutExpired:
        return False

    return result.returncode == 0


@lru_cache(maxsize=1)
def detect_hardware_encoders():
    """
    Return hardware encoders that successfully work on this computer.

    Example result:
    {
        "nvidia": {
            "h264": "h264_nvenc",
            "h265": "hevc_nvenc",
        }
    }
    """

    compiled_encoders = get_compiled_video_encoders()
    available_encoders = {}

    for vendor, codecs in HARDWARE_ENCODERS.items():
        usable_codecs = {}

        for codec, encoder in codecs.items():
            if encoder not in compiled_encoders:
                continue

            if encoder_is_usable(encoder):
                usable_codecs[codec] = encoder

        if usable_codecs:
            available_encoders[vendor] = usable_codecs

    return available_encoders
