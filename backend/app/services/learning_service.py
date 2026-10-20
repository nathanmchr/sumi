from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.learning import LearningState, ReviewHistory
from app.repositories.learning_repository import LearningRepository
from app.schemas.learning import SessionRecommendationOut
from app.utils.enums import ContentType, ReviewStatus


def recommend_session(db: Session, user_id: str) -> SessionRecommendationOut:
    repo = LearningRepository(db)
    due_count = len(repo.list_due_states(user_id))
    focus = [ContentType.vocabulary, ContentType.grammar] if due_count > 10 else [ContentType.vocabulary, ContentType.kanji]
    minutes = 15 if due_count < 10 else 25 if due_count < 25 else 40
    return SessionRecommendationOut(
        minutes=minutes,
        target_items=max(8, min(30, due_count or 12)),
        focus=focus,
        rationale="Priorise due items, then mix one active recall block with one recognition block.",
    )


STUDY_DAYS_WINDOW = 14
STREAK_LOOKBACK_DAYS = 400


def study_activity(db: Session, user_id: str, today: date | None = None) -> tuple[int, list[date]]:
    """Return the current streak and the study days inside the recent window.

    A day counts once any answer was recorded on it, in the server's local time zone.
    The streak stays alive until the end of today, so it may end yesterday.
    """
    today = today or datetime.now().astimezone().date()
    since = datetime.combine(today - timedelta(days=STREAK_LOOKBACK_DAYS), datetime.min.time()).astimezone()
    stamps = db.query(ReviewHistory.created_at).filter(ReviewHistory.user_id == user_id, ReviewHistory.created_at >= since).all()
    days = {(at if at.tzinfo else at.replace(tzinfo=timezone.utc)).astimezone().date() for (at,) in stamps}
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    window_start = today - timedelta(days=STUDY_DAYS_WINDOW - 1)
    return streak, sorted(day for day in days if window_start <= day <= today)


def build_dashboard(db: Session, user_id: str) -> dict:
    repo = LearningRepository(db)
    due_states = repo.list_due_states(user_id)
    learned = db.query(LearningState).filter(LearningState.user_id == user_id, LearningState.status != ReviewStatus.new).count()
    streak_days, study_days = study_activity(db, user_id)
    progression = {
        "vocabulary": min(100.0, learned * 4.2),
        "grammar": min(100.0, learned * 3.1),
        "kanji": min(100.0, learned * 2.6),
    }
    estimated_minutes = 10 if len(due_states) < 8 else 20 if len(due_states) < 20 else 35
    recommendation = "Start with vocabulary recall, then do one kanji sheet and finish with a grammar pass."
    return {
        "learned_items": learned,
        "due_reviews": len(due_states),
        "streak_days": streak_days,
        "study_days": study_days,
        "estimated_session_minutes": estimated_minutes,
        "progression_by_category": progression,
        "recommendation": recommendation,
    }
