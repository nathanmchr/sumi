from typing import Literal
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.learning import DueItemOut, SessionRecommendationOut
from app.services.learning_service import recommend_session
from app.repositories.learning_repository import LearningRepository

from app.schemas.quiz import AnswerIn, AnswerOut, QuestionOut, QuizStartIn, QuizTurnOut
from app.services.quiz_service import start_session, get_turn, next_question, answer_question, begin_question
from app.services.fsrs_service import memory_status

router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("/due", response_model=list[DueItemOut])
def due_items(locale: Literal["en", "fr"] = "en", current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[DueItemOut]:
    repo = LearningRepository(db)
    items = []
    for state in repo.list_due_states(current_user.id):
        title, subtitle, level_code = repo.get_content_title(state.content_type, state.content_id, locale)
        items.append(
            DueItemOut(
                content_type=state.content_type,
                content_id=state.content_id,
                title=title,
                subtitle=subtitle,
                jlpt_level_code=level_code,
                next_review_at=state.next_review_at,
                status=memory_status(state, datetime.now(timezone.utc)),
            )
        )
    return items


@router.get("/recommendation", response_model=SessionRecommendationOut)
def recommendation(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SessionRecommendationOut:
    return recommend_session(db, current_user.id)


@router.post("/reviews", deprecated=True)
def legacy_review(current_user: User = Depends(get_current_user)):
    raise HTTPException(410, "Manual ratings have been replaced by study questions")


@router.post("/sessions", response_model=QuizTurnOut)
def create_session(payload: QuizStartIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return start_session(db, current_user.id, payload)


@router.get("/sessions/{session_id}", response_model=QuizTurnOut)
def resume_session(session_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_turn(db, current_user.id, str(session_id))


@router.post("/sessions/{session_id}/next", response_model=QuizTurnOut)
def advance_session(session_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return next_question(db, current_user.id, str(session_id))


@router.post("/questions/{question_id}/answer", response_model=AnswerOut)
def answer(question_id: UUID, payload: AnswerIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return answer_question(db, current_user.id, str(question_id), str(payload.option_id))


@router.post("/questions/{question_id}/begin", response_model=QuestionOut)
def begin(question_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return begin_question(db, current_user.id, str(question_id))
