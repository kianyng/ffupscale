import json
import subprocess
from pathlib import Path

from ffmpeg_manager import (
    find_ffmpeg,
    find_ffprobe,
    hidden_process_flags,
)

# -- Shared Encoding Speeds --

ENCODING_SPEEDS = {
    "fast",
    "medium",
    "slow",
}

GIF_PALETTE_SAMPLE_DURATION = 2.0


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
QUALITY_AUDIO_BITRATE = 192_000
CONTAINER_OVERHEAD_RATIO = 0.02
MINIMUM_VIDEO_BITRATE = 500_000
TARGET_SIZE_SAFETY_RATIO = 0.97
QUALITY_ESTIMATE_SCALE = 10
QUALITY_ESTIMATE_REFERENCE = 30
CRF_BITRATE_STEP = 6
NVENC_HIGH_QUALITY_REFERENCE = 18
NVENC_HIGH_QUALITY_BITRATE_STEP = 9.9
# Approximate bits required for each output pixel per frame.
#
# CPU values represent a recommended quality floor. Hardware values
# estimate where the encoder may stop obeying lower bitrate requests.
MINIMUM_BITS_PER_PIXEL = {
    # CPU
    "libx264": 0.007,
    "libx265": 0.004,
    # NVIDIA NVENC
    "h264_nvenc": 0.011,
    "hevc_nvenc": 0.006,
    # AMD AMF — provisional until tested on AMD hardware
    "h264_amf": 0.011,
    "hevc_amf": 0.006,
    # Intel Quick Sync — provisional until tested on Intel hardware
    "h264_qsv": 0.011,
    "hevc_qsv": 0.006,
}


# Approximate bitrate requirements for visually reasonable output.
#
# These are intentionally higher than MINIMUM_BITS_PER_PIXEL.
# The minimum values describe encoder limits, while these values
# are used when automatically recommending resolution and FPS.
RECOMMENDED_BITS_PER_PIXEL = {
    # CPU encoders
    "libx264": 0.016,
    "libx265": 0.010,

    # NVIDIA NVENC
    "h264_nvenc": 0.020,
    "hevc_nvenc": 0.012,

    # AMD AMF — provisional until tested on AMD hardware
    "h264_amf": 0.020,
    "hevc_amf": 0.012,

    # Intel Quick Sync — provisional until tested on Intel hardware
    "h264_qsv": 0.020,
    "hevc_qsv": 0.012,
}


# Only tested NVENC estimates should currently block a render.
ENFORCED_MINIMUM_ENCODERS = {
    "h264_nvenc",
    "hevc_nvenc",
}


def calculate_minimum_target_size_mb(
    duration,
    width,
    height,
    fps,
    encoder,
):
    """
    Estimate a practical minimum output size.

    Hardware estimates approximate the encoder's bitrate floor.
    CPU estimates represent a recommended quality floor.
    """

    if (
        duration is None
        or duration <= 0
        or fps is None
        or fps <= 0
        or width <= 0
        or height <= 0
    ):
        return None

    bits_per_pixel = MINIMUM_BITS_PER_PIXEL.get(encoder)

    if bits_per_pixel is None:
        return None

    minimum_video_bitrate = int(width * height * fps * bits_per_pixel)

    minimum_size_mb = (
        (minimum_video_bitrate + TARGET_AUDIO_BITRATE)
        * duration
        / 8
        / 1_000_000
        / (1 - CONTAINER_OVERHEAD_RATIO)
    )

    return minimum_size_mb


