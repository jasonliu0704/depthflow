from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from depthflow_api.app import create_app
from depthflow_api.jobs import JobManager
from depthflow_api.models import OutputTarget, RenderMode, RenderRequest
from depthflow_api.renderer import ZoomBatchRenderer
from depthflow_api.storage import AzureBlobStorage
from depthflow_api.subtitles import write_srt
from depthflow_api.tts import SpeechSynthesisResult, WordBoundary


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00"
    b"\xc9\xfe\x92\xef"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class ImmediateJobManager(JobManager):
    def start_job(self, job_id, worker):
        worker()
        return threading.Thread()


class FakeRenderer(ZoomBatchRenderer):
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def render_batch(self, request: RenderRequest, job_dir: Path, progress):
        progress(0, "rendering")
        if self.should_fail:
            raise RuntimeError("render failed")
        output = request.output_path or (job_dir / request.output_name)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake-mp4")
        progress(len(request.image_paths), "completed local render")
        return output


class CapturingRenderer(FakeRenderer):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[RenderRequest] = []

    def render_batch(self, request: RenderRequest, job_dir: Path, progress):
        self.requests.append(request)
        return super().render_batch(request, job_dir, progress)


class FakeStorage:
    def __init__(self, url: str = "https://storage.example.com/depthflow/jobs/job/final.mp4") -> None:
        self.url = url

    def upload_file(self, local_path: Path, blob_name: str) -> str:
        assert local_path.exists()
        assert blob_name.startswith("depthflow/jobs/")
        return self.url


class FakeTextToSpeech:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Path, str | None]] = []

    def synthesize_to_file(
        self,
        text: str,
        output_path: Path,
        voice_name: str | None = None,
    ) -> SpeechSynthesisResult:
        self.calls.append((text, output_path, voice_name))
        output_path.write_bytes(b"speech")
        return SpeechSynthesisResult(
            audio_path=output_path,
            word_boundaries=[
                WordBoundary("Narrate", start=0.0, duration=0.2),
                WordBoundary("this", start=0.2, duration=0.2),
                WordBoundary("video.", start=0.4, duration=0.2, is_sentence_end=True),
            ],
        )


@pytest.fixture
def client(tmp_path: Path):
    jobs = ImmediateJobManager(tmp_path)
    app = create_app(
        jobs=jobs,
        renderer=FakeRenderer(),
        storage_factory=lambda: FakeStorage(),
    )
    return TestClient(app)


def test_rejects_unsupported_upload_type(client: TestClient):
    response = client.post(
        "/jobs/zoom-batch",
        files=[("images", ("bad.txt", b"nope", "text/plain"))],
    )
    assert response.status_code == 400
    assert "Unsupported image type" in response.json()["detail"]


def test_invalid_later_upload_does_not_create_orphaned_job(tmp_path: Path):
    jobs = ImmediateJobManager(tmp_path)
    app = create_app(
        jobs=jobs,
        renderer=FakeRenderer(),
        storage_factory=lambda: FakeStorage(),
    )
    client = TestClient(app)

    response = client.post(
        "/jobs/zoom-batch",
        files=[
            ("images", ("one.png", PNG_BYTES, "image/png")),
            ("images", ("bad.txt", b"nope", "text/plain")),
        ],
    )

    assert response.status_code == 400
    assert response.json()["detail"].startswith("Unsupported image type")
    assert jobs._jobs == {}
    assert list(tmp_path.iterdir()) == []


def test_job_creation_and_completion(client: TestClient):
    response = client.post(
        "/jobs/zoom-batch",
        files=[
            ("images", ("one.png", PNG_BYTES, "image/png")),
            ("images", ("two.png", PNG_BYTES, "image/png")),
        ],
        data={"output_name": "joined.mp4"},
    )
    assert response.status_code == 200
    payload = response.json()
    job = client.get(payload["status_url"])
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["rendered_images"] == 2
    assert job.json()["final_video_url"].startswith("/files/")
    assert job.json()["output_target"] == "local"
    assert job.json()["output_name"] == "joined.mp4"
    assert job.json()["local_video_path"].endswith("joined.mp4")

    file_response = client.get(job.json()["final_video_url"])
    assert file_response.status_code == 200
    assert file_response.content == b"fake-mp4"


