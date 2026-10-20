from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.lesson import LessonProgress
from app.schemas.lesson import LessonCommand, LessonState, LessonSummary
from app.services import lesson_service as service

router = APIRouter(prefix="/lessons", tags=["lessons"])


@router.get("", response_model=list[LessonSummary])
def lessons(level: Literal["N5", "N4", "N3", "N2", "N1"] = "N5", locale: Literal["en", "fr"] = "en",
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.list_lessons(db, user.id, level, locale)


@router.get("/{lesson_id}", response_model=LessonState)
def lesson(lesson_id: str, locale: Literal["en", "fr"] = "en", step: int | None = Query(None, ge=0),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = service.require_lesson(db, lesson_id)
    return service.state(db, item, db.get(LessonProgress, (user.id, lesson_id)), locale, step, user_id=user.id)


@router.post("/{lesson_id}/progress", response_model=LessonState)
def progress(lesson_id: str, payload: LessonCommand, locale: Literal["en", "fr"] = "en",
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        result = service.command(db, user.id, lesson_id, payload, locale)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