def calculate_recommended_target_size_mb(
    duration,
    width,
    height,
    fps,
    encoder,
):
    """
    Estimate a target size likely to provide reasonable visual quality.

    This is used by automatic presets and does not prevent users from
    manually selecting more aggressive compression settings.
    """

    if (
        duration is None
        or duration <= 0
        or fps is None
        or fps <= 0
        or width <= 0
        or height <= 0
    ):
        return None

    bits_per_pixel = (
        RECOMMENDED_BITS_PER_PIXEL.get(encoder)
    )

    if bits_per_pixel is None:
        return None

    recommended_video_bitrate = int(
        width
        * height
        * fps
        * bits_per_pixel
    )

    recommended_video_bitrate = max(
        recommended_video_bitrate,
        MINIMUM_VIDEO_BITRATE,
    )

    recommended_size_mb = (
        (
            recommended_video_bitrate
            + TARGET_AUDIO_BITRATE
        )
        * duration
        / 8
        / 1_000_000
        / (1 - CONTAINER_OVERHEAD_RATIO)
    )

    return recommended_size_mb


def calculate_estimated_quality_size_mb(
    duration,
    width,
    height,
    fps,
    encoder,
    quality,
):
    """Estimate output size from quality settings using a CRF bitrate heuristic."""

    if (
        duration is None
        or duration <= 0
        or fps is None
        or fps <= 0
        or width <= 0
        or height <= 0
    ):
        return None

    recommended_bits_per_pixel = RECOMMENDED_BITS_PER_PIXEL.get(encoder)

    if recommended_bits_per_pixel is None:
        return None

    if (
        encoder == "h264_nvenc"
        and quality > NVENC_HIGH_QUALITY_REFERENCE
    ):
        quality_multiplier = 2 ** (
            (
                NVENC_HIGH_QUALITY_REFERENCE
                - QUALITY_ESTIMATE_REFERENCE
            )
            / CRF_BITRATE_STEP
        ) * 2 ** (
            (quality - NVENC_HIGH_QUALITY_REFERENCE)
            / NVENC_HIGH_QUALITY_BITRATE_STEP
        )

    else:
        quality_multiplier = 2 ** (
            (quality - QUALITY_ESTIMATE_REFERENCE)
            / CRF_BITRATE_STEP
        )

    estimated_video_bitrate = max(
        1,
        int(
            width
            * height
            * fps
            * recommended_bits_per_pixel
            * quality_multiplier
        ),
    )

    return QUALITY_ESTIMATE_SCALE * (
        (estimated_video_bitrate + QUALITY_AUDIO_BITRATE)
        * duration
        / 8
        / 1_000_000
        / (1 - CONTAINER_OVERHEAD_RATIO)
    )


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

    if isinstance(target_size_mb, bool) or not isinstance(
        target_size_mb,
        (int, float),
    ):
        raise TypeError("Target file size must be a number.")

    if target_size_mb <= 0:
        raise ValueError("Target file size must be greater than zero.")

    if duration <= 0:
        raise ValueError("The video duration must be greater than zero.")

    # Aim slightly below the upload limit to allow for bitrate
    # variation and MP4 metadata.
    safe_target_size_mb = (
        target_size_mb
        * TARGET_SIZE_SAFETY_RATIO
    )

    target_bits = (
        safe_target_size_mb
        * 1_000_000
        * 8
    )

    usable_bits = target_bits * (1 - CONTAINER_OVERHEAD_RATIO)

    total_bitrate = usable_bits / duration

    video_bitrate = int(total_bitrate - TARGET_AUDIO_BITRATE)

    if video_bitrate < MINIMUM_VIDEO_BITRATE:
        minimum_size_mb = (
            (MINIMUM_VIDEO_BITRATE + TARGET_AUDIO_BITRATE)
            * duration
            / 8
            / 1_000_000
            / (1 - CONTAINER_OVERHEAD_RATIO)
        )

        raise ValueError(
            "The selected target size is too small "
            "for this video's duration.\n\n"
            f"Try at least {minimum_size_mb:.1f} MB."
        )

    minimum_target_size_mb = calculate_minimum_target_size_mb(
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        encoder=encoder,
    )

    if (
        encoder in ENFORCED_MINIMUM_ENCODERS
        and minimum_target_size_mb is not None
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
        raise ValueError(f"Unknown encoder: {encoder}")

    if speed not in ENCODING_SPEEDS:
        raise ValueError(f"Unknown encoding speed: {speed}")

    if isinstance(quality, bool) or not isinstance(quality, int):
        raise TypeError("Quality must be a whole number.")

    if not 1 <= quality <= 51:
        raise ValueError("Quality must be between 1 and 51.")

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

        if vendor == "nvidia" or vendor == "amd":
            arguments.extend(
                [
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
                ]
            )

        else:
            # CPU and Intel encoders accept FFmpeg's generic
            # bitrate constraint options.
            arguments.extend(
                [
                    "-b:v",
                    bitrate,
                    "-maxrate",
                    bitrate,
                    "-bufsize",
                    buffer_size,
                ]
            )

        return arguments

    # ffupscale presents larger values as better quality. FFmpeg's CRF,
    # CQ and QP systems generally use smaller values for better quality.
    ffmpeg_quality = 52 - quality

    if vendor == "cpu":
        arguments.extend(
            [
                "-crf",
                str(ffmpeg_quality),
            ]
        )

    elif vendor == "nvidia":
        arguments.extend(
            [
                "-rc",
                "vbr",
                "-cq",
                str(ffmpeg_quality),
                "-b:v",
                "0",
            ]
        )

    elif vendor == "amd":
        arguments.extend(
            [
                "-rc",
                "cqp",
                "-qp_i",
                str(ffmpeg_quality),
                "-qp_p",
                str(ffmpeg_quality),
            ]
        )

    elif vendor == "intel":
        arguments.extend(
            [
                "-global_quality",
                str(ffmpeg_quality),
            ]
        )

    else:
        raise ValueError(f"Unsupported encoder vendor: {vendor}")

    return arguments


# -- FFmpeg Command --


def get_audio_stream_codecs(input_path):
    """Return the codec name for each audio stream in the input."""

    ffprobe_path = find_ffprobe()

    result = subprocess.run(
        [
            ffprobe_path,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "json",
            str(input_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        creationflags=hidden_process_flags(),
    )

    probe_data = json.loads(result.stdout)

    return [
        stream.get("codec_name")
        for stream in probe_data.get("streams", [])
    ]


def calculate_gif_palette_colors(
    quality,
    target_size_mb=None,
    width=None,
    height=None,
    duration=None,
    fps=None,
):
    """Choose GIF palette colors from quality or a best-effort size target."""

    if target_size_mb is None:
        if isinstance(quality, bool) or not isinstance(quality, int):
            raise TypeError("GIF quality must be a whole number.")

        if not 1 <= quality <= 51:
            raise ValueError("GIF quality must be between 1 and 51.")

        return 2 + round((quality - 1) * 254 / 50)

    if target_size_mb <= 0:
        raise ValueError("Target file size must be greater than zero.")

    if (
        width is None
        or height is None
        or duration is None
        or fps is None
        or width <= 0
        or height <= 0
        or duration <= 0
        or fps <= 0
    ):
        raise ValueError(
            "Resolution, duration and frame rate are required "
            "for GIF target-size mode."
        )

    # GIFs do not support bitrate control. Estimate the unconstrained output
    # from the pixel-frame count, then reduce palette depth toward the target.
    estimated_full_palette_mb = (
        width * height * duration * fps * 0.20 / 1_000_000
    )
    target_ratio = min(
        1.0,
        target_size_mb / estimated_full_palette_mb,
    )
    palette_colors = round(2 ** (1 + 7 * target_ratio))

    return max(2, min(256, palette_colors))


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
    trim_start=0.0,
    trim_end=None,
    merge_audio_tracks=False,
    output_format="mp4",
    gif_dither="sierra2_4a",
    audio_stream_codecs=None,
):
    """
    Validate the settings and build an FFmpeg command.
    This function does not run FFmpeg.
    """

    ffmpeg_path = find_ffmpeg()

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_format = str(output_format).lower()

    if output_format not in {"mp4", "gif", "mkv"}:
        raise ValueError(f"Unsupported output format: {output_format}")

    if output_path.suffix.lower() != f".{output_format}":
        raise ValueError(
            f"The output path must use the .{output_format} extension."
        )

    if not input_path.is_file():
        raise FileNotFoundError(f"Input video does not exist:\n{input_path}")

    if input_path.resolve() == output_path.resolve():
        raise ValueError("The output path cannot be the same as the input path.")

    if width <= 0 or height <= 0:
        raise ValueError("Width and height must be greater than zero.")

    if width % 2 != 0 or height % 2 != 0:
        raise ValueError("Width and height must both be even numbers.")

    if output_format != "gif" and encoder not in SUPPORTED_ENCODERS:
        raise ValueError(f"Unknown encoder: {encoder}")

    if output_format != "gif" and preset not in ENCODING_SPEEDS:
        raise ValueError(f"Unknown encoding speed: {preset}")

    if fps is not None and fps <= 0:
        raise ValueError("FPS must be greater than zero.")

    if rate_control not in {
        "quality",
        "target_size",
    }:
        raise ValueError(f"Unknown rate-control mode: {rate_control}")

    # -- Trim Validation --

    if trim_start < 0:
        raise ValueError(
            "The trim start cannot be negative."
        )

    if duration is not None:
        if trim_start >= duration:
            raise ValueError(
                "The trim start must be inside the video."
            )

        if (
            trim_end is not None
            and trim_end > duration
        ):
            raise ValueError(
                "The trim end cannot exceed the video duration."
            )

    if (
        trim_end is not None
        and trim_end <= trim_start
    ):
        raise ValueError(
            "The trim end must be after the trim start."
        )

    selected_duration = None

    if duration is not None:
        end_time = (
            trim_end
            if trim_end is not None
            else duration
        )

        selected_duration = (
            end_time - trim_start
        )

    if output_format == "gif":
        if rate_control == "target_size" and target_size_mb is None:
            raise ValueError("Enter a target file size.")

        gif_fps = fps if fps is not None else source_fps
        palette_colors = calculate_gif_palette_colors(
            quality=quality,
            target_size_mb=(
                target_size_mb
                if rate_control == "target_size"
                else None
            ),
            width=width,
            height=height,
            duration=selected_duration,
            fps=gif_fps,
        )

        if gif_dither not in {"sierra2_4a", "bayer", "none"}:
            raise ValueError(f"Unsupported GIF dithering mode: {gif_dither}")

        input_arguments = []

        if trim_start > 0:
            input_arguments.extend(["-ss", str(trim_start)])

        input_arguments.extend(["-i", str(input_path)])

        if selected_duration is not None and (
            trim_start > 0 or trim_end is not None
        ):
            input_arguments.extend(["-t", str(selected_duration)])

        video_filters = []

        if fps is not None:
            video_filters.append(f"fps={fps}")

        video_filters.extend([
            f"scale={width}:{height}:flags=lanczos",
            "split[gif_palette_source][gif_output_source]",
        ])

        filter_graph = (
            "[0:v:0]"
            + ",".join(video_filters)
            + (
                f";[gif_palette_source]trim=duration="
                f"{GIF_PALETTE_SAMPLE_DURATION},"
            )
            + (
                f"palettegen=max_colors={palette_colors}:"
                "stats_mode=diff[gif_palette]"
            )
            + ";[gif_output_source][gif_palette]"
            + (
                f"paletteuse=dither={gif_dither}:"
                "diff_mode=rectangle[gif_output]"
            )
        )

        arguments = [
            "-progress",
            "pipe:1",
            "-nostats",
            "-hide_banner",
            "-n",
            *input_arguments,
            "-filter_complex",
            filter_graph,
            "-map",
            "[gif_output]",
            "-an",
            "-loop",
            "0",
            "-f",
            "gif",
            str(output_path),
        ]

        return ffmpeg_path, arguments

    video_bitrate = None

    if rate_control == "target_size":
        if target_size_mb is None:
            raise ValueError("Enter a target file size.")

        if selected_duration is None:
            raise ValueError("Video duration is required for target-size mode.")

        effective_fps = fps if fps is not None else source_fps

        if effective_fps is None or effective_fps <= 0:
            raise ValueError(
                "The source frame rate is required for target-size validation."
            )

        video_bitrate = calculate_target_video_bitrate(
            target_size_mb=target_size_mb,
            duration=selected_duration,
            width=width,
            height=height,
            fps=effective_fps,
            encoder=encoder,
        )

    video_encoder_arguments = build_video_encoder_arguments(
        encoder=encoder,
        quality=quality,
        speed=preset,
        video_bitrate=video_bitrate,
    )

    if audio_stream_codecs is None:
        audio_stream_codecs = get_audio_stream_codecs(input_path)

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
        # Convert the source audio to AAC for reliable MP4 playback.
        # WebM files commonly contain Opus audio, which Discord may not
        # recognise as an inline-playable MP4.
        audio_arguments = [
            "-c:a",
            "aac",
            "-b:a",
            "192k",
        ]

    # Copy AAC streams to retain their original bitrate and avoid
    # unnecessary lossy re-encoding. Other formats are converted to AAC
    # for compatibility with the MP4 output.
    for audio_index, codec in enumerate(audio_stream_codecs):
        if not merge_audio_tracks and codec == "aac":
            audio_arguments.extend(
                [
                    f"-c:a:{audio_index}",
                    "copy",
                ]
            )

    # Seeking before the input lets FFmpeg reach the selected
    # starting position efficiently. Because the video is then
    # re-encoded, FFmpeg can still produce an accurate start point.

    input_arguments = []

    if trim_start > 0:
        input_arguments.extend([
            "-ss",
            str(trim_start),
        ])

    input_arguments.extend([
        "-i",
        str(input_path),
    ])

    if selected_duration is not None and (
        trim_start > 0
        or trim_end is not None
    ):
        input_arguments.extend([
            "-t",
            str(selected_duration),
        ])

    arguments = [
        # Send machine-readable progress to stdout for the Qt progress bar.
        "-progress",
        "pipe:1",
        "-nostats",
        "-hide_banner",
        # Refuse to overwrite an existing output.
        "-n",
        # Input and optional trim range
        *input_arguments,
        # Upscaling
        "-vf",
        f"scale={width}:{height}:flags=lanczos",
        # Encoder-specific codec, quality and speed options
        *video_encoder_arguments,
        # Broad playback compatibility
        "-pix_fmt",
        "yuv420p",
    ]

    if merge_audio_tracks and len(audio_stream_codecs) > 1:
        # Mix every input audio stream into one AAC track.
        audio_filter = (
            "".join(
                f"[0:a:{audio_index}]"
                for audio_index in range(len(audio_stream_codecs))
            )
            + (
                f"amix=inputs={len(audio_stream_codecs)}:"
                "duration=longest[aout]"
            )
        )

        arguments.extend(
            [
                "-filter_complex",
                audio_filter,
                "-map",
                "0:v:0",
                "-map",
                "[aout]",
            ]
        )

        # Mixing requires encoding the combined audio stream.
        arguments.extend(audio_arguments)

    else:
        # Copy audio in quality mode or use a predictable bitrate
        # when targeting a file size.
        arguments.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                *audio_arguments,
            ]
        )

    if output_format == "mp4":
        arguments.extend(
            [
                # Make MP4 begin playback sooner when streamed
                "-movflags",
                "+faststart",
            ]
        )

    # hvc1 improves H.265 recognition in Apple players and devices.
    if (
        output_format == "mp4"
        and ENCODER_PROFILES[encoder]["codec"] == "h265"
    ):
        arguments.extend(
            [
                "-tag:v",
                "hvc1",
            ]
        )

    if fps is not None:
        arguments.extend(["-r", str(fps)])

    arguments.append(str(output_path))

    return ffmpeg_path, arguments
