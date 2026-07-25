import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.foundation import (
    BuyerProofDocument,
    ContractTemplate,
    FieldInspectionPhoto,
    TransactionDocument,
)
from app.services.document_storage import store_content


@dataclass(frozen=True)
class FileRecord:
    item: Any
    organization_id: UUID
    namespace: str
    file_name: str
    content_type: str
    content: bytes
    content_attribute: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy database-backed private files into the configured S3 storage provider."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Persist object uploads and clear copied database bytes. "
            "Without this flag, only count."
        ),
    )
    return parser.parse_args()


def pending_files(db: Session) -> Iterable[FileRecord]:
    for template in db.scalars(
        select(ContractTemplate).where(
            ContractTemplate.storage_provider == "database",
            ContractTemplate.file_data.is_not(None),
        )
    ):
        assert template.file_data is not None
        yield FileRecord(
            template,
            template.organization_id,
            "contract-templates",
            template.file_name,
            template.content_type,
            bytes(template.file_data),
            "file_data",
        )
    for document in db.scalars(
        select(TransactionDocument).where(
            TransactionDocument.storage_provider == "database",
            TransactionDocument.file_data.is_not(None),
            TransactionDocument.deleted_at.is_(None),
        )
    ):
        assert document.file_data is not None
        yield FileRecord(
            document,
            document.organization_id,
            f"transactions/{document.transaction_id}",
            document.file_name,
            document.content_type,
            bytes(document.file_data),
            "file_data",
        )
    for photo in db.scalars(
        select(FieldInspectionPhoto).where(
            FieldInspectionPhoto.storage_provider == "database",
            FieldInspectionPhoto.image_data.is_not(None),
        )
    ):
        assert photo.image_data is not None
        yield FileRecord(
            photo,
            photo.organization_id,
            f"field-inspections/{photo.inspection_id}",
            photo.file_name,
            photo.content_type,
            bytes(photo.image_data),
            "image_data",
        )
    for proof in db.scalars(
        select(BuyerProofDocument).where(
            BuyerProofDocument.storage_provider == "database",
            BuyerProofDocument.file_data.is_not(None),
            BuyerProofDocument.deleted_at.is_(None),
        )
    ):
        assert proof.file_data is not None
        yield FileRecord(
            proof,
            proof.organization_id,
            f"buyers/{proof.buyer_id}/proof-of-funds",
            proof.file_name,
            proof.content_type,
            bytes(proof.file_data),
            "file_data",
        )


def main() -> None:
    args = parse_args()
    settings = get_settings()
    if settings.document_storage_provider != "s3":
        raise SystemExit("Set DOCUMENT_STORAGE_PROVIDER=s3 before running this migration.")
    with SessionLocal() as db:
        records = list(pending_files(db))
        if not args.apply:
            print(f"Dry run: {len(records)} database-backed private file(s) are ready to copy.")
            return
        for index, record in enumerate(records, start=1):
            stored = store_content(
                organization_id=record.organization_id,
                namespace=record.namespace,
                record_id=record.item.id,
                file_name=record.file_name,
                content_type=record.content_type,
                content=record.content,
                settings=settings,
            )
            record.item.storage_provider = stored.provider
            record.item.storage_key = stored.key
            record.item.malware_scan_status = stored.malware_scan_status
            record.item.retention_until = stored.retention_until
            setattr(record.item, record.content_attribute, None)
            db.commit()
            print(f"Copied {index}/{len(records)}: {record.item.id}")
        print(f"Completed: {len(records)} private file(s) copied to S3 storage.")


if __name__ == "__main__":
    main()
