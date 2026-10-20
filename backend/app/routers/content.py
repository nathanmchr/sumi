from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.repositories.content_repository import ContentRepository
from app.schemas.content import DashboardStatsOut, GrammarOut, JLPTLevelOut, KanjiOut, SearchOut, VocabularyOut
from app.services.content_service import grammar_out, kanji_out, search_content, vocabulary_out
from app.services.learning_service import build_dashboard
from app.schemas.content import HomophonePageOut
from app.services.homophone_service import list_homophones

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/levels", response_model=list[JLPTLevelOut])
def levels(db: Session = Depends(get_db)) -> list[JLPTLevelOut]:
    repo = ContentRepository(db)
    return [JLPTLevelOut.model_validate(level, from_attributes=True) for level in repo.list_jlpt_levels()]


@router.get("/dashboard", response_model=DashboardStatsOut)
def dashboard(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DashboardStatsOut:
    return DashboardStatsOut.model_validate(build_dashboard(db, current_user.id))


@router.get("/search", response_model=list[SearchOut])
def search(q: str = Query(min_length=1), locale: Literal["en", "fr"] = "en", db: Session = Depends(get_db)) -> list[SearchOut]:
    return search_content(db, q, locale)


@router.get("/vocabulary", response_model=list[VocabularyOut])
def vocabulary(level: str | None = None, q: str | None = None, locale: Literal["en", "fr"] = "en", db: Session = Depends(get_db)) -> list[VocabularyOut]:
    repo = ContentRepository(db)
    return [vocabulary_out(db, item, locale=locale) for item in repo.list_vocabulary(level, q, locale)]


@router.get("/homophones", response_model=HomophonePageOut)
def homophones(
    q: str = Query(default="", max_length=100),
    locale: Literal["en", "fr"] = "en",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HomophonePageOut:
    """Compare complete same-reading groups, with existing audio and localised senses."""
    return list_homophones(db, q, locale, offset, limit)


@router.get("/vocabulary/{item_id}", response_model=VocabularyOut)
def vocabulary_detail(item_id: str, locale: Literal["en", "fr"] = "en", current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> VocabularyOut:
    repo = ContentRepository(db)
    item = repo.get_vocabulary(item_id)
    if not item:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Vocabulary item not found")
    return vocabulary_out(db, item, current_user.id, locale)


@router.get("/kanji", response_model=list[KanjiOut])
def kanji(level: str | None = None, q: str | None = None, locale: Literal["en", "fr"] = "en", db: Session = Depends(get_db)) -> list[KanjiOut]:
    repo = ContentRepository(db)
    return [kanji_out(db, item, locale=locale) for item in repo.list_kanji(level, q, locale)]


@router.get("/kanji/{item_id}", response_model=KanjiOut)
def kanji_detail(item_id: str, locale: Literal["en", "fr"] = "en", current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> KanjiOut:
    repo = ContentRepository(db)
    item = repo.get_kanji(item_id)
    if not item:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Kanji item not found")
    return kanji_out(db, item, current_user.id, locale)


@router.get("/grammar", response_model=list[GrammarOut])
def grammar(level: str | None = None, q: str | None = None, locale: Literal["en", "fr"] = "en", db: Session = Depends(get_db)) -> list[GrammarOut]:
    repo = ContentRepository(db)
    return [grammar_out(db, item, locale=locale) for item in repo.list_grammar(level, q, locale)]


@router.get("/grammar/{item_id}", response_model=GrammarOut)
def grammar_detail(item_id: str, locale: Literal["en", "fr"] = "en", current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> GrammarOut:
    repo = ContentRepository(db)
    item = repo.get_grammar(item_id)
    if not item:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Grammar item not found")
    return grammar_out(db, item, current_user.id, locale)
