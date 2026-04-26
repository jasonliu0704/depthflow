# Docker Deployment Bundle

This bundle packages the DepthFlow API as a Docker image and deploys it to a Linux VM with `docker compose`.

It is designed for a single host that already has:

- Docker
- the Docker Compose plugin
- SSH access from GitHub Actions

## Files

- [compose.yml](/Users/jk/project/DepthFlow/deploy/docker/compose.yml)
  - runs the API container
  - mounts persistent `workdir/` and `output/` folders
- [deploy.sh](/Users/jk/project/DepthFlow/deploy/docker/deploy.sh)
  - loads the packaged image archive
  - creates the runtime folders
  - starts or updates the stack with `docker compose`
- [depthflow-api.env.example](/Users/jk/project/DepthFlow/deploy/docker/depthflow-api.env.example)
  - runtime configuration template

## Local Packaging

Build the image and save a compressed archive:

```bash
bash scripts/package_depthflow_api.sh
```

This creates:

```text
dist/depthflow-api-image.tar.gz
```

## Manual VM Setup

On the target host, create a deployment folder:

```bash
mkdir -p /opt/depthflow-api
```

Copy these files into it:

- `deploy/docker/compose.yml`
- `deploy/docker/deploy.sh`
- `deploy/docker/depthflow-api.env.example`
- `dist/depthflow-api-image.tar.gz`

Then create the runtime env file:

```bash
cp /opt/depthflow-api/depthflow-api.env.example /opt/depthflow-api/.env.depthflow-api
```

Deploy:

```bash
cd /opt/depthflow-api
bash deploy.sh
```

The service will be exposed on `HOST_PORT` from the env file, default `8000`.

## GitHub Actions Deployment

The workflow at [.github/workflows/deploy-depthflow-api.yml](/Users/jk/project/DepthFlow/.github/workflows/deploy-depthflow-api.yml) can build and deploy for you.

Set these repository secrets:

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`

Optional secret:

- `DEPLOY_PATH`
  - defaults to `/opt/depthflow-api`

After that, you can:

- run the workflow manually
- or let pushes to `main` deploy automatically when API packaging files change
