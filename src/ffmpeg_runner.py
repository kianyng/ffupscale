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

# -- Target Size Calculation --

TARGET_AUDIO_BITRATE = 128_000
CONTAINER_OVERHEAD_RATIO = 0.02
MINIMUM_VIDEO_BITRATE = 500_000
MINIMUM_NVENC_BITS_PER_PIXEL = 0.011


def calculate_minimum_target_size_mb(
    duration,
    width,
    height,
    fps,
    encoder,
):
    """
    Estimate the smallest target NVENC is likely to reach.

    Returns None when no estimate is available for the encoder.
    """

    if (
        duration is None
        or duration <= 0
        or fps is None
        or fps <= 0
    ):
        return None

    if encoder == "h264_nvenc":
        bits_per_pixel = (
            MINIMUM_NVENC_BITS_PER_PIXEL
        )

    elif encoder == "hevc_nvenc":
        bits_per_pixel = (
            MINIMUM_NVENC_BITS_PER_PIXEL
            * 0.6
        )

    else:
        # We currently only have a tested estimate for NVENC.
        return None

    minimum_video_bitrate = int(
        width
        * height
        * fps
        * bits_per_pixel
    )

    minimum_size_mb = (
        (
            minimum_video_bitrate
            + TARGET_AUDIO_BITRATE
        )
        * duration
        / 8
        / 1_000_000
        / (
            1
            - CONTAINER_OVERHEAD_RATIO
        )
    )

    return minimum_size_mb


def calculate_target_video_bitrate(
    target_size_mb,
    duration,
    width,
    height,
    fps,
    encoder,
):
    """
    Calculate the video bitrate required to approach a target size.

    Target size uses decimal megabytes, where one MB is 1,000,000 bytes.
    A small allowance is reserved for the MP4 container and 128 kbps audio.
    """

    if (
        isinstance(target_size_mb, bool)
        or not isinstance(
            target_size_mb,
            (int, float),
        )
    ):
        raise ValueError(
            "Target file size must be a number."
        )

    if target_size_mb <= 0:
        raise ValueError(
            "Target file size must be greater than zero."
        )

    if duration <= 0:
        raise ValueError(
            "The video duration must be greater than zero."
        )

    target_bits = (
        target_size_mb
        * 1_000_000
        * 8
    )

    usable_bits = target_bits * (
        1 - CONTAINER_OVERHEAD_RATIO
    )

    total_bitrate = usable_bits / duration

    video_bitrate = int(
        total_bitrate
        - TARGET_AUDIO_BITRATE
    )

    if video_bitrate < MINIMUM_VIDEO_BITRATE:
        minimum_size_mb = (
            (
                MINIMUM_VIDEO_BITRATE
                + TARGET_AUDIO_BITRATE
            )
            * duration
            / 8
            / 1_000_000
            / (
                1
                - CONTAINER_OVERHEAD_RATIO
            )
        )

        raise ValueError(
            "The selected target size is too small "
            "for this video's duration.\n\n"
            f"Try at least {minimum_size_mb:.1f} MB."
        )

    minimum_target_size_mb = (
        calculate_minimum_target_size_mb(
            duration=duration,
            width=width,
            height=height,
            fps=fps,
            encoder=encoder,
        )
    )

    if (
        minimum_target_size_mb is not None
        and target_size_mb < minimum_target_size_mb
    ):
        raise ValueError(
            "The target size is too small for the selected "
            "resolution, frame rate, and GPU encoder.\n\n"
            f"Estimated minimum: "
            f"{minimum_target_size_mb:.1f} MB\n\n"
            "Try lowering the resolution or frame rate, "
            "selecting H.265, increasing the target size, "
            "or using CPU encoding."
        )
    
    return video_bitrate


# -- Encoder Arguments --

def build_video_encoder_arguments(
    encoder,
    quality,
    speed,
    video_bitrate=None,
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

    arguments = [
        "-c:v",
        encoder,
        profile["preset_option"],
        profile["presets"][speed],
    ]

    vendor = profile["vendor"]

    # Target-size mode needs tighter bitrate control than quality mode.
    if video_bitrate is not None:
        bitrate = str(video_bitrate)
        buffer_size = str(video_bitrate * 2)

        if vendor == "nvidia":
            arguments.extend([
                "-rc",
                "cbr",
                "-b:v",
                bitrate,
                "-minrate",
                bitrate,
                "-maxrate",
                bitrate,
                "-bufsize",
                buffer_size,
            ])

        elif vendor == "amd":
            arguments.extend([
                "-rc",
                "cbr",
                "-b:v",
                bitrate,
                "-minrate",
                bitrate,
                "-maxrate",
                bitrate,
                "-bufsize",
                buffer_size,
            ])

        else:
            # CPU and Intel encoders accept FFmpeg's generic
            # bitrate constraint options.
            arguments.extend([
                "-b:v",
                bitrate,
                "-maxrate",
                bitrate,
                "-bufsize",
                buffer_size,
            ])

        return arguments

    # ffupscale presents larger values as better quality. FFmpeg's CRF,
    # CQ and QP systems generally use smaller values for better quality.
    ffmpeg_quality = 52 - quality

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
    rate_control="quality",
    target_size_mb=None,
    duration=None,
    source_fps=None,
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

    if rate_control not in {
        "quality",
        "target_size",
    }:
        raise ValueError(
            f"Unknown rate-control mode: {rate_control}"
        )

    video_bitrate = None

    if rate_control == "target_size":
        if target_size_mb is None:
            raise ValueError(
                "Enter a target file size."
            )

        if duration is None:
            raise ValueError(
                "Video duration is required for target-size mode."
            )

        effective_fps = (
            fps
            if fps is not None
            else source_fps
        )

        if (
            effective_fps is None
            or effective_fps <= 0
        ):
            raise ValueError(
                "The source frame rate is required "
                "for target-size validation."
            )

        video_bitrate = (
            calculate_target_video_bitrate(
                target_size_mb=target_size_mb,
                duration=duration,
                width=width,
                height=height,
                fps=effective_fps,
                encoder=encoder,
            )
        )

    video_encoder_arguments = (
        build_video_encoder_arguments(
            encoder=encoder,
            quality=quality,
            speed=preset,
            video_bitrate=video_bitrate,
        )
    )

    if rate_control == "target_size":
        # A known audio bitrate makes the final size more predictable.
        audio_arguments = [
            "-c:a",
            "aac",
            "-b:a",
            "128k",
        ]

    else:
        # Quality mode can preserve the original compressed audio.
        audio_arguments = [
            "-c:a",
            "copy",
        ]

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
        "0:a:0?",
        # Upscaling
        "-vf",
        f"scale={width}:{height}:flags=lanczos",
        # Encoder-specific codec, quality and speed options
        *video_encoder_arguments,
        # Broad playback compatibility
        "-pix_fmt",
        "yuv420p",
        # Copy audio in quality mode or use a predictable bitrate
        # when targeting a file size.
        *audio_arguments,
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