def test_job_creation_accepts_render_tuning_fields(tmp_path: Path):
    jobs = ImmediateJobManager(tmp_path)
    renderer = CapturingRenderer()
    app = create_app(
        jobs=jobs,
        renderer=renderer,
        storage_factory=lambda: FakeStorage(),
    )
    client = TestClient(app)

    response = client.post(
        "/jobs/zoom-batch",
        files=[("images", ("one.png", PNG_BYTES, "image/png"))],
        data={
            "mode": "drift",
            "quality": "72",
            "ssaa": "1.75",
            "width": "1080",
            "height": "1920",
        },
    )

    assert response.status_code == 200
    assert len(renderer.requests) == 1
    request = renderer.requests[0]
    assert request.mode == RenderMode.drift
    assert request.quality == 72
    assert math.isclose(request.ssaa or 0, 1.75)
    assert request.width == 1080
    assert request.height == 1920


def test_job_creation_accepts_speech_text_and_voice(tmp_path: Path):
    jobs = ImmediateJobManager(tmp_path)
    renderer = CapturingRenderer()
    app = create_app(
        jobs=jobs,
        renderer=renderer,
        storage_factory=lambda: FakeStorage(),
    )
    client = TestClient(app)

    response = client.post(
        "/jobs/zoom-batch",
        files=[("images", ("one.png", PNG_BYTES, "image/png"))],
        data={
            "speech_text": "  Hello, welcome to Avatar Talk AI.  ",
            "speech_voice": "en-US-FableTurboMultilingualNeural",
        },
    )

    assert response.status_code == 200
    assert len(renderer.requests) == 1
    request = renderer.requests[0]
    assert request.speech_text == "Hello, welcome to Avatar Talk AI."
    assert request.speech_voice == "en-US-FableTurboMultilingualNeural"


def test_local_output_honors_specified_path(tmp_path: Path):
    jobs = ImmediateJobManager(tmp_path / "jobs")
    app = create_app(
        jobs=jobs,
        renderer=FakeRenderer(),
        storage_factory=lambda: FakeStorage(),
    )
    client = TestClient(app)
    requested = tmp_path / "exports" / "custom-location"

    response = client.post(
        "/jobs/zoom-batch",
        files=[("images", ("one.png", PNG_BYTES, "image/png"))],
        data={"output_name": str(requested)},
    )
    assert response.status_code == 200

    job = client.get(response.json()["status_url"])
    assert job.status_code == 200
    payload = job.json()
    expected_path = requested.with_suffix(".mp4").resolve()
    assert payload["status"] == "completed"
    assert payload["output_name"] == "custom-location.mp4"
    assert payload["local_video_path"] == str(expected_path)
    assert expected_path.exists()


def test_job_creation_with_azure_output(tmp_path: Path):
    jobs = ImmediateJobManager(tmp_path)
    app = create_app(
        jobs=jobs,
        renderer=FakeRenderer(),
        storage_factory=lambda: FakeStorage(),
    )
    client = TestClient(app)

    response = client.post(
        "/jobs/zoom-batch",
        files=[("images", ("one.png", PNG_BYTES, "image/png"))],
        data={"output_target": "azure"},
    )
    assert response.status_code == 200
    job = client.get(response.json()["status_url"])
    assert job.status_code == 200
    assert job.json()["output_target"] == "azure"
    assert job.json()["final_video_url"].startswith("https://storage.example.com/")


def test_job_failure_state(tmp_path: Path):
    jobs = ImmediateJobManager(tmp_path)
    app = create_app(
        jobs=jobs,
        renderer=FakeRenderer(should_fail=True),
        storage_factory=lambda: FakeStorage(),
    )
    client = TestClient(app)

    response = client.post(
        "/jobs/zoom-batch",
        files=[("images", ("one.png", PNG_BYTES, "image/png"))],
    )
    job = client.get(response.json()["status_url"])
    assert job.json()["status"] == "failed"
    assert job.json()["error"] == "render failed"


