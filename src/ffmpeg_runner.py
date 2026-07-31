from pathlib import Path

from ffmpeg_manager import find_ffmpeg

# -- Shared Encoding Speeds --

ENCODING_SPEEDS = {
    "fast",
    "medium",
    "slow",
}


# -- Encoder Profiles --

ENCODER_PROFILES = {
    # CPU encoders
    "libx264": {
        "vendor": "cpu",
        "codec": "h264",
        "hardware": False,
        "preset_option": "-preset",
        "presets": {
            "fast": "fast",
            "medium": "medium",
            "slow": "slow",
        },
    },
    "libx265": {
        "vendor": "cpu",
        "codec": "h265",
        "hardware": False,
        "preset_option": "-preset",
        "presets": {
            "fast": "fast",
            "medium": "medium",
            "slow": "slow",
        },
    },

    # NVIDIA NVENC
    "h264_nvenc": {
        "vendor": "nvidia",
        "codec": "h264",
        "hardware": True,
        "preset_option": "-preset",
        "presets": {
            "fast": "p2",
            "medium": "p4",
            "slow": "p7",
        },
    },
    "hevc_nvenc": {
        "vendor": "nvidia",
        "codec": "h265",
        "hardware": True,
        "preset_option": "-preset",
        "presets": {
            "fast": "p2",
            "medium": "p4",
            "slow": "p7",
        },
    },

    # AMD AMF
    "h264_amf": {
        "vendor": "amd",
        "codec": "h264",
        "hardware": True,
        "preset_option": "-quality",
        "presets": {
            "fast": "speed",
            "medium": "balanced",
            "slow": "quality",
        },
    },
    "hevc_amf": {
        "vendor": "amd",
        "codec": "h265",
        "hardware": True,
        "preset_option": "-quality",
        "presets": {
            "fast": "speed",
            "medium": "balanced",
            "slow": "quality",
        },
    },

    # Intel Quick Sync
    "h264_qsv": {
        "vendor": "intel",
        "codec": "h264",
        "hardware": True,
        "preset_option": "-preset",
        "presets": {
            "fast": "fast",
            "medium": "medium",
            "slow": "slow",
        },
    },
    "hevc_qsv": {
        "vendor": "intel",
        "codec": "h265",
        "hardware": True,
        "preset_option": "-preset",
        "presets": {
            "fast": "fast",
            "medium": "medium",
            "slow": "slow",
        },
    },
}


SUPPORTED_ENCODERS = set(ENCODER_PROFILES)


# -- Encoder Arguments --

def build_video_encoder_arguments(
    encoder,
    quality,
    speed,
):
    """Build quality and speed arguments for a video encoder."""

    if encoder not in ENCODER_PROFILES:
        raise ValueError(
            f"Unknown encoder: {encoder}"
        )

    if speed not in ENCODING_SPEEDS:
        raise ValueError(
            f"Unknown encoding speed: {speed}"
        )

    if (
        isinstance(quality, bool)
        or not isinstance(quality, int)
    ):
        raise ValueError(
            "Quality must be a whole number."
        )

    if not 1 <= quality <= 51:
        raise ValueError(
            "Quality must be between 1 and 51."
        )

    profile = ENCODER_PROFILES[encoder]

    # ffupscale presents larger values as better quality. FFmpeg's CRF,
    # CQ and QP systems generally use smaller values for better quality.
    ffmpeg_quality = 52 - quality

    arguments = [
        "-c:v",
        encoder,
        profile["preset_option"],
        profile["presets"][speed],
    ]

    vendor = profile["vendor"]

    if vendor == "cpu":
        arguments.extend([
            "-crf",
            str(ffmpeg_quality),
        ])

    elif vendor == "nvidia":
        arguments.extend([
            "-rc",
            "vbr",
            "-cq",
            str(ffmpeg_quality),
            "-b:v",
            "0",
        ])

    elif vendor == "amd":
        arguments.extend([
            "-rc",
            "cqp",
            "-qp_i",
            str(ffmpeg_quality),
            "-qp_p",
            str(ffmpeg_quality),
        ])

    elif vendor == "intel":
        arguments.extend([
            "-global_quality",
            str(ffmpeg_quality),
        ])

    else:
        raise ValueError(
            f"Unsupported encoder vendor: {vendor}"
        )

    return arguments


# -- FFmpeg Command --

def build_upscale_command(
    input_path,
    output_path,
    width,
    height,
    quality=30,
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

    if encoder not in SUPPORTED_ENCODERS:
        raise ValueError(
            f"Unknown encoder: {encoder}"
        )

    if preset not in ENCODING_SPEEDS:
        raise ValueError(
            f"Unknown encoding speed: {preset}"
        )

    if fps is not None and fps <= 0:
        raise ValueError("FPS must be greater than zero.")

    video_encoder_arguments = (
        build_video_encoder_arguments(
            encoder=encoder,
            quality=quality,
            speed=preset,
        )
    )

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
        # Encoder-specific codec, quality and speed options
        *video_encoder_arguments,
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
    if ENCODER_PROFILES[encoder]["codec"] == "h265":
        arguments.extend([
            "-tag:v",
            "hvc1",
        ])

    if fps is not None:
        arguments.extend(["-r", str(fps)])

    arguments.append(str(output_path))

    return ffmpeg_path, arguments
