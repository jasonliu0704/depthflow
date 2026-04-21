# DepthFlow Batch API

This API accepts multiple uploaded images, renders a DepthFlow zoom clip for each image, stitches the clips together in upload order, and returns the final `.mp4`.

By default, the final video is kept locally and exposed by the API itself through a download URL. You can optionally switch a job to Azure Blob Storage output instead.

If the repo-level [`background-musics`](/Users/jk/project/DepthFlow/background-musics) folder contains audio files, the stitch step randomly selects one track and adds it as background music. The audio is automatically trimmed so it never outlasts the final video.

## What It Exposes

- `POST /jobs/zoom-batch`
  - accepts `multipart/form-data`
  - field `images` can be repeated
  - optional fields: `clip_duration_seconds`, `fps`, `width`, `height`, `output_name`, `output_target`
  - returns `job_id`, `status`, `status_url`
- `GET /jobs/{job_id}`
  - returns job state, progress, and `final_video_url` when completed
- `GET /files/{job_id}/{filename}`
  - serves locally stored completed videos

## Requirements

- Python 3.10+
- `ffmpeg` available on `PATH`
- a working DepthFlow runtime on the machine where the API runs
  - this includes the project dependencies such as `shaderflow`, `torch`, `transformers`, and related render/runtime packages
- Azure Blob Storage is optional and only needed when using `output_target=azure`

## Required Environment Variables

- `DEPTHFLOW_API_WORKDIR`
  - optional
  - defaults to `.depthflow-api` in the repo root when using the deploy script
- `DEPTHFLOW_API_DEFAULT_OUTPUT_TARGET`
  - optional
  - default `local`
- `AZURE_STORAGE_CONNECTION_STRING`
  - optional unless `output_target=azure`
- `AZURE_STORAGE_CONTAINER`
  - optional unless `output_target=azure`
- `AZURE_PUBLIC_BASE_URL`
  - optional unless `output_target=azure`
  - example: `https://myaccount.blob.core.windows.net/my-public-container`
- `HOST`
  - optional
  - default `0.0.0.0`
- `PORT`
  - optional
  - default `8000`
- `UVICORN_WORKERS`
  - optional
  - default `1`
- `UVICORN_LOG_LEVEL`
  - optional
  - default `info`

## Quick Start

From the repository root:

```bash
./scripts/deploy_depthflow_api.sh
```

The script will:

1. verify `ffmpeg` is installed
2. create a local virtual environment at `.venv-depthflow-api` if needed
3. build the `depthflow` wheel into `dist/`
4. install the built wheel into the virtual environment
5. default to local output delivery unless you override it per job
6. start the API with Uvicorn

## Local Run Without The Script

```bash
python3 -m venv .venv-depthflow-api
source .venv-depthflow-api/bin/activate
python -m pip install --upgrade pip
python -m pip install --upgrade build
python -m build --wheel --outdir dist .
python -m pip install --force-reinstall dist/depthflow-*.whl

export DEPTHFLOW_API_WORKDIR="$(pwd)/.depthflow-api"

python -m uvicorn depthflow_api.app:app --host 0.0.0.0 --port 8000
```

## Example Request

Create a batch job:

```bash
curl -X POST "http://127.0.0.1:8000/jobs/zoom-batch" \
  -F "images=@/absolute/path/image-1.png" \
  -F "images=@/absolute/path/image-2.jpg" \
  -F "clip_duration_seconds=5" \
  -F "fps=30" \
  -F "width=1280" \
  -F "output_name=my-batch.mp4"
```

Example response:

```json
{
  "job_id": "5d0c4e2c7eb54b8d96f9b8dd2d4e4a65",
  "status": "queued",
  "status_url": "/jobs/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65"
}
```

Poll the job:

```bash
curl "http://127.0.0.1:8000/jobs/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65"
```

Completed job response:

```json
{
  "job_id": "5d0c4e2c7eb54b8d96f9b8dd2d4e4a65",
  "status": "completed",
  "status_url": "/jobs/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65",
  "total_images": 2,
  "rendered_images": 2,
  "current_step": "completed",
  "output_name": "my-batch.mp4",
  "output_target": "local",
  "final_video_url": "/files/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65/my-batch.mp4",
  "local_video_path": "/absolute/path/to/.depthflow-api/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65/my-batch.mp4",
  "error": null
}
```

Download the locally stored video:

```bash
curl -O "http://127.0.0.1:8000/files/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65/my-batch.mp4"
```

## Azure Output

To publish the final video to Azure instead of keeping the returned URL local:

```bash
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net"
export AZURE_STORAGE_CONTAINER="depthflow-videos"
export AZURE_PUBLIC_BASE_URL="https://myaccount.blob.core.windows.net/depthflow-videos"

curl -X POST "http://127.0.0.1:8000/jobs/zoom-batch" \
  -F "images=@/absolute/path/image-1.png" \
  -F "output_target=azure"
```

- Azure uploads use:
  - `depthflow/jobs/{job_id}/{output_name}`
- `AZURE_PUBLIC_BASE_URL` should point at the same public container named by `AZURE_STORAGE_CONTAINER`
- the returned Azure URL is public, not signed

## Testing

Run the API tests with:

```bash
pytest -q tests/test_depthflow_api.py
```

## Operational Notes

- The current implementation keeps local uploads, rendered clips, and job status files under `DEPTHFLOW_API_WORKDIR`
- local output is the default delivery mode
- there is no cleanup policy yet, so plan periodic cleanup if this service will run continuously
- background jobs run inside the API process for v1, so use a single worker unless you are confident the local DepthFlow runtime is safe for concurrent renders
