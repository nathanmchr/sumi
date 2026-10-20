from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token, hash_password, hash_token, verify_and_update_password
from app.models.content import JLPTLevel
from app.models.learning import StudySession
from app.models.user import RefreshToken, User, UserSettings
from app.schemas.auth import AuthLoginIn, AuthRegisterIn
from app.schemas.user import UserProfileUpdate, UserSettingsUpdate
from app.services.learning_scope import MODELS, settings_levels
from app.utils.enums import FuriganaDisplayMode

settings = get_settings()


def _default_settings(db: Session, user_id: str) -> UserSettings:
    levels = db.query(JLPTLevel).order_by(JLPTLevel.rank.asc()).all()
    default_level = levels[0].code if levels else "N5"
    return UserSettings(
        user_id=user_id,
        vocabulary_level_code=default_level,
        vocabulary_min_level_code=default_level,
        grammar_level_code=default_level,
        grammar_min_level_code=default_level,
        kanji_level_code=default_level,
        kanji_min_level_code=default_level,
        furigana_display_mode=FuriganaDisplayMode.always.value,
        furigana_helper_enabled=False,
        daily_goal_minutes=20,
        interface_locale="en",
        content_locale="en",
    )


def register_user(db: Session, payload: AuthRegisterIn) -> User:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    db.add(_default_settings(db, user.id))
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, payload: AuthLoginIn) -> User:
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    is_valid, updated_hash = verify_and_update_password(payload.password, user.hashed_password)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if updated_hash:
        user.hashed_password = updated_hash
        db.commit()
        db.refresh(user)
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    return user


def issue_tokens(db: Session, user: User) -> tuple[str, str]:
    access_token = create_access_token({"sub": user.id, "email": user.email})
    refresh_token = create_refresh_token({"sub": user.id, "email": user.email})
    token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_exp_days),
    )
    db.add(token)
    db.commit()
    return access_token, refresh_token


def rotate_refresh_token(db: Session, refresh_token_value: str) -> User:
    from app.core.security import decode_token

    try:
        payload = decode_token(refresh_token_value)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token") from exc
    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    token_hash = hash_token(refresh_token_value)
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
                      .execution_options(populate_existing=True))
    now = datetime.now(timezone.utc)
    expires_at = token.expires_at if token else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not token or token.revoked_at is not None or expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = db.get(User, token.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    token.revoked_at = now
    # The caller issues the replacement in this same transaction. A failed
    # issuance must not consume the user's last working refresh token.
    db.flush()
    return user


def get_user_settings(db: Session, user_id: str) -> UserSettings:
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        settings = _default_settings(db, user_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def update_user_settings(db: Session, user_id: str, payload: UserSettingsUpdate) -> UserSettings:
    # Same lock as question/answer operations: a removed level cannot receive
    # another answer after this settings transaction has completed.
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    settings = get_user_settings(db, user_id)
    previous_levels = settings_levels(settings)
    settings.vocabulary_level_code = payload.vocabulary_level_code
    settings.vocabulary_min_level_code = payload.vocabulary_min_level_code
    settings.grammar_level_code = payload.grammar_level_code
    settings.grammar_min_level_code = payload.grammar_min_level_code
    settings.kanji_level_code = payload.kanji_level_code
    settings.kanji_min_level_code = payload.kanji_min_level_code
    settings.furigana_display_mode = payload.furigana_display_mode.value
    settings.furigana_helper_enabled = payload.furigana_helper_enabled and payload.furigana_display_mode != FuriganaDisplayMode.hidden
    # Older clients must not silently disable a preference they do not expose.
    if "romaji_enabled" in payload.model_fields_set:
        settings.romaji_enabled = payload.romaji_enabled
    settings.daily_goal_minutes = payload.daily_goal_minutes
    settings.interface_locale = payload.interface_locale
    settings.content_locale = payload.content_locale
    updated_levels = settings_levels(settings)
    changed = {
        kind for kind in MODELS
        if any(previous_levels[bound][kind] != updated_levels[bound][kind]
               for bound in ("levels", "min_levels"))
    }
    if changed:
        for session in db.scalars(select(StudySession).where(
            StudySession.user_id == user_id, StudySession.ended_at.is_(None)
        )):
            if session.snapshot.get("scheduler") == "fsrs6" and changed.intersection(session.snapshot.get("categories", [])):
                # Keep questions, history and every LearningState unchanged.
                # The next course starts with the new scope and existing memory.
                session.ended_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)
    return settings


def update_user_profile(db: Session, user_id: str, payload: UserProfileUpdate) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.full_name = payload.full_name
    db.commit()
    db.refresh(user)
    return user
