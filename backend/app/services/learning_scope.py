"""Selected levels control course eligibility, never the stored memory state."""

from sqlalchemy import and_, or_, select

from app.models.content import GrammarItem, KanjiItem, VocabularyItem
from app.models.learning import LearningState

MODELS = {"vocabulary": VocabularyItem, "kanji": KanjiItem, "grammar": GrammarItem}


def settings_levels(settings) -> dict:
    return {
        "levels": {kind: getattr(settings, f"{kind}_level_code") for kind in MODELS},
        "min_levels": {kind: getattr(settings, f"{kind}_min_level_code") for kind in MODELS},
    }


def level_codes(scope: dict, kind: str) -> tuple[str, ...]:
    minimum = scope.get("min_levels", scope["levels"])[kind]
    maximum = scope["levels"][kind]
    return tuple(f"N{rank}" for rank in range(int(minimum[1]), int(maximum[1]) - 1, -1))


def scoped_states_query(user_id: str, scope: dict):
    categories = scope.get("categories", MODELS)
    stmt = select(LearningState).where(
        LearningState.user_id == user_id,
        or_(*(
            and_(
                LearningState.content_type == kind,
                select(model.id).where(
                    model.id == LearningState.content_id,
                    model.jlpt_level_code.in_(level_codes(scope, kind)),
                ).exists(),
            )
            for kind, model in MODELS.items() if kind in categories
        )),
    )
    if scope.get("content_id"):
        stmt = stmt.where(LearningState.content_id == scope["content_id"])
    return stmt