def test_rejects_invalid_quality_and_ssaa(client: TestClient):
    bad_quality = client.post(
        "/jobs/zoom-batch",
        files=[("images", ("one.png", PNG_BYTES, "image/png"))],
        data={"quality": "101"},
    )
    assert bad_quality.status_code == 400
    assert bad_quality.json()["detail"] == "quality must be between 0 and 100"

    bad_ssaa = client.post(
        "/jobs/zoom-batch",
        files=[("images", ("one.png", PNG_BYTES, "image/png"))],
        data={"ssaa": "0"},
    )
    assert bad_ssaa.status_code == 400
    assert bad_ssaa.json()["detail"] == "ssaa must be positive"


def test_motion_profiles_do_not_enable_green_inpaint_mask(monkeypatch: pytest.MonkeyPatch):
    fake_depthflow_scene = types.ModuleType("depthflow.scene")

    class FakeDepthScene:
        def update(self) -> None:
            pass

    fake_depthflow_scene.DepthScene = FakeDepthScene
    monkeypatch.setitem(sys.modules, "depthflow.scene", fake_depthflow_scene)

    class FakeImage:
        size = (1080, 1920)

    class FakeState:
        def __init__(self) -> None:
            self.steady = 0.0
            self.focus = 0.0
            self.isometric = 0.0
            self.height = 0.0
            self.inpaint = type("FakeInpaint", (), {"limit": 0.0})()

    class FakeScene:
        def __init__(self) -> None:
            self.image = FakeImage()
            self.state = FakeState()

    for mode in (RenderMode.gentle, RenderMode.tour, RenderMode.drift):
        scene = FakeScene()
        ZoomBatchRenderer._apply_motion_profile(scene, mode)
        assert scene.state.inpaint.limit == 0.0


def test_tour_motion_profile_applies_extra_zoom_effect(monkeypatch: pytest.MonkeyPatch):
    fake_depthflow_scene = types.ModuleType("depthflow.scene")

    class FakeDepthScene:
        def update(self) -> None:
            pass

    fake_depthflow_scene.DepthScene = FakeDepthScene
    monkeypatch.setitem(sys.modules, "depthflow.scene", fake_depthflow_scene)

    class FakeImage:
        size = (1920, 1080)

    class FakeState:
        def __init__(self) -> None:
            self.steady = 0.0
            self.focus = 0.0
            self.isometric = 0.0
            self.height = 0.0

    class FakeScene:
        def __init__(self) -> None:
            self.image = FakeImage()
            self.state = FakeState()
            self.cycle = math.pi

    scene = FakeScene()
    ZoomBatchRenderer._apply_motion_profile(scene, RenderMode.tour)
    scene.update()

    assert math.isclose(scene.state.zoom, 1.05)


def test_job_manager_persists_status(tmp_path: Path):
    jobs = JobManager(tmp_path)
    state = jobs.create_job(
        total_images=3,
        output_name="final.mp4",
        output_target=OutputTarget.local,
    )
    jobs.update_job(state.job_id, status="running", rendered_images=1, current_step="rendering")

    reloaded = JobManager(tmp_path).get_job(state.job_id)
    assert reloaded is not None
    assert reloaded.status == "running"
    assert reloaded.rendered_images == 1
    assert reloaded.output_target == "local"


def test_public_url_builder():
    storage = AzureBlobStorage(
        connection_string="UseDevelopmentStorage=true",
        container_name="videos",
        public_base_url="https://cdn.example.com/videos",
    )
    assert (
        storage.public_url_for_blob("depthflow/jobs/abc/final.mp4")
        == "https://cdn.example.com/videos/depthflow/jobs/abc/final.mp4"
    )


