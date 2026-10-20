from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.imports import ImportSummaryOut
from app.services.import_service import import_csv
from app.utils.enums import ContentType

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.post("/import/{item_type}", response_model=ImportSummaryOut)
def import_content(
    item_type: ContentType,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportSummaryOut:
    _require_admin(current_user)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(file.file.read())
        tmp_path = Path(tmp.name)
    try:
        summary = import_csv(db, item_type, tmp_path)
        return summary.to_out()
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    finally:
        tmp_path.unlink(missing_ok=True)
