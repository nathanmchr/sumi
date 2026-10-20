from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import hash_token
from app.models.user import User
from app.models.user import RefreshToken
from app.schemas.auth import AuthLoginIn, AuthRegisterIn, AuthSessionOut, AuthTokensOut
from app.schemas.user import UserOut, UserSettingsOut
from app.services.auth_service import authenticate_user, get_user_settings, issue_tokens, register_user, rotate_refresh_token
from app.services.seed_service import seed_reference_data
from app.schemas.content import JLPTLevelOut
from app.models.content import JLPTLevel

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "domain": settings.cookie_domain,
        "path": "/",
    }


@router.post("/register", response_model=AuthTokensOut, status_code=status.HTTP_201_CREATED)
def register(payload: AuthRegisterIn, response: Response, db: Session = Depends(get_db)) -> AuthTokensOut:
    seed_reference_data(db)
    user = register_user(db, payload)
    access_token, refresh_token = issue_tokens(db, user)
    response.set_cookie("access_token", access_token, max_age=settings.access_token_exp_minutes * 60, **_cookie_kwargs())
    response.set_cookie("refresh_token", refresh_token, max_age=settings.refresh_token_exp_days * 24 * 60 * 60, **_cookie_kwargs())
    settings_obj = get_user_settings(db, user.id)
    return AuthTokensOut(
        user=UserOut.model_validate(user, from_attributes=True),
        settings=UserSettingsOut.model_validate(settings_obj, from_attributes=True),
        access_token_expires_minutes=settings.access_token_exp_minutes,
    )


@router.post("/login", response_model=AuthTokensOut)
def login(payload: AuthLoginIn, response: Response, db: Session = Depends(get_db)) -> AuthTokensOut:
    user = authenticate_user(db, payload)
    access_token, refresh_token = issue_tokens(db, user)
    response.set_cookie("access_token", access_token, max_age=settings.access_token_exp_minutes * 60, **_cookie_kwargs())
    response.set_cookie("refresh_token", refresh_token, max_age=settings.refresh_token_exp_days * 24 * 60 * 60, **_cookie_kwargs())
    settings_obj = get_user_settings(db, user.id)
    return AuthTokensOut(
        user=UserOut.model_validate(user, from_attributes=True),
        settings=UserSettingsOut.model_validate(settings_obj, from_attributes=True),
        access_token_expires_minutes=settings.access_token_exp_minutes,
    )


@router.post("/refresh", response_model=AuthTokensOut)
def refresh(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias="refresh_token"),
) -> AuthTokensOut:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required")
    user = rotate_refresh_token(db, refresh_token)
    access_token, new_refresh_token = issue_tokens(db, user)
    response.set_cookie("access_token", access_token, max_age=settings.access_token_exp_minutes * 60, **_cookie_kwargs())
    response.set_cookie("refresh_token", new_refresh_token, max_age=settings.refresh_token_exp_days * 24 * 60 * 60, **_cookie_kwargs())
    settings_obj = get_user_settings(db, user.id)
    return AuthTokensOut(
        user=UserOut.model_validate(user, from_attributes=True),
        settings=UserSettingsOut.model_validate(settings_obj, from_attributes=True),
        access_token_expires_minutes=settings.access_token_exp_minutes,
    )


@router.post("/logout")
def logout(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias="refresh_token"),
) -> dict:
    if refresh_token:
        token = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(refresh_token)).first()
        if token and token.revoked_at is None:
            token.revoked_at = datetime.now(timezone.utc)
            db.commit()
    response.delete_cookie("access_token", **_cookie_kwargs())
    response.delete_cookie("refresh_token", **_cookie_kwargs())
    return {"ok": True}


@router.get("/session", response_model=AuthSessionOut)
def session(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AuthSessionOut:
    settings_obj = get_user_settings(db, current_user.id)
    levels = [JLPTLevelOut.model_validate(level, from_attributes=True) for level in db.query(JLPTLevel).order_by(JLPTLevel.rank.asc()).all()]
    return AuthSessionOut(
        user=UserOut.model_validate(current_user, from_attributes=True),
        settings=UserSettingsOut.model_validate(settings_obj, from_attributes=True),
        jlpt_levels=levels,
    )
