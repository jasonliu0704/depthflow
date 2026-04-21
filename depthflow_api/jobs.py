from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Callable

from depthflow_api.models import JobState, JobStatus, OutputTarget


class JobManager:
    def __init__(self, workdir: Path) -> None:
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.RLock()

    def create_job(
        self,
        total_images: int,
        output_name: str,
        output_target: OutputTarget = OutputTarget.local,
    ) -> JobState:
        job_id = uuid.uuid4().hex
        status_url = f"/jobs/{job_id}"
        state = JobState(
            job_id=job_id,
            status=JobStatus.queued,
            status_url=status_url,
            total_images=total_images,
            output_name=output_name,
            output_target=output_target,
        )
        with self._lock:
            self._jobs[job_id] = state
        self.job_dir(job_id).mkdir(parents=True, exist_ok=True)
        self._persist(state)
        return state

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            if state := self._jobs.get(job_id):
                return state

        state_file = self.job_dir(job_id) / "status.json"
        if not state_file.exists():
            return None

        state = JobState.model_validate_json(state_file.read_text())
        with self._lock:
            self._jobs[job_id] = state
        return state

    def update_job(self, job_id: str, **changes) -> JobState:
        with self._lock:
            current = self._jobs[job_id]
            state = JobState.model_validate({
                **current.model_dump(mode="json"),
                **changes,
            })
            self._jobs[job_id] = state
        self._persist(state)
        return state

    def start_job(self, job_id: str, worker: Callable[[], None]) -> threading.Thread:
        thread = threading.Thread(target=worker, name=f"depthflow-job-{job_id}", daemon=True)
        thread.start()
        return thread

    def job_dir(self, job_id: str) -> Path:
        return self.workdir / job_id

    def uploads_dir(self, job_id: str) -> Path:
        path = self.job_dir(job_id) / "uploads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _persist(self, state: JobState) -> None:
        state_file = self.job_dir(state.job_id) / "status.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state.model_dump(mode="json"), indent=2))
