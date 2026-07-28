import re
import socket
import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from uuid import UUID

import boto3  # type: ignore[import-untyped]

from app.core.config import Settings, get_settings

ALLOWED_CONTENT_TYPES = {
    "application/msword",
    "application/octet-stream",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "image/jpeg",
    "image/heic",
    "image/png",
    "image/tiff",
    "image/webp",
    "text/csv",
    "text/plain",
}


@dataclass(frozen=True)
class StoredContent:
    provider: str
    key: str | None
    database_bytes: bytes | None
    malware_scan_status: str
    retention_until: datetime


def validate_document_content(content: bytes, content_type: str) -> None:
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    if normalized_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("Use a PDF, Word document, image file, or CSV statement.")
    if content.startswith(b"MZ"):
        raise ValueError("Executable files cannot be stored.")
    if normalized_type == "application/pdf" and not content.startswith(b"%PDF"):
        raise ValueError("The uploaded file does not contain a valid PDF header.")


def scan_document(content: bytes, settings: Settings | None = None) -> str:
    active_settings = settings or get_settings()
    if active_settings.document_malware_scanner == "disabled":
        if active_settings.document_malware_scan_required:
            raise ValueError("Document scanning is required but CLAMAV_HOST is not configured.")
        return "not_configured"
    if not active_settings.clamav_host:
        if active_settings.document_malware_scan_required:
            raise ValueError("Document scanning requires CLAMAV_HOST.")
        return "scan_error"
    try:
        with socket.create_connection(
            (active_settings.clamav_host, active_settings.clamav_port),
            timeout=active_settings.clamav_timeout_seconds,
        ) as connection:
            connection.sendall(b"zINSTREAM\0")
            for offset in range(0, len(content), 64 * 1024):
                chunk = content[offset : offset + 64 * 1024]
                connection.sendall(struct.pack("!I", len(chunk)))
                connection.sendall(chunk)
            connection.sendall(struct.pack("!I", 0))
            response = bytearray()
            while True:
                block = connection.recv(4096)
                if not block:
                    break
                response.extend(block)
                if b"\0" in block:
                    break
        result = bytes(response).rstrip(b"\0").decode("utf-8", errors="replace")
    except OSError as exc:
        if active_settings.document_malware_scan_required:
            raise ValueError("Document scanning is temporarily unavailable.") from exc
        return "scan_error"
    if result.endswith(" OK"):
        return "clean"
    if " FOUND" in result:
        raise ValueError("The uploaded document failed malware scanning.")
    if active_settings.document_malware_scan_required:
        raise ValueError("Document scanning returned an unknown result.")
    return "scan_error"


def store_content(
    *,
    organization_id: UUID,
    namespace: str,
    record_id: UUID,
    file_name: str,
    content_type: str,
    content: bytes,
    settings: Settings | None = None,
) -> StoredContent:
    active_settings = settings or get_settings()
    validate_document_content(content, content_type)
    scan_status = scan_document(content, active_settings)
    retention_until = datetime.now(UTC) + timedelta(days=active_settings.document_retention_days)
    if active_settings.document_storage_provider == "database":
        return StoredContent(
            provider="database",
            key=None,
            database_bytes=content,
            malware_scan_status=scan_status,
            retention_until=retention_until,
        )
    blockers = active_settings.document_storage_configuration_blockers
    if blockers:
        raise ValueError(f"Private object storage is missing: {', '.join(blockers)}.")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", file_name).strip(".-") or "document"
    key = f"{organization_id}/{namespace}/{record_id}/{safe_name}"
    client = s3_client(active_settings)
    client.put_object(
        Bucket=active_settings.document_storage_bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
        Metadata={"record-id": str(record_id), "malware-scan-status": scan_status},
    )
    return StoredContent(
        provider="s3",
        key=key,
        database_bytes=None,
        malware_scan_status=scan_status,
        retention_until=retention_until,
    )


def read_content(
    *,
    provider: str,
    key: str | None,
    database_bytes: bytes | None,
    settings: Settings | None = None,
) -> bytes:
    if provider == "database":
        if database_bytes is None:
            raise ValueError("The stored document body is unavailable.")
        return database_bytes
    if not key:
        raise ValueError("The object-storage key is unavailable.")
    active_settings = settings or get_settings()
    response: dict[str, Any] = s3_client(active_settings).get_object(
        Bucket=active_settings.document_storage_bucket,
        Key=key,
    )
    body: Any = response["Body"]
    return bytes(body.read())


def create_download_url(
    *,
    provider: str,
    key: str | None,
    fallback_url: str,
    settings: Settings | None = None,
) -> tuple[str, datetime]:
    active_settings = settings or get_settings()
    expires_at = datetime.now(UTC) + timedelta(
        seconds=active_settings.document_storage_download_ttl_seconds
    )
    if provider == "database":
        return fallback_url, expires_at
    if not key:
        raise ValueError("The object-storage key is unavailable.")
    url = s3_client(active_settings).generate_presigned_url(
        "get_object",
        Params={"Bucket": active_settings.document_storage_bucket, "Key": key},
        ExpiresIn=active_settings.document_storage_download_ttl_seconds,
    )
    return str(url), expires_at


def delete_content(
    *,
    provider: str,
    key: str | None,
    settings: Settings | None = None,
) -> None:
    if provider != "s3" or not key:
        return
    active_settings = settings or get_settings()
    s3_client(active_settings).delete_object(
        Bucket=active_settings.document_storage_bucket,
        Key=key,
    )


@lru_cache(maxsize=4)
def _s3_client(
    endpoint_url: str,
    region: str,
    access_key_id: str,
    secret_access_key: str,
) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )


def s3_client(settings: Settings) -> Any:
    blockers = settings.document_storage_configuration_blockers
    if blockers:
        raise ValueError(f"Private object storage is missing: {', '.join(blockers)}.")
    return _s3_client(
        settings.document_storage_endpoint_url or "",
        settings.document_storage_region,
        settings.document_storage_access_key_id or "",
        settings.document_storage_secret_access_key or "",
    )
