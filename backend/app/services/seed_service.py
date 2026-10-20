from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.import_service import ensure_reference_levels, import_csv
from app.utils.enums import ContentType


def seed_reference_data(db: Session) -> None:
    ensure_reference_levels(db)


def seed_sample_content(db: Session) -> None:
    base = Path(__file__).resolve().parents[2] / "seed"
    for filename, item_type in [
        ("vocabulary.csv", ContentType.vocabulary),
        ("kanji.csv", ContentType.kanji),
        ("grammar.csv", ContentType.grammar),
    ]:
        csv_path = base / filename
        if csv_path.exists():
            import_csv(db, item_type, csv_path)

