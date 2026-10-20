from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.utils.enums import FuriganaDisplayMode


JLPTLevelCode = Literal["N5", "N4", "N3", "N2", "N1"]


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    is_admin: bool = False


class UserProfileUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)


class UserSettingsOut(BaseModel):
    user_id: str
    vocabulary_level_code: JLPTLevelCode
    vocabulary_min_level_code: JLPTLevelCode
    grammar_level_code: JLPTLevelCode
    grammar_min_level_code: JLPTLevelCode
    kanji_level_code: JLPTLevelCode
    kanji_min_level_code: JLPTLevelCode
    furigana_display_mode: FuriganaDisplayMode
    furigana_helper_enabled: bool = False
    romaji_enabled: bool = False
    daily_goal_minutes: int
    interface_locale: Literal["en", "fr"]
    content_locale: Literal["en", "fr"]


class UserSettingsUpdate(BaseModel):
    vocabulary_level_code: JLPTLevelCode
    vocabulary_min_level_code: JLPTLevelCode | None = None
    grammar_level_code: JLPTLevelCode
    grammar_min_level_code: JLPTLevelCode | None = None
    kanji_level_code: JLPTLevelCode
    kanji_min_level_code: JLPTLevelCode | None = None
    furigana_display_mode: FuriganaDisplayMode = FuriganaDisplayMode.always
    furigana_helper_enabled: bool = False
    romaji_enabled: bool = False
    daily_goal_minutes: int = Field(default=20, ge=5, le=240)
    interface_locale: Literal["en", "fr"] = "en"
    content_locale: Literal["en", "fr"] = "en"

    @model_validator(mode="after")
    def validate_level_ranges(self):
        for category in ("vocabulary", "grammar", "kanji"):
            maximum = getattr(self, f"{category}_level_code")
            minimum = getattr(self, f"{category}_min_level_code")
            if minimum is None:
                # Older clients submitting a single level retain that meaning.
                minimum = maximum
                setattr(self, f"{category}_min_level_code", minimum)
            if int(minimum[1]) < int(maximum[1]):
                raise ValueError(f"{category}: minimum difficulty must not exceed maximum difficulty")
        return self
