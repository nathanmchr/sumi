from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import UserOut, UserProfileUpdate, UserSettingsOut, UserSettingsUpdate
from app.services.auth_service import get_user_settings, update_user_profile, update_user_settings

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user, from_attributes=True)


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    user = update_user_profile(db, current_user.id, payload)
    return UserOut.model_validate(user, from_attributes=True)


@router.get("/me/settings", response_model=UserSettingsOut)
def read_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserSettingsOut:
    settings = get_user_settings(db, current_user.id)
    return UserSettingsOut.model_validate(settings, from_attributes=True)


@router.put("/me/settings", response_model=UserSettingsOut)
def change_settings(payload: UserSettingsUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserSettingsOut:
    settings = update_user_settings(db, current_user.id, payload)
    return UserSettingsOut.model_validate(settings, from_attributes=True)
