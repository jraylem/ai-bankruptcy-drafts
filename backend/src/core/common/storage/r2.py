"""Cloudflare R2 (S3-compatible) storage service.

Thin async wrapper over boto3's S3 client. Keys are layered as
`{prefix}/{template_id}/{filename}`. The module exposes a singleton
`r2_service` used by the case ingestion, template generation, draft finalizer,
and supporting-docs upload paths.
"""

import os
from io import BytesIO

import boto3
from botocore.config import Config


class R2Service:
    """S3-compatible async wrapper around Cloudflare R2; keys are layered as `{prefix}/{template_id}/{filename}`."""

    def __init__(self):
        self.endpoint_url = os.getenv("R2_ENDPOINT_URL")
        self.access_key_id = os.getenv("R2_ACCESS_KEY_ID")
        self.secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY")
        self.bucket_name = os.getenv("R2_BUCKET_NAME", "templates")

        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=Config(signature_version="s3v4"),
        )

    async def upload_file(
        self,
        file_content: bytes,
        template_id: str,
        filename: str,
        content_type: str = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        prefix: str | None = None
    ) -> str:
        """Upload file to R2 bucket under optional prefix and template_id folder."""
        key = f"{prefix}/{template_id}/{filename}" if prefix else f"{template_id}/{filename}"

        self.client.upload_fileobj(
            BytesIO(file_content),
            self.bucket_name,
            key,
            ExtraArgs={"ContentType": content_type}
        )

        return key

    async def download_file(
        self,
        template_id: str,
        filename: str,
        prefix: str | None = None
    ) -> bytes:
        """Download file from R2 bucket."""
        key = f"{prefix}/{template_id}/{filename}" if prefix else f"{template_id}/{filename}"

        response = self.client.get_object(Bucket=self.bucket_name, Key=key)
        return response["Body"].read()

    async def download_by_key(self, key: str) -> bytes:
        """Download a file from R2 by its full bucket-relative key.

        Useful when the caller already has a fully-qualified key (e.g.
        parsed out of a stored R2 URL) rather than the layered
        `{prefix}/{template_id}/{filename}` shape that `download_file`
        expects. Uses the boto3 client which signs each request fresh,
        so it sidesteps stale presigned URLs."""
        response = self.client.get_object(Bucket=self.bucket_name, Key=key)
        return response["Body"].read()

    async def list_files(self, template_id: str, prefix: str | None = None) -> list[str]:
        """List all files in a template folder."""
        key_prefix = f"{prefix}/{template_id}/" if prefix else f"{template_id}/"

        response = self.client.list_objects_v2(
            Bucket=self.bucket_name,
            Prefix=key_prefix
        )

        files = []
        for obj in response.get("Contents", []):
            filename = obj["Key"].replace(key_prefix, "")
            if filename:
                files.append(filename)

        return files

    async def get_presigned_url(
        self,
        template_id: str,
        filename: str,
        expires_in: int = 3600,
        prefix: str | None = None
    ) -> str:
        """Generate a presigned URL for downloading a file."""
        key = f"{prefix}/{template_id}/{filename}" if prefix else f"{template_id}/{filename}"

        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": key},
            ExpiresIn=expires_in
        )

        return url

    async def get_presigned_url_by_key(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL from a fully-qualified bucket key.

        Used by v2 case_generation_logs which persist the raw R2 key and
        re-sign on every read so the FE never receives an expired URL.
        """
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": key},
            ExpiresIn=expires_in,
        )

    async def upload_by_key(
        self,
        key: str,
        file_content: bytes,
        content_type: str = "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ) -> str:
        """Overwrite an object at a fully-qualified bucket key.

        Used by the v2 docx autosave path — the case_generation_logs row
        already owns the key, so we don't need the `template_id / filename
        / prefix` layering. Returns the key for symmetry with upload_file.
        """
        self.client.upload_fileobj(
            BytesIO(file_content),
            self.bucket_name,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return key

    async def delete_object(self, key: str) -> None:
        """Delete a single object by its full key. Used by the case_inbox
        accept flow to clean up the staging copy once the petition has
        been re-uploaded under `cases/{case_id}/petition.pdf`. Idempotent
        — S3 returns success even when the key doesn't exist."""
        self.client.delete_object(Bucket=self.bucket_name, Key=key)


r2_service = R2Service()
