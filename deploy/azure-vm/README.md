# Azure VM Deployment Bundle

This bundle is the easiest way to run the DepthFlow Batch API on an Azure Linux VM.

It is designed for a single Ubuntu VM with:

- Python 3
- `ffmpeg`
- systemd
- optional Azure Blob output

The deployment layout assumes the repository lives at:

```text
/opt/depthflow/DepthFlow
```

You can change that if needed, but the examples below use that path.

## Files In This Bundle

- [install.sh](/Users/jk/project/DepthFlow/deploy/azure-vm/install.sh)
  - installs OS packages
  - creates the virtual environment
  - builds the wheel
  - installs the app into the venv
- [start.sh](/Users/jk/project/DepthFlow/deploy/azure-vm/start.sh)
  - loads environment variables
  - starts `uvicorn`
- [depthflow-api.env.example](/Users/jk/project/DepthFlow/deploy/azure-vm/depthflow-api.env.example)
  - environment template for the API
- [depthflow-api.service](/Users/jk/project/DepthFlow/deploy/azure-vm/depthflow-api.service)
  - reference systemd unit template
- [install-systemd.sh](/Users/jk/project/DepthFlow/deploy/azure-vm/install-systemd.sh)
  - writes a systemd unit using the current VM user and repo path

## Recommended VM Setup

Example Azure VM choices:

- Ubuntu 22.04 LTS or 24.04 LTS
- Standard CPU VM is enough if you are using CPU rendering / light workloads
- a VM with GPU only if you explicitly want GPU-backed inference/rendering

Open at least:

- TCP `8000` if you want to expose Uvicorn directly
- or TCP `80` / `443` if you place Nginx in front

## Deployment Steps

### 1. Copy The Repo To The VM

Example:

```bash
ssh azureuser@your-vm
sudo mkdir -p /opt/depthflow
sudo chown -R "$USER":"$USER" /opt/depthflow
cd /opt/depthflow
git clone <your-repo-url> DepthFlow
cd DepthFlow
```

### 2. Run The Installer

```bash
cd /opt/depthflow/DepthFlow
bash deploy/azure-vm/install.sh
```

This will:

1. install required Ubuntu packages
2. create `.venv-depthflow-api`
3. build the `depthflow` wheel
4. install the wheel into the venv

### 3. Create The Environment File

```bash
cp deploy/azure-vm/depthflow-api.env.example /opt/depthflow/DepthFlow/.env.depthflow-api
```

Then edit it:

```bash
nano /opt/depthflow/DepthFlow/.env.depthflow-api
```

At minimum, set:

```bash
DEPTHFLOW_API_WORKDIR=/opt/depthflow/DepthFlow/.depthflow-api
DEPTHFLOW_API_DEFAULT_OUTPUT_TARGET=local
HOST=0.0.0.0
PORT=8000
UVICORN_WORKERS=1
UVICORN_LOG_LEVEL=info
```

Optional Azure output:

```bash
AZURE_STORAGE_CONNECTION_STRING=...
AZURE_STORAGE_CONTAINER=...
AZURE_PUBLIC_BASE_URL=...
```

### 4. Install The systemd Service

Recommended:

```bash
bash deploy/azure-vm/install-systemd.sh
```

Reload systemd and enable the service:

```bash
sudo systemctl start depthflow-api
```

Check status:

```bash
sudo systemctl status depthflow-api
```

Tail logs:

```bash
journalctl -u depthflow-api -f
```

If you need a different user or service name:

```bash
SERVICE_USER=azureuser SERVICE_NAME=depthflow-api bash deploy/azure-vm/install-systemd.sh
```

## Updating The Deployment

After pulling new code:

```bash
cd /opt/depthflow/DepthFlow
git pull
bash deploy/azure-vm/install.sh
sudo systemctl restart depthflow-api
```

## Manual Start Without systemd

Useful for debugging:

```bash
cd /opt/depthflow/DepthFlow
bash deploy/azure-vm/start.sh
```

## Recommended Next Production Steps

For a more production-ready setup, add:

- Nginx as a reverse proxy
- TLS via Let's Encrypt
- a cleanup cron for old job folders and rendered files
- VM disk sizing for uploads and generated videos

## Smoke Test

After the service is up:

```bash
curl http://127.0.0.1:8000/jobs/not-a-real-id
```

Expected result:

```json
{"detail":"Job not found"}
```

Then submit a real batch request using the API examples in:

- [depthflow_api/API.md](/Users/jk/project/DepthFlow/depthflow_api/API.md)