def test_concat_manifest_preserves_order(tmp_path: Path):
    renderer = ZoomBatchRenderer()
    clips = [tmp_path / "b.mp4", tmp_path / "a.mp4"]
    for clip in clips:
        clip.write_bytes(b"x")

    manifest = renderer.write_concat_manifest(clips, tmp_path / "concat.txt")
    assert manifest.read_text().splitlines() == [
        f"file '{clips[0].resolve()}'",
        f"file '{clips[1].resolve()}'",
    ]


def test_background_music_paths_only_include_supported_audio_files(tmp_path: Path):
    music_dir = tmp_path / "background-musics"
    music_dir.mkdir()
    (music_dir / "track-b.mp3").write_bytes(b"b")
    (music_dir / "track-a.wav").write_bytes(b"a")
    (music_dir / "notes.txt").write_text("ignore me")

    renderer = ZoomBatchRenderer(background_music_dir=music_dir)

    assert renderer.background_music_paths() == [
        music_dir / "track-a.wav",
        music_dir / "track-b.mp3",
    ]


def test_render_batch_adds_random_background_music_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    class StubRenderer(ZoomBatchRenderer):
        def render_single(self, image_path: Path, output_path: Path, request: RenderRequest) -> None:
            output_path.write_bytes(image_path.name.encode("utf-8"))

        def concat_videos(self, manifest_path: Path, output_path: Path) -> None:
            output_path.write_text(manifest_path.read_text())

        def add_background_music(self, video_path: Path, music_path: Path, output_path: Path) -> None:
            output_path.write_text(video_path.read_text() + f"music:{music_path.name}\n")

    music_dir = tmp_path / "background-musics"
    music_dir.mkdir()
    selected_track = music_dir / "selected.mp3"
    selected_track.write_bytes(b"track")
    (music_dir / "other.mp3").write_bytes(b"other")

    monkeypatch.setattr("depthflow_api.renderer.random.choice", lambda candidates: selected_track)

    request = RenderRequest(
        image_paths=[tmp_path / "one.png", tmp_path / "two.png"],
        clip_duration_seconds=0.2,
        fps=5,
        output_name="final.mp4",
    )
    for path in request.image_paths:
        path.write_bytes(PNG_BYTES)

    renderer = StubRenderer(background_music_dir=music_dir)
    output = renderer.render_batch(request, tmp_path / "job", lambda *_: None)

    assert output.exists()
    assert output.read_text().endswith("music:selected.mp3\n")


def test_render_batch_adds_speech_audio_when_requested(tmp_path: Path):
    class StubRenderer(ZoomBatchRenderer):
        def render_single(self, image_path: Path, output_path: Path, request: RenderRequest) -> None:
            output_path.write_bytes(image_path.name.encode("utf-8"))

        def concat_videos(self, manifest_path: Path, output_path: Path) -> None:
            output_path.write_text(manifest_path.read_text())

        def add_speech_audio(
            self,
            video_path: Path,
            speech_path: Path,
            output_path: Path,
            subtitles_path: Path | None = None,
        ) -> None:
            assert subtitles_path is not None
            assert subtitles_path.read_text().strip().endswith("Narrate this video.")
            output_path.write_text(video_path.read_text() + speech_path.read_text())

    tts = FakeTextToSpeech()
    request = RenderRequest(
        image_paths=[tmp_path / "one.png"],
        clip_duration_seconds=0.2,
        fps=5,
        output_name="final.mp4",
        speech_text="Narrate this video",
        speech_voice="custom-voice",
    )
    request.image_paths[0].write_bytes(PNG_BYTES)

    renderer = StubRenderer(background_music_dir=tmp_path / "unused", text_to_speech=tts)
    output = renderer.render_batch(request, tmp_path / "job", lambda *_: None)

    assert output.exists()
    assert output.read_text().endswith("speech")
    assert len(tts.calls) == 1
    text, speech_path, voice_name = tts.calls[0]
    assert text == "Narrate this video"
    assert voice_name == "custom-voice"
    assert not speech_path.exists()
    assert (tmp_path / "job" / "captions.srt").exists()


