"""Resolve public catalogue IDs and historical links to stable database keys."""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.content import ContentAlias, GrammarItem, KanjiItem, VocabularyItem

MODELS = {"vocabulary": VocabularyItem, "grammar": GrammarItem, "kanji": KanjiItem}


def resolve_content_id(db: Session, kind: str, identity: str) -> str:
    model = MODELS[kind]
    found = db.scalar(select(model.id).where(or_(model.id == identity, model.catalog_id == identity)))
    if found:
        return found
    alias = db.get(ContentAlias, (kind, identity))
    return alias.content_id if alias else identity
