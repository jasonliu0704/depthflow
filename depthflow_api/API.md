# DepthFlow Batch API Reference

This document is a client-facing reference for integrating with the DepthFlow batch render server.

Base URL examples:

- local: `http://127.0.0.1:8000`
- remote: `https://your-server.example.com`

## Overview

The API supports one workflow:

1. create a render job by uploading one or more images
2. poll the job status
3. when the job is complete, download or open the final video URL

The server renders one zoom clip per uploaded image, stitches the clips in upload order, and exposes the final `.mp4`.
When local audio files are present in [`background-musics`](/Users/jk/project/DepthFlow/background-musics), the final stitch step randomly picks one track as background music and trims it to the rendered video length.

## Authentication

There is currently no built-in authentication layer in this API.

If you deploy it publicly, put it behind your own auth, proxy, or network restrictions.

## Content Types

- `POST /jobs/zoom-batch` uses `multipart/form-data`
- `GET /jobs/{job_id}` returns `application/json`
- `GET /files/{job_id}/{filename}` returns `video/mp4`

## Job Status Values

Possible `status` values:

- `queued`
- `running`
- `failed`
- `completed`

Possible `output_target` values:

- `local`
- `azure`

## Endpoints

### `POST /jobs/zoom-batch`

Create a render job from one or more uploaded images.

#### Request

Content type:

```http
multipart/form-data
```

Form fields:

- `images`
  - required
  - repeat this field for each image
  - accepted extensions: `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tiff`
- `clip_duration_seconds`
  - optional
  - float
  - default: `5.0`
- `fps`
  - optional
  - integer
  - default: `30`
- `width`
  - optional
  - integer
  - if omitted, render width follows the source image / DepthFlow defaults
- `height`
  - optional
  - integer
  - if omitted, render height follows the source image / DepthFlow defaults
- `mode`
  - optional
  - enum: `gentle`, `tour`, `drift`
  - default: `tour`
  - controls the camera motion profile used for the parallax clip
- `quality`
  - optional
  - integer from `0` to `100`
  - forwards DepthFlow's projection quality setting
- `ssaa`
  - optional
  - positive number
  - forwards DepthFlow's super-sampling setting for smoother edges
- `output_name`
  - optional
  - string
  - default: `final.mp4`
  - if no `.mp4` suffix is provided, the server adds it
- `output_target`
  - optional
  - enum: `local` or `azure`
  - default: `local`
  - `azure` requires Azure storage environment variables to be configured on the server

#### Success Response

Status:

```http
200 OK
```

Body:

```json
{
  "job_id": "5d0c4e2c7eb54b8d96f9b8dd2d4e4a65",
  "status": "queued",
  "status_url": "/jobs/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65"
}
```

Field meanings:

- `job_id`: unique identifier for the job
- `status`: initial job state, usually `queued`
- `status_url`: relative path to poll for updates

#### Error Responses

Typical failures:

- `400 Bad Request`
  - no images uploaded
  - unsupported file extension
  - unsupported content type
  - invalid `clip_duration_seconds`, `fps`, `width`, `height`, `quality`, or `ssaa`
- `500 Internal Server Error`
  - server-side configuration or runtime failure
  - for example, Azure output requested but Azure storage is not configured

Example error:

```json
{
  "detail": "Unsupported image type: .txt"
}
```

#### cURL Example

```bash
curl -X POST "http://127.0.0.1:8000/jobs/zoom-batch" \
  -F "images=@/absolute/path/image-1.png" \
  -F "images=@/absolute/path/image-2.jpg" \
  -F "clip_duration_seconds=5" \
  -F "fps=30" \
  -F "mode=tour" \
  -F "quality=72" \
  -F "ssaa=1.75" \
  -F "output_name=demo.mp4"
```

#### JavaScript Example

```javascript
const form = new FormData();
form.append("images", fileInput1.files[0]);
form.append("images", fileInput2.files[0]);
form.append("clip_duration_seconds", "5");
form.append("fps", "30");
form.append("mode", "tour");
form.append("quality", "72");
form.append("ssaa", "1.75");
form.append("output_name", "demo.mp4");
form.append("output_target", "local");

const response = await fetch("http://127.0.0.1:8000/jobs/zoom-batch", {
  method: "POST",
  body: form,
});

if (!response.ok) {
  throw new Error(`Job creation failed: ${response.status}`);
}

const job = await response.json();
console.log(job);
```

### `GET /jobs/{job_id}`

