# Deployment Guide

This document describes how to deploy the DepthFlow API packaged in this repository.

The recommended path is:

1. build the API as a Docker image
2. ship the deployment bundle to a Linux VM
3. run the deploy script with `docker compose`

The repository already includes:

- [Dockerfile.depthflow-api](/Users/jk/project/DepthFlow/Dockerfile.depthflow-api)
- [scripts/package_depthflow_api.sh](/Users/jk/project/DepthFlow/scripts/package_depthflow_api.sh)
- [scripts/run_depthflow_api.sh](/Users/jk/project/DepthFlow/scripts/run_depthflow_api.sh)
- [deploy/docker/compose.yml](/Users/jk/project/DepthFlow/deploy/docker/compose.yml)
- [deploy/docker/deploy.sh](/Users/jk/project/DepthFlow/deploy/docker/deploy.sh)
- [deploy/docker/depthflow-api.env.example](/Users/jk/project/DepthFlow/deploy/docker/depthflow-api.env.example)
- [.github/workflows/deploy-depthflow-api.yml](/Users/jk/project/DepthFlow/.github/workflows/deploy-depthflow-api.yml)

## Recommended Deployment

Use the GitHub Actions workflow at [.github/workflows/deploy-depthflow-api.yml](/Users/jk/project/DepthFlow/.github/workflows/deploy-depthflow-api.yml).

It will:

1. build the Docker image
2. save `dist/depthflow-api-image.tar.gz`
3. upload the deployment bundle
4. copy the bundle to your server over SSH
5. run the remote deploy script

## One-Time Server Setup

On the target Linux VM:

1. Install Docker and the Docker Compose plugin.
2. Create the deployment directory:

```bash
sudo mkdir -p /opt/depthflow-api
sudo chown -R "$USER":"$USER" /opt/depthflow-api
```

## One-Time GitHub Setup

Add these GitHub repository secrets:

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`

Optional:

- `DEPLOY_PATH`
  - defaults to `/opt/depthflow-api`

## First Deploy

Trigger the workflow manually from GitHub Actions:

- `deploy-depthflow-api`

After the bundle is copied to the server, SSH into the machine and create the runtime env file:

```bash
cd /opt/depthflow-api
cp depthflow-api.env.example .env.depthflow-api
nano .env.depthflow-api
```

At minimum, set:

```bash
DEPTHFLOW_API_IMAGE=depthflow-api:deploy
DEPTHFLOW_API_DEFAULT_OUTPUT_TARGET=local
HOST_PORT=8000
UVICORN_WORKERS=1
UVICORN_LOG_LEVEL=info
```

If you want Azure-backed output, also set:

```bash
AZURE_STORAGE_CONNECTION_STRING=...
AZURE_STORAGE_CONTAINER=...
AZURE_PUBLIC_BASE_URL=...
```

Then deploy:

```bash
APP_DIR=/opt/depthflow-api bash /opt/depthflow-api/deploy.sh
```

## Normal Ongoing Deploys

After the first setup, your deploy flow is:

1. push changes to `main`
2. let GitHub Actions run `deploy-depthflow-api`

The workflow is configured to run automatically when these areas change:

- `depthflow/**`
- `depthflow_api/**`
- `background-musics/**`
- `Dockerfile.depthflow-api`
- `deploy/docker/**`
- `scripts/package_depthflow_api.sh`
- `scripts/run_depthflow_api.sh`
- `pyproject.toml`

You can also run the workflow manually any time.

## Manual Fallback Deployment

If you do not want to use GitHub Actions, you can deploy by hand.

### 1. Build The Package Locally

```bash
bash /Users/jk/project/DepthFlow/scripts/package_depthflow_api.sh
```

This creates:

```text
/Users/jk/project/DepthFlow/dist/depthflow-api-image.tar.gz
```

### 2. Copy The Bundle To The Server

Copy these files to `/opt/depthflow-api` on the server:

- `dist/depthflow-api-image.tar.gz`
- [deploy/docker/compose.yml](/Users/jk/project/DepthFlow/deploy/docker/compose.yml)
- [deploy/docker/deploy.sh](/Users/jk/project/DepthFlow/deploy/docker/deploy.sh)
- [deploy/docker/depthflow-api.env.example](/Users/jk/project/DepthFlow/deploy/docker/depthflow-api.env.example)

### 3. Create The Runtime Env File

```bash
cd /opt/depthflow-api
cp depthflow-api.env.example .env.depthflow-api
nano .env.depthflow-api
```

### 4. Run The Deploy Script

```bash
APP_DIR=/opt/depthflow-api bash ./deploy.sh
```

## What The Deploy Script Does

The deploy script at [deploy/docker/deploy.sh](/Users/jk/project/DepthFlow/deploy/docker/deploy.sh) will:

1. ensure Docker is installed
2. ensure the Docker Compose plugin is available
3. create `workdir/` and `output/`
4. load the Docker image archive if present
5. start or update the container with `docker compose up -d`

## Runtime Files On The Server

The deployment directory will typically contain:

```text
/opt/depthflow-api/
  compose.yml
  deploy.sh
  depthflow-api.env.example
  .env.depthflow-api
  depthflow-api-image.tar.gz
  workdir/
  output/
```

## Smoke Checks

After deployment:

```bash
docker ps
curl http://127.0.0.1:8000/openapi.json
```

You can also inspect the composed service:

```bash
cd /opt/depthflow-api
docker compose --env-file .env.depthflow-api -f compose.yml ps
docker compose --env-file .env.depthflow-api -f compose.yml logs -f
```

## Notes

- The container listens on port `8000` internally.
- `HOST_PORT` in `.env.depthflow-api` controls the external port on the VM.
- The API keeps job state and intermediate files in `workdir/`.
- Final local outputs are written under `output/`.
- The image is based on Python 3.11 to avoid the Python 3.13 runtime instability seen during local development.
