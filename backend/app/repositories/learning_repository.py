from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.content import GrammarItem, KanjiItem, VocabularyItem
from app.models.learning import LearningState, ReviewHistory, StudySession
from app.models.user import UserSettings
from app.services.learning_scope import scoped_states_query, settings_levels
from app.utils.enums import ContentType


class LearningRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_state(self, user_id: str, content_type: ContentType, content_id: str) -> LearningState | None:
        stmt = select(LearningState).where(
            LearningState.user_id == user_id,
            LearningState.content_type == content_type,
            LearningState.content_id == content_id,
        )
        return self.db.scalars(stmt).first()

    def list_due_states(self, user_id: str) -> list[LearningState]:
        now = datetime.now(timezone.utc)
        settings = self.db.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
        if settings is None:
            return []
        stmt = scoped_states_query(user_id, settings_levels(settings)).where(
            LearningState.last_review_at.is_not(None),
            (LearningState.next_review_at.is_(None)) | (LearningState.next_review_at <= now),
        )
        return list(self.db.scalars(stmt).all())

    def upsert_state(self, user_id: str, content_type: ContentType, content_id: str) -> LearningState:
        state = self.get_state(user_id, content_type, content_id)
        if state:
            return state
        state = LearningState(user_id=user_id, content_type=content_type, content_id=content_id)
        self.db.add(state)
        self.db.flush()
        return state

    def create_history(self, **payload) -> ReviewHistory:
        history = ReviewHistory(**payload)
        self.db.add(history)
        return history

    def create_session(self, **payload) -> StudySession:
        session = StudySession(**payload)
        self.db.add(session)
        self.db.flush()
        return session

    def get_content_title(self, content_type: ContentType, content_id: str, locale: str = "en") -> tuple[str, str, str]:
        if content_type == ContentType.vocabulary:
            item = self.db.get(VocabularyItem, content_id)
            if not item:
                return ("Unknown vocabulary", "", "N/A")
            localized = next((value for value in item.translations if value.locale == locale), None) or next((value for value in item.translations if value.locale == "en"), None)
            return (item.japanese, localized.translation if localized else item.translation, item.jlpt_level_code)
        if content_type == ContentType.kanji:
            item = self.db.get(KanjiItem, content_id)
            if not item:
                return ("Unknown kanji", "", "N/A")
            localized = next((value for value in item.translations if value.locale == locale), None) or next((value for value in item.translations if value.locale == "en"), None)
            meanings = localized.meanings if localized else item.meanings
            return (item.character, ", ".join(meanings[:3]), item.jlpt_level_code)
        item = self.db.get(GrammarItem, content_id)
        if not item:
            return ("Unknown grammar", "", "N/A")
        localized = next((value for value in item.translations if value.locale == locale), None) or next((value for value in item.translations if value.locale == "en"), None)
        return (item.title, localized.explanation if localized else item.explanation, item.jlpt_level_code)