Fetch current job status and final output details.

#### Request

Path parameters:

- `job_id`
  - required
  - string returned by `POST /jobs/zoom-batch`

#### Success Response

Status:

```http
200 OK
```

Completed example:

```json
{
  "job_id": "5d0c4e2c7eb54b8d96f9b8dd2d4e4a65",
  "status": "completed",
  "status_url": "/jobs/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65",
  "total_images": 2,
  "rendered_images": 2,
  "current_step": "completed",
  "output_name": "demo.mp4",
  "output_target": "local",
  "final_video_url": "/files/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65/demo.mp4",
  "local_video_path": "/absolute/path/to/.depthflow-api/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65/demo.mp4",
  "error": null
}
```

Running example:

```json
{
  "job_id": "5d0c4e2c7eb54b8d96f9b8dd2d4e4a65",
  "status": "running",
  "status_url": "/jobs/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65",
  "total_images": 3,
  "rendered_images": 1,
  "current_step": "rendering clip 2 of 3",
  "output_name": "demo.mp4",
  "output_target": "local",
  "final_video_url": null,
  "local_video_path": null,
  "error": null
}
```

Failed example:

```json
{
  "job_id": "5d0c4e2c7eb54b8d96f9b8dd2d4e4a65",
  "status": "failed",
  "status_url": "/jobs/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65",
  "total_images": 2,
  "rendered_images": 0,
  "current_step": "failed",
  "output_name": "demo.mp4",
  "output_target": "local",
  "final_video_url": null,
  "local_video_path": null,
  "error": "ffmpeg executable was not found on PATH"
}
```

Field meanings:

- `total_images`: number of uploaded images in the job
- `rendered_images`: number of clips completed so far
- `current_step`: human-readable progress string
- `final_video_url`: where the client should fetch the final video when complete
- `local_video_path`: absolute file path on the server when output is local
  - useful for trusted internal deployments
  - external clients should usually use `final_video_url` instead
- `error`: failure message when `status` is `failed`

#### Error Response

Status:

```http
404 Not Found
```

Body:

```json
{
  "detail": "Job not found"
}
```

#### Polling Guidance

Recommended polling loop:

- poll every `2` to `5` seconds
- stop when `status` becomes `completed` or `failed`
- when `completed`, resolve `final_video_url` against your server base URL if it is relative

JavaScript polling example:

```javascript
async function waitForJob(baseUrl, jobId) {
  while (true) {
    const response = await fetch(`${baseUrl}/jobs/${jobId}`);
    if (!response.ok) {
      throw new Error(`Status fetch failed: ${response.status}`);
    }

    const job = await response.json();
    if (job.status === "completed") {
      return job;
    }
    if (job.status === "failed") {
      throw new Error(job.error || "Job failed");
    }

    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
}
```

### `GET /files/{job_id}/{filename}`

Download a completed locally stored output video.

This endpoint is only meaningful when the job was created with `output_target=local`.

#### Request

Path parameters:

- `job_id`
  - required
- `filename`
  - required
  - must match the job's `output_name`

#### Success Response

Status:

```http
200 OK
```

Content type:

```http
video/mp4
```

The response body is the raw video file.

#### Error Responses

- `404 Not Found`
  - job does not exist
  - filename does not match the job output
  - file is not available yet

#### cURL Example

```bash
curl -L "http://127.0.0.1:8000/files/5d0c4e2c7eb54b8d96f9b8dd2d4e4a65/demo.mp4" -o demo.mp4
```

## URL Handling

`status_url` and `final_video_url` may be relative paths.

Client rule:

- if the value starts with `/`, prepend your API base URL
- if the value already starts with `http://` or `https://`, use it as-is

Example:

- base URL: `http://127.0.0.1:8000`
- `final_video_url`: `/files/abc/demo.mp4`
- resolved URL: `http://127.0.0.1:8000/files/abc/demo.mp4`

## Recommended Client Flow

1. Upload images with `POST /jobs/zoom-batch`
2. Store `job_id` and `status_url`
3. Poll `GET /jobs/{job_id}`
4. If `status=completed`, resolve and fetch `final_video_url`
5. If `status=failed`, show `error`

## Notes And Limits

- image order matters; the final stitched video uses the same order the files were uploaded
- local output is the default
- Azure output is optional and depends on server-side Azure configuration
- the API currently runs background jobs in-process
- there is no server-side cleanup policy yet for old jobs or local files
