from pydantic import BaseModel, EmailStr, Field

from app.schemas.content import JLPTLevelOut
from app.schemas.user import UserOut, UserSettingsOut


class AuthRegisterIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class AuthLoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class AuthTokensOut(BaseModel):
    user: UserOut
    settings: UserSettingsOut
    access_token_expires_minutes: int


class AuthRefreshOut(BaseModel):
    user: UserOut
    settings: UserSettingsOut
    access_token_expires_minutes: int


class AuthSessionOut(BaseModel):
    user: UserOut
    settings: UserSettingsOut
    jlpt_levels: list[JLPTLevelOut]
