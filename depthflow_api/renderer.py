from __future__ import annotations

import contextlib
import gc
import math
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import MethodType
from typing import Callable

from depthflow_api.models import RenderRequest

ProgressCallback = Callable[[int, str], None]
BACKGROUND_MUSIC_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac"}


class ZoomBatchRenderer:
    def __init__(self, background_music_dir: Path | None = None) -> None:
        self.background_music_dir = (
            Path(background_music_dir)
            if background_music_dir is not None
            else Path(__file__).resolve().parent.parent / "background-musics"
        )

    @staticmethod
    def _apply_resize_compat(scene) -> None:
        original_resize = scene.resize

        def compat_resize(self, *args, **kwargs):
            if args:
                if len(args) > 2:
                    raise TypeError("resize accepts at most width and height as positional arguments")
                if "width" not in kwargs and len(args) >= 1:
                    kwargs["width"] = args[0]
                if "height" not in kwargs and len(args) >= 2:
                    kwargs["height"] = args[1]
            return original_resize(**kwargs)

        scene.resize = MethodType(compat_resize, scene)

    def render_batch(
        self,
        request: RenderRequest,
        job_dir: Path,
        progress: ProgressCallback,
    ) -> Path:
        clips_dir = job_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        clip_paths: list[Path] = []
        for index, image_path in enumerate(request.image_paths):
            progress(index, f"rendering clip {index + 1} of {len(request.image_paths)}")
            clip_path = clips_dir / f"{index:03d}-{image_path.stem}.mp4"
            self.render_single(image_path=image_path, output_path=clip_path, request=request)
            clip_paths.append(clip_path)
            progress(index + 1, f"rendered clip {index + 1} of {len(request.image_paths)}")

        progress(len(clip_paths), "stitching clips")
        manifest = self.write_concat_manifest(clip_paths, job_dir / "concat.txt")
        final_path = request.output_path or (job_dir / request.output_name)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        background_music = self.choose_background_music()
        if background_music is None:
            self.concat_videos(manifest, final_path)
            progress(len(clip_paths), "completed local render")
            return final_path

        with tempfile.NamedTemporaryFile(
            prefix="depthflow-stitch-",
            suffix=".mp4",
            dir=job_dir,
            delete=False,
        ) as handle:
            stitched_path = Path(handle.name)

        try:
            self.concat_videos(manifest, stitched_path)
            progress(len(clip_paths), f"adding background music: {background_music.name}")
            self.add_background_music(stitched_path, background_music, final_path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                stitched_path.unlink()

        progress(len(clip_paths), "completed local render")
        return final_path

    def render_single(self, image_path: Path, output_path: Path, request: RenderRequest) -> None:
        from depthflow.scene import DepthScene
        from shaderflow.scene import WindowBackend

        class HouseTourRenderScene(DepthScene):
            def update(self) -> None:
                DepthScene.update(self)
                # A subtle lateral slide feels closer to a real interior walkthrough
                # than a straight promo-style zoom-in.
                self.state.offset = (0.12 * math.sin(self.cycle), 0.0)
                self.state.zoom = 0.98 + 0.04 * (1 - math.cos(self.cycle)) / 2

        scene = HouseTourRenderScene(backend=WindowBackend.Headless)
        try:
            self._apply_resize_compat(scene)
            scene.initialize()
            scene.input(image=image_path)

            main_kwargs = {
                "output": output_path,
                "fps": request.fps,
                "time": request.clip_duration_seconds,
            }
            if request.width is not None:
                main_kwargs["width"] = request.width
            if request.height is not None:
                main_kwargs["height"] = request.height

            scene.main(**main_kwargs)
        finally:
            self._cleanup_scene(scene)

    @staticmethod
    def _cleanup_scene(scene) -> None:
        """Release GPU resources before ModernGL falls back to destructor cleanup.

        ShaderFlow currently relies on object finalizers during interpreter shutdown.
        On macOS that can crash inside `glDeleteTextures` if the OpenGL context has
        already been torn down. Releasing resources deterministically keeps the API
        process alive after a successful render.
        """
        context = getattr(scene, "opengl", None)
        window = getattr(scene, "window", None)

        if context is not None:
            with contextlib.suppress(Exception):
                context.gc_mode = "context_gc"

        for module in list(getattr(scene, "modules", []) or []):
            destroy = getattr(module, "destroy", None)
            if destroy is None:
                continue
            with contextlib.suppress(Exception):
                destroy()

        if context is not None:
            with contextlib.suppress(Exception):
                context.gc()

        with contextlib.suppress(Exception):
            scene.modules = []
        for attr in ("shader", "_final", "frametimer", "keyboard", "camera"):
            with contextlib.suppress(Exception):
                setattr(scene, attr, None)

        if window is not None:
            with contextlib.suppress(Exception):
                window.destroy()
        if context is not None:
            with contextlib.suppress(Exception):
                context.release()

        with contextlib.suppress(Exception):
            scene.window = None
        with contextlib.suppress(Exception):
            scene.opengl = None

        gc.collect()

    def write_concat_manifest(self, clip_paths: list[Path], manifest_path: Path) -> Path:
        lines = [f"file '{self._ffmpeg_escape(path.resolve())}'" for path in clip_paths]
        manifest_path.write_text("\n".join(lines) + "\n")
        return manifest_path

    def concat_videos(self, manifest_path: Path, output_path: Path) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg executable was not found on PATH")

        process = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest_path),
                "-c",
                "copy",
                str(output_path),
            ],
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip() or "ffmpeg concat failed")

    def background_music_paths(self) -> list[Path]:
        if not self.background_music_dir.exists():
            return []
        return sorted(
            path
            for path in self.background_music_dir.iterdir()
            if path.is_file() and path.suffix.lower() in BACKGROUND_MUSIC_EXTENSIONS
        )

    def choose_background_music(self) -> Path | None:
        candidates = self.background_music_paths()
        if not candidates:
            return None
        return random.choice(candidates)

    def add_background_music(self, video_path: Path, music_path: Path, output_path: Path) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg executable was not found on PATH")

        process = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(video_path),
                "-stream_loop",
                "-1",
                "-i",
                str(music_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-af",
                "volume=0.18",
                "-shortest",
                str(output_path),
            ],
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            raise RuntimeError(process.stderr.strip() or "ffmpeg audio mux failed")

    @staticmethod
    def _ffmpeg_escape(path: Path) -> str:
        return str(path).replace("'", "'\\''")
