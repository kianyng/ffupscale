from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4


class RenderStatus(str, Enum):
    """Possible states for a queued render."""

    WAITING = "Waiting"
    RENDERING = "Rendering"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


@dataclass
class RenderJob:
    """Store everything required to render one video."""

    input_path: Path
    output_path: Path
    width: int
    height: int
    quality: int
    fps: Optional[float]
    encoder: str
    preset: str
    duration: float

    job_id: str = field(
        default_factory=lambda: uuid4().hex
    )
    status: RenderStatus = RenderStatus.WAITING
    progress: int = 0
    error_message: Optional[str] = None

    def __post_init__(self):
        self.input_path = Path(self.input_path)
        self.output_path = Path(self.output_path)

    @classmethod
    def from_settings(
        cls,
        input_path,
        duration,
        settings,
    ):
        """Create a job from settings collected by SettingsPage."""

        width, height = settings["resolution"]

        return cls(
            input_path=Path(input_path),
            output_path=Path(
                settings["output_path"]
            ),
            width=width,
            height=height,
            quality=settings["quality"],
            fps=settings["fps"],
            encoder=settings["encoder"],
            preset=settings["preset"],
            duration=duration,
        )

    @property
    def filename(self):
        """Return the input filename for display in the queue."""

        return self.input_path.name

    @property
    def resolution_text(self):
        return f"{self.width} × {self.height}"

    def set_progress(self, percentage):
        """Store progress as a value between 0 and 100."""

        self.progress = max(
            0,
            min(100, int(percentage)),
        )

    def mark_waiting(self):
        self.status = RenderStatus.WAITING
        self.progress = 0
        self.error_message = None

    def mark_rendering(self):
        self.status = RenderStatus.RENDERING
        self.progress = 0
        self.error_message = None

    def mark_completed(self):
        self.status = RenderStatus.COMPLETED
        self.progress = 100
        self.error_message = None

    def mark_failed(self, message):
        self.status = RenderStatus.FAILED
        self.error_message = str(message)

    def mark_cancelled(self):
        self.status = RenderStatus.CANCELLED
        self.error_message = None