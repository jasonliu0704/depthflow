from __future__ import annotations

import mimetypes
import os
from pathlib import Path


class AzureBlobStorage:
    def __init__(
        self,
        connection_string: str,
        container_name: str,
        public_base_url: str | None = None,
    ) -> None:
        self.connection_string = connection_string
        self.container_name = container_name
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None

    @classmethod
    def from_env(cls) -> "AzureBlobStorage":
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        container_name = os.getenv("AZURE_STORAGE_CONTAINER")
        public_base_url = os.getenv("AZURE_PUBLIC_BASE_URL")

        if not connection_string:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is required")
        if not container_name:
            raise RuntimeError("AZURE_STORAGE_CONTAINER is required")

        return cls(
            connection_string=connection_string,
            container_name=container_name,
            public_base_url=public_base_url,
        )

    def public_url_for_blob(self, blob_name: str) -> str:
        blob_name = blob_name.lstrip("/")
        if self.public_base_url:
            return f"{self.public_base_url}/{blob_name}"
        raise RuntimeError(
            "AZURE_PUBLIC_BASE_URL is required to return a public blob URL in this deployment"
        )

    def upload_file(self, local_path: Path, blob_name: str) -> str:
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import ContentSettings
        from azure.storage.blob import BlobServiceClient

        blob_name = blob_name.lstrip("/")
        client = BlobServiceClient.from_connection_string(self.connection_string)
        container = client.get_container_client(self.container_name)
        try:
            container.create_container()
        except ResourceExistsError:
            pass

        content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        blob_client = container.get_blob_client(blob_name)
        with local_path.open("rb") as handle:
            blob_client.upload_blob(
                handle,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
        return self.public_url_for_blob(blob_name)