def test_render_batch_mixes_speech_with_background_music_when_both_available(tmp_path: Path):
    class StubRenderer(ZoomBatchRenderer):
        def render_single(self, image_path: Path, output_path: Path, request: RenderRequest) -> None:
            output_path.write_bytes(image_path.name.encode("utf-8"))

        def concat_videos(self, manifest_path: Path, output_path: Path) -> None:
            output_path.write_text(manifest_path.read_text())

        def add_speech_with_background_music(
            self,
            video_path: Path,
            speech_path: Path,
            music_path: Path,
            output_path: Path,
            subtitles_path: Path | None = None,
        ) -> None:
            assert subtitles_path is not None
            assert subtitles_path.read_text().strip().endswith("Narrate this video.")
            output_path.write_text(
                video_path.read_text()
                + speech_path.read_text()
                + f"music:{music_path.name}\n"
            )

    music_dir = tmp_path / "background-musics"
    music_dir.mkdir()
    selected_track = music_dir / "selected.mp3"
    selected_track.write_bytes(b"track")

    request = RenderRequest(
        image_paths=[tmp_path / "one.png"],
        clip_duration_seconds=0.2,
        fps=5,
        output_name="final.mp4",
        speech_text="Narrate this video",
    )
    request.image_paths[0].write_bytes(PNG_BYTES)

    renderer = StubRenderer(
        background_music_dir=music_dir,
        text_to_speech=FakeTextToSpeech(),
    )
    output = renderer.render_batch(request, tmp_path / "job", lambda *_: None)

    assert output.exists()
    assert output.read_text().endswith("speechmusic:selected.mp3\n")


def test_write_srt_groups_sentence_cues_and_clamps_padding(tmp_path: Path):
    subtitle_path = tmp_path / "captions.srt"
    write_srt(
        [
            WordBoundary("Hello", start=0.0, duration=0.2),
            WordBoundary(",", start=0.2, duration=0.0),
            WordBoundary("world.", start=0.3, duration=0.2, is_sentence_end=True),
            WordBoundary("Next", start=0.5, duration=0.2),
            WordBoundary("sentence?", start=0.7, duration=0.1, is_sentence_end=True),
        ],
        subtitle_path,
    )

    assert subtitle_path.read_text() == (
        "1\n"
        "00:00:00,000 --> 00:00:00,500\n"
        "Hello, world.\n"
        "\n"
        "2\n"
        "00:00:00,500 --> 00:00:00,950\n"
        "Next sentence?\n"
    )


