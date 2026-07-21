import subprocess
from pathlib import Path

from ffmpeg_manager import find_ffmpeg

QUALITY_CRF = {
    "libx264": {
        "balanced": 22,
        "high": 18,
        "near_lossless": 14,
    },
    "libx265": {
        "balanced": 27,
        "high": 22,
        "near_lossless": 17,
    },
}

# Only expose presets supported by both software encoders in the UI.
ENCODING_PRESETS = {
    "fast",
    "medium",
    "slow",
}


def create_output_path(input_path):
    """Create a unique output path beside the input video."""

    input_path = Path(input_path)

    output_path = input_path.with_name(f"{input_path.stem}_upscaled.mp4")

    number = 2

    while output_path.exists():
        output_path = input_path.with_name(f"{input_path.stem}_upscaled_{number}.mp4")

        number += 1

    return output_path


def build_upscale_command(
    input_path,
    output_path,
    width,
    height,
    quality="high",
    fps=None,
    encoder="libx264",
    preset="medium",
):
    """
    Validate the settings and build an FFmpeg command.
    This function does not run FFmpeg.
    """

    ffmpeg_path = find_ffmpeg()


    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input video does not exist:\n{input_path}")

    if input_path.resolve() == output_path.resolve():
        raise ValueError("The output path cannot be the same as the input path.")

    if width <= 0 or height <= 0:
        raise ValueError("Width and height must be greater than zero.")

    if width % 2 != 0 or height % 2 != 0:
        raise ValueError("Width and height must both be even numbers.")

    if encoder not in QUALITY_CRF:
        raise ValueError(f"Unknown encoder: {encoder}")

    if quality not in QUALITY_CRF[encoder]:
        raise ValueError(f"Unknown quality setting: {quality}")

    if preset not in ENCODING_PRESETS:
        raise ValueError(f"Unknown encoding preset: {preset}")

    if fps is not None and fps <= 0:
        raise ValueError("FPS must be greater than zero.")

    crf = QUALITY_CRF[encoder][quality]

    arguments = [
        # Send machine-readable progress to stdout for the Qt progress bar.
        "-progress",
        "pipe:1",
        "-nostats",
        "-hide_banner",
        # Refuse to overwrite an existing output.
        "-n",
        # Input
        "-i",
        str(input_path),
        # First video stream and optional audio stream
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        # Upscaling
        "-vf",
        f"scale={width}:{height}:flags=lanczos",
        # Video encoding
        "-c:v",
        encoder,
        "-preset",
        preset,
        "-crf",
        str(crf),
        # Broad playback compatibility
        "-pix_fmt",
        "yuv420p",
        # Preserve the original compressed audio
        "-c:a",
        "copy",
        # Make MP4 begin playback sooner when streamed
        "-movflags",
        "+faststart",
    ]

    # hvc1 improves H.265 recognition in Apple players and devices.
    if encoder == "libx265":
        arguments.extend(["-tag:v", "hvc1"])

    if fps is not None:
        arguments.extend(["-r", str(fps)])

    arguments.append(str(output_path))

    return ffmpeg_path, arguments


def run_test_encode(
    input_path,
    width=3840,
    height=2160,
    quality="high",
    fps=None,
    encoder="libx264",
    preset="medium",
):
    """
    Run a blocking test encode independently of the GUI.
    """

    output_path = create_output_path(input_path)

    ffmpeg_path, arguments = build_upscale_command(
        input_path=input_path,
        output_path=output_path,
        width=width,
        height=height,
        quality=quality,
        fps=fps,
        encoder=encoder,
        preset=preset,
    )

    print("FFmpeg command:")
    print(subprocess.list2cmdline([ffmpeg_path, *arguments]))

    print(f"\nOutput: {output_path}\n")

    result = subprocess.run(
        [ffmpeg_path, *arguments],
        check=True,
    )

    return output_path, result.returncode

