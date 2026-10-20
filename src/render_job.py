from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from uuid import uuid4

# -- Render Status --


class RenderStatus(str, Enum):
    """Possible states for a queued render."""

    WAITING = "Waiting"
    RENDERING = "Rendering"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


# -- Render Job --


@dataclass
class RenderJob:
    """Store everything required to render one video."""

    input_path: Path
    output_path: Path
    width: int
    height: int
    quality: int
    rate_control: str
    target_size_mb: float | None
    fps: float | None
    encoder: str
    preset: str
    source_duration: float
    source_fps: float
    trim_start: float = 0.0
    trim_end: float | None = None
    merge_audio_tracks: bool = False
    output_format: str = "mp4"
    gif_dither: str = "sierra2_4a"

    job_id: str = field(default_factory=lambda: uuid4().hex)
    status: RenderStatus = RenderStatus.WAITING
    progress: int = 0
    error_message: str | None = None
    _progress_fraction: float = field(default=0.0, init=False, repr=False)
    _render_started_at: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Normalize paths and validate the selected trim range."""

        self.input_path = Path(self.input_path)
        self.output_path = Path(self.output_path)
        self.output_format = str(self.output_format).lower()

        if self.output_format not in {"mp4", "gif", "mkv"}:
            raise ValueError(
                f"Unsupported output format: {self.output_format}"
            )

        self.source_duration = float(
            self.source_duration
        )

        self.trim_start = float(
            self.trim_start
        )

        if self.trim_end is not None:
            self.trim_end = float(
                self.trim_end
            )

        if self.source_duration <= 0:
            raise ValueError(
                "The source duration must be greater than zero."
            )

        if (
            self.trim_start < 0
            or self.trim_start >= self.source_duration
        ):
            raise ValueError(
                "The trim start must be inside the video."
            )

        if self.trim_end is not None:
            if self.trim_end <= self.trim_start:
                raise ValueError(
                    "The trim end must be after the trim start."
                )

            if self.trim_end > self.source_duration:
                raise ValueError(
                    "The trim end cannot exceed the video duration."
                )

    @classmethod
    def from_settings(
        cls,
        input_path,
        duration,
        settings,
        source_fps,
    ):
        """Create a job from settings collected by SettingsPage."""

        width, height = settings["resolution"]

        trim_start = settings.get(
            "trim_start",
            0.0,
        )

        trim_end = settings.get(
            "trim_end",
        )

        return cls(
            input_path=Path(input_path),
            output_path=Path(settings["output_path"]),
            width=width,
            height=height,
            quality=settings["quality"],
            rate_control=settings["rate_control"],
            target_size_mb=settings["target_size_mb"],
            fps=settings["fps"],
            encoder=settings["encoder"],
            preset=settings["preset"],
            source_duration=duration,
            source_fps=source_fps,
            trim_start=trim_start,
            trim_end=trim_end,
            merge_audio_tracks=settings.get(
                "merge_audio_tracks",
                False,
            ),
            output_format=settings.get(
                "output_format",
                "mp4",
            ),
            gif_dither=settings.get(
                "gif_dither",
                "sierra2_4a",
            ),
        )

    # -- Display Helpers --

    @staticmethod
    def format_timecode(seconds):
        """Format seconds as HH:MM:SS.mmm."""

        total_milliseconds = max(
            0,
            round(float(seconds) * 1000),
        )

        total_seconds, milliseconds = divmod(
            total_milliseconds,
            1000,
        )

        hours, remainder = divmod(
            total_seconds,
            3600,
        )

        minutes, seconds = divmod(
            remainder,
            60,
        )

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds:02d}."
            f"{milliseconds:03d}"
        )

    @property
    def trim_range_text(self):
        """Describe the range stored by this job."""

        duration_text = self.format_timecode(
            self.duration
        )

        if (
            self.trim_start == 0
            and self.trim_end is None
        ):
            return (
                f"Full video · {duration_text}"
            )

        end_time = (
            self.trim_end
            if self.trim_end is not None
            else self.source_duration
        )

        start_text = self.format_timecode(
            self.trim_start
        )

        end_text = self.format_timecode(
            end_time
        )

        return (
            f"{start_text}–{end_text}"
            f" · {duration_text}"
        )

    @property
    def duration(self):
        """Return the duration that FFmpeg will render."""

        end_time = (
            self.trim_end
            if self.trim_end is not None
            else self.source_duration
        )

        return end_time - self.trim_start

    @property
    def filename(self):
        """Return the input filename for display in the queue."""

        return self.input_path.name

    @property
    def resolution_text(self):
        return f"{self.width} × {self.height}"

    @property
    def remaining_time_text(self):
        """Return a live render-time estimate suitable for progress displays."""

        if self.status != RenderStatus.RENDERING:
            return None

        if self._progress_fraction >= 1:
            return "Finalizing..."

        if (
            self._render_started_at is None
            or self._progress_fraction < 0.01
        ):
            return "Estimating remaining time..."

        elapsed = time.monotonic() - self._render_started_at

        if elapsed < 3:
            return "Estimating remaining time..."

        remaining_seconds = (
            elapsed
            * (1 - self._progress_fraction)
            / self._progress_fraction
        )
        return f"About {self.format_remaining_time(remaining_seconds)} remaining"

    @staticmethod
    def format_remaining_time(seconds):
        """Format an estimated duration as compact hours, minutes and seconds."""

        total_seconds = max(1, round(seconds))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours}h {minutes}m"

        if minutes:
            return f"{minutes}m {seconds}s"

        return f"{seconds}s"

    def set_progress(self, percentage):
        """Store progress as a value between 0 and 100."""

        self._progress_fraction = max(0.0, min(100.0, float(percentage))) / 100
        self.progress = max(
            0,
            min(100, int(percentage)),
        )

    # -- Status Updates --

    def mark_waiting(self):
        self.status = RenderStatus.WAITING
        self.progress = 0
        self._progress_fraction = 0.0
        self._render_started_at = None
        self.error_message = None

    def mark_rendering(self):
        self.status = RenderStatus.RENDERING
        self.progress = 0
        self._progress_fraction = 0.0
        self._render_started_at = time.monotonic()
        self.error_message = None

    def mark_completed(self):
        self.status = RenderStatus.COMPLETED
        self.progress = 100
        self._progress_fraction = 1.0
        self._render_started_at = None
        self.error_message = None

    def mark_failed(self, message):
        self.status = RenderStatus.FAILED
        self.error_message = str(message)

    def mark_cancelled(self):
        self.status = RenderStatus.CANCELLED
        self.error_message = None