def test_cleanup_scene_releases_context_before_destructor_cleanup():
    events: list[str] = []

    class FakeModule:
        def __init__(self, name: str) -> None:
            self.name = name

        def destroy(self) -> None:
            events.append(f"destroy:{self.name}")

    class FakeContext:
        def __init__(self) -> None:
            self.gc_mode = None

        def gc(self) -> None:
            events.append(f"gc:{self.gc_mode}")

        def release(self) -> None:
            events.append("context.release")

    class FakeWindow:
        def destroy(self) -> None:
            events.append("window.destroy")

    class FakeScene:
        def __init__(self) -> None:
            self.modules = [FakeModule("texture"), object(), FakeModule("shader")]
            self.opengl = FakeContext()
            self.window = FakeWindow()
            self.shader = object()
            self._final = object()
            self.frametimer = object()
            self.keyboard = object()
            self.camera = object()

    scene = FakeScene()

    ZoomBatchRenderer._cleanup_scene(scene)

    assert events == [
        "destroy:texture",
        "destroy:shader",
        "gc:context_gc",
        "window.destroy",
        "context.release",
    ]
    assert scene.modules == []
    assert scene.opengl is None
    assert scene.window is None
    assert scene.shader is None
    assert scene._final is None
    assert scene.frametimer is None
    assert scene.keyboard is None
    assert scene.camera is None


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="ffmpeg not available",
)
def test_real_concat_smoke(tmp_path: Path):
    renderer = ZoomBatchRenderer()
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    manifest = tmp_path / "concat.txt"
    output = tmp_path / "joined.mp4"

    for path in (first, second):
        result = shutil.which("ffmpeg")
        assert result is not None
        import subprocess

        subprocess.run(
            [
                result,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=16x16:d=0.2",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            check=True,
            capture_output=True,
        )

    renderer.concat_videos(renderer.write_concat_manifest([first, second], manifest), output)
    assert output.exists()
    assert output.stat().st_size > 0


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not available",
)
def test_add_background_music_trims_to_video_length(tmp_path: Path):
    renderer = ZoomBatchRenderer(background_music_dir=tmp_path / "unused")
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg is not None
    assert ffprobe is not None

    video_path = tmp_path / "video.mp4"
    music_path = tmp_path / "music.mp3"
    output_path = tmp_path / "with-music.mp4"

    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=16x16:d=0.4",
            "-pix_fmt",
            "yuv420p",
            str(video_path),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            str(music_path),
        ],
        check=True,
        capture_output=True,
    )

    renderer.add_background_music(video_path, music_path, output_path)
    assert output_path.exists()

    duration = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    audio_streams = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "audio" in audio_streams.stdout
    assert math.isclose(float(duration.stdout.strip()), 0.4, rel_tol=0.2, abs_tol=0.15)


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not available",
)
def test_add_speech_audio_pads_short_speech_to_video_length(tmp_path: Path):
    renderer = ZoomBatchRenderer(background_music_dir=tmp_path / "unused")
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg is not None
    assert ffprobe is not None

    video_path = tmp_path / "video.mp4"
    speech_path = tmp_path / "speech.wav"
    output_path = tmp_path / "with-speech.mp4"

    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=16x16:d=0.8",
            "-pix_fmt",
            "yuv420p",
            str(video_path),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.2",
            str(speech_path),
        ],
        check=True,
        capture_output=True,
    )

    renderer.add_speech_audio(video_path, speech_path, output_path)

    duration = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    audio_streams = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "audio" in audio_streams.stdout
    assert math.isclose(float(duration.stdout.strip()), 0.8, rel_tol=0.2, abs_tol=0.15)


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not available",
)
def test_add_speech_audio_adds_mov_text_subtitle_stream(tmp_path: Path):
    renderer = ZoomBatchRenderer(background_music_dir=tmp_path / "unused")
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg is not None
    assert ffprobe is not None

    video_path = tmp_path / "video.mp4"
    speech_path = tmp_path / "speech.wav"
    subtitles_path = tmp_path / "captions.srt"
    output_path = tmp_path / "with-speech-and-captions.mp4"

    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=16x16:d=0.8",
            "-pix_fmt",
            "yuv420p",
            str(video_path),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.2",
            str(speech_path),
        ],
        check=True,
        capture_output=True,
    )
    subtitles_path.write_text(
        "1\n00:00:00,000 --> 00:00:00,500\nHello world.\n",
        encoding="utf-8",
    )

    renderer.add_speech_audio(
        video_path,
        speech_path,
        output_path,
        subtitles_path=subtitles_path,
    )

    subtitle_streams = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "s",
            "-show_entries",
            "stream=codec_name:stream_tags=language",
            "-of",
            "default=noprint_wrappers=1",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "codec_name=mov_text" in subtitle_streams.stdout
    assert "TAG:language=eng" in subtitle_streams.stdout


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="ffmpeg not available",
)
def test_real_pipeline_smoke_if_runtime_available(tmp_path: Path):
    pytest.importorskip("dearlog")
    pytest.importorskip("shaderflow")
    pytest.importorskip("imageio")

    request = RenderRequest(
        image_paths=[tmp_path / "one.png", tmp_path / "two.png"],
        clip_duration_seconds=0.2,
        fps=5,
        output_name="final.mp4",
    )
    for path in request.image_paths:
        path.write_bytes(PNG_BYTES)

    renderer = ZoomBatchRenderer()
    output = renderer.render_batch(request, tmp_path / "job", lambda *_: None)
    assert output.exists()
