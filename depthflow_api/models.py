from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    failed = "failed"
    completed = "completed"


class OutputTarget(str, Enum):
    local = "local"
    azure = "azure"


class RenderRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    image_paths: list[Path]
    clip_duration_seconds: float = Field(default=5.0, gt=0)
    fps: int = Field(default=30, gt=0)
    width: Optional[int] = Field(default=None, gt=0)
    height: Optional[int] = Field(default=None, gt=0)
    output_name: str = Field(default="final.mp4", min_length=1)
    output_path: Optional[Path] = None
    output_target: OutputTarget = OutputTarget.local


class JobState(BaseModel):
    job_id: str
    status: JobStatus
    status_url: str
    total_images: int
    rendered_images: int = 0
    current_step: str = "queued"
    output_name: str = "final.mp4"
    output_target: OutputTarget = OutputTarget.local
    final_video_url: Optional[str] = None
    local_video_path: Optional[str] = None
    error: Optional[str] = None


class JobCreatedResponse(BaseModel):
    job_id: str
    status: JobStatus
    status_url: str
