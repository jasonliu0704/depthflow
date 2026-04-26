from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Annotated, Callable

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from depthflow_api.jobs import JobManager
from depthflow_api.models import (
    JobCreatedResponse,
    RenderMode,
    JobState,
    JobStatus,
    OutputTarget,
    RenderRequest,
)
from depthflow_api.renderer import ZoomBatchRenderer
from depthflow_api.storage import AzureBlobStorage

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


def default_workdir() -> Path:
    root = os.getenv("DEPTHFLOW_API_WORKDIR", ".depthflow-api")
    return Path(root).expanduser().resolve()


def default_output_target() -> OutputTarget:
    value = os.getenv("DEPTHFLOW_API_DEFAULT_OUTPUT_TARGET", OutputTarget.local.value)
    try:
        return OutputTarget(value)
    except ValueError as exc:
        raise RuntimeError(
            "DEPTHFLOW_API_DEFAULT_OUTPUT_TARGET must be either 'local' or 'azure'"
        ) from exc


def create_app(
    *,
    jobs: JobManager | None = None,
    renderer: ZoomBatchRenderer | None = None,
    storage_factory: Callable[[], AzureBlobStorage] | None = None,
) -> FastAPI:
    app = FastAPI(title="DepthFlow Batch API", version="0.1.0")
    job_manager = jobs or JobManager(default_workdir())
    zoom_renderer = renderer or ZoomBatchRenderer()
    storage_factory = storage_factory or AzureBlobStorage.from_env

    @app.post("/jobs/zoom-batch", response_model=JobCreatedResponse)
    async def create_zoom_batch_job(
        images: Annotated[list[UploadFile], File(...)],
        clip_duration_seconds: Annotated[float, Form()] = 5.0,
        fps: Annotated[int, Form()] = 30,
        width: Annotated[int | None, Form()] = None,
        height: Annotated[int | None, Form()] = None,
        mode: Annotated[RenderMode, Form()] = RenderMode.tour,
        quality: Annotated[int | None, Form()] = None,
        ssaa: Annotated[float | None, Form()] = None,
        output_name: Annotated[str, Form()] = "final.mp4",
        output_target: Annotated[OutputTarget | None, Form()] = None,
    ) -> JobCreatedResponse:
        if not images:
            raise HTTPException(status_code=400, detail="At least one image is required")
        if clip_duration_seconds <= 0:
            raise HTTPException(status_code=400, detail="clip_duration_seconds must be positive")
        if fps <= 0:
            raise HTTPException(status_code=400, detail="fps must be positive")
        if width is not None and width <= 0:
            raise HTTPException(status_code=400, detail="width must be positive")
        if height is not None and height <= 0:
            raise HTTPException(status_code=400, detail="height must be positive")
        if quality is not None and not 0 <= quality <= 100:
            raise HTTPException(status_code=400, detail="quality must be between 0 and 100")
        if ssaa is not None and ssaa <= 0:
            raise HTTPException(status_code=400, detail="ssaa must be positive")

        resolved_output_target = output_target or default_output_target()
        safe_output_name = _normalize_output_name(output_name)
        if resolved_output_target == OutputTarget.azure:
            _ = storage_factory()
        for index, upload in enumerate(images):
            _validate_upload(index, upload)

        state = job_manager.create_job(
            total_images=len(images),
            output_name=safe_output_name,
            output_target=resolved_output_target,
        )
        final_output_path = _resolve_final_output_path(
            output_name=output_name,
            output_target=resolved_output_target,
            job_dir=job_manager.job_dir(state.job_id),
        )
        job_manager.update_job(
            state.job_id,
            local_video_path=str(final_output_path) if resolved_output_target == OutputTarget.local else None,
        )
        uploads_dir = job_manager.uploads_dir(state.job_id)
        saved_images = []
        for index, upload in enumerate(images):
            saved_images.append(await _save_upload(uploads_dir, index, upload))

        render_request = RenderRequest(
            image_paths=saved_images,
            clip_duration_seconds=clip_duration_seconds,
            fps=fps,
            width=width,
            height=height,
            mode=mode,
            quality=quality,
            ssaa=ssaa,
            output_name=safe_output_name,
            output_path=final_output_path,
            output_target=resolved_output_target,
        )

        def worker() -> None:
            try:
                job_manager.update_job(
                    state.job_id,
                    status=JobStatus.running,
                    current_step="starting render",
                )
                final_path = zoom_renderer.render_batch(
                    render_request,
                    job_manager.job_dir(state.job_id),
                    progress=lambda rendered_images, current_step: job_manager.update_job(
                        state.job_id,
                        rendered_images=rendered_images,
                        current_step=current_step,
                    ),
                )
                final_url = f"/files/{state.job_id}/{state.output_name}"
                if resolved_output_target == OutputTarget.azure:
                    blob_name = f"depthflow/jobs/{state.job_id}/{state.output_name}"
                    final_url = storage_factory().upload_file(final_path, blob_name)
                job_manager.update_job(
                    state.job_id,
                    status=JobStatus.completed,
                    rendered_images=len(render_request.image_paths),
                    current_step="completed",
                    final_video_url=final_url,
                    local_video_path=str(final_path.resolve()),
                )
            except Exception as exc:  # pragma: no cover - exercised in integration tests
                job_manager.update_job(
                    state.job_id,
                    status=JobStatus.failed,
                    current_step="failed",
                    error=str(exc),
                )

        job_manager.start_job(state.job_id, worker)
        return JobCreatedResponse(
            job_id=state.job_id,
            status=state.status,
            status_url=state.status_url,
        )

    @app.get("/jobs/{job_id}", response_model=JobState)
    def get_job(job_id: str) -> JobState:
        if state := job_manager.get_job(job_id):
            return state
        raise HTTPException(status_code=404, detail="Job not found")

    @app.get("/files/{job_id}/{filename}")
    def get_output_file(job_id: str, filename: str) -> FileResponse:
        state = job_manager.get_job(job_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if filename != state.output_name:
            raise HTTPException(status_code=404, detail="File not found")
        file_path = Path(state.local_video_path) if state.local_video_path else job_manager.job_dir(job_id) / state.output_name
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path=file_path, media_type="video/mp4", filename=state.output_name)

    return app


async def _save_upload(uploads_dir: Path, index: int, upload: UploadFile) -> Path:
    filename = _validate_upload(index, upload)

    target = uploads_dir / f"{index:03d}-{filename.name}"
    with target.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)
    return target


def _validate_upload(index: int, upload: UploadFile) -> Path:
    filename = Path(upload.filename or f"image-{index}.bin")
    suffix = filename.suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {suffix or 'unknown'}")
    if upload.content_type and not upload.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {upload.content_type}")
    return filename


def _normalize_output_name(output_name: str) -> str:
    name = Path(output_name).name or "final.mp4"
    if not name.lower().endswith(".mp4"):
        name = f"{name}.mp4"
    return name


def _resolve_final_output_path(output_name: str, output_target: OutputTarget, job_dir: Path) -> Path:
    normalized_name = _normalize_output_name(output_name)

    if output_target == OutputTarget.azure:
        return (job_dir / normalized_name).resolve()

    candidate = Path(output_name).expanduser()
    if output_name.strip() and (candidate.is_absolute() or len(candidate.parts) > 1):
        if candidate.suffix.lower() != ".mp4":
            candidate = candidate.with_suffix(".mp4")
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        else:
            candidate = candidate.resolve()
        return candidate

    return (job_dir / normalized_name).resolve()


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("depthflow_api.app:app", host="0.0.0.0", port=8000, reload=False)
