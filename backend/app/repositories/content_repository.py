from __future__ import annotations

from sqlalchemy import Text, and_, case, cast, false, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, load_only, raiseload, selectinload

from app.models.content import (
    ExampleSentence,
    ExampleSentenceTranslation,
    GrammarItem,
    GrammarTranslation,
    JLPTLevel,
    KanjiItem,
    KanjiTranslation,
    VocabularyItem,
    VocabularyKanjiLink,
    VocabularyTranslation,
)
from app.models.learning import LearningState
from app.utils.enums import ContentType
from app.utils.romaji import normalize_romaji, romaji_search_key
from app.services.content_identity import resolve_content_id


def _romaji_rank(column, term: str):
    # Variants are separated by " / "; an exact variant outranks substrings.
    exact = or_(
        column == term,
        column.startswith(f"{term} / ", autoescape=True),
        column.endswith(f" / {term}", autoescape=True),
        column.contains(f" / {term} / ", autoescape=True),
    )
    return case((exact, 0), else_=1)


class ContentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_jlpt_levels(self) -> list[JLPTLevel]:
        stmt = select(JLPTLevel).order_by(JLPTLevel.rank.asc())
        return list(self.db.scalars(stmt).all())

    def get_jlpt_level(self, code: str) -> JLPTLevel | None:
        return self.db.get(JLPTLevel, code)

    def list_homophone_candidates(self) -> list[VocabularyItem]:
        # No examples, kanji links or learning states are needed for comparison.
        stmt = select(VocabularyItem).options(
            load_only(
                VocabularyItem.id, VocabularyItem.japanese, VocabularyItem.reading,
                VocabularyItem.catalog_id,
                VocabularyItem.translation, VocabularyItem.romaji_search,
                VocabularyItem.jlpt_level_code, VocabularyItem.audio_url,
            ),
            selectinload(VocabularyItem.translations).load_only(
                VocabularyTranslation.locale, VocabularyTranslation.translation,
            ),
            raiseload("*"),
        )
        return list(self.db.scalars(stmt).all())

    def list_vocabulary(self, level_code: str | None = None, search: str | None = None, locale: str = "en", limit: int | None = None) -> list[VocabularyItem]:
        stmt = (
            select(VocabularyItem)
            .options(
                selectinload(VocabularyItem.translations),
                selectinload(VocabularyItem.example_sentences).selectinload(ExampleSentence.translations),
                selectinload(VocabularyItem.kanji_links)
                .selectinload(VocabularyKanjiLink.kanji_item)
                .selectinload(KanjiItem.translations),
            )
            .order_by(VocabularyItem.source_order.asc().nulls_last(), VocabularyItem.jlpt_level_code.asc(), VocabularyItem.japanese.asc())
        )
        if level_code:
            stmt = stmt.where(VocabularyItem.jlpt_level_code == level_code)
        if search and (term := search.strip()):
            romaji = normalize_romaji(term)
            stmt = stmt.where(or_(
                VocabularyItem.japanese.icontains(term, autoescape=True),
                VocabularyItem.reading.icontains(term, autoescape=True),
                VocabularyItem.romaji_search.icontains(romaji, autoescape=True) if romaji else false(),
                VocabularyItem.translation.icontains(term, autoescape=True),
                VocabularyItem.translations.any(and_(
                    VocabularyTranslation.locale == locale,
                    VocabularyTranslation.translation.icontains(term, autoescape=True),
                )),
            ))
            stmt = stmt.order_by(None).order_by(
                _romaji_rank(VocabularyItem.romaji_search, romaji),
                VocabularyItem.source_order.asc().nulls_last(),
                VocabularyItem.jlpt_level_code.asc(), VocabularyItem.japanese.asc(),
            )
        if limit:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def list_kanji(self, level_code: str | None = None, search: str | None = None, locale: str = "en", limit: int | None = None) -> list[KanjiItem]:
        stmt = (
            select(KanjiItem)
            .options(
                selectinload(KanjiItem.translations),
                selectinload(KanjiItem.vocabulary_links)
                .selectinload(VocabularyKanjiLink.vocabulary_item)
                .selectinload(VocabularyItem.translations),
            )
            .order_by(KanjiItem.source_order.asc().nulls_last(), KanjiItem.jlpt_level_code.asc(), KanjiItem.character.asc())
        )
        if level_code:
            stmt = stmt.where(KanjiItem.jlpt_level_code == level_code)
        if search and (term := search.strip()):
            romaji = normalize_romaji(term)
            stmt = stmt.where(or_(
                KanjiItem.character.icontains(term, autoescape=True),
                KanjiItem.romaji_search.icontains(romaji, autoescape=True) if romaji else false(),
                cast(KanjiItem.meanings, Text).icontains(term, autoescape=True),
                KanjiItem.translations.any(and_(
                    KanjiTranslation.locale == locale,
                    cast(KanjiTranslation.meanings, Text).icontains(term, autoescape=True),
                )),
            ))
            stmt = stmt.order_by(None).order_by(
                _romaji_rank(KanjiItem.romaji_search, romaji),
                KanjiItem.source_order.asc().nulls_last(),
                KanjiItem.jlpt_level_code.asc(), KanjiItem.character.asc(),
            )
        if limit:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def list_grammar(self, level_code: str | None = None, search: str | None = None, locale: str = "en", limit: int | None = None) -> list[GrammarItem]:
        stmt = select(GrammarItem).options(selectinload(GrammarItem.translations)).order_by(GrammarItem.source_order.asc().nulls_last(), GrammarItem.jlpt_level_code.asc(), GrammarItem.title.asc())
        if level_code:
            stmt = stmt.where(GrammarItem.jlpt_level_code == level_code)
        if search and (term := search.strip()):
            romaji = normalize_romaji(term)
            stmt = stmt.where(or_(
                GrammarItem.title.icontains(term, autoescape=True),
                GrammarItem.romaji_search.icontains(romaji, autoescape=True) if romaji else false(),
                GrammarItem.explanation.icontains(term, autoescape=True),
                GrammarItem.structure.icontains(term, autoescape=True),
                GrammarItem.translations.any(and_(
                    GrammarTranslation.locale == locale,
                    GrammarTranslation.explanation.icontains(term, autoescape=True),
                )),
            ))
            stmt = stmt.order_by(None).order_by(
                _romaji_rank(GrammarItem.romaji_search, romaji),
                GrammarItem.source_order.asc().nulls_last(),
                GrammarItem.jlpt_level_code.asc(), GrammarItem.title.asc(),
            )
        if limit:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def get_vocabulary(self, item_id: str) -> VocabularyItem | None:
        item_id = resolve_content_id(self.db, "vocabulary", item_id)
        stmt = (
            select(VocabularyItem)
            .where(VocabularyItem.id == item_id)
            .options(
                selectinload(VocabularyItem.translations),
                selectinload(VocabularyItem.example_sentences).selectinload(ExampleSentence.translations),
                selectinload(VocabularyItem.kanji_links)
                .selectinload(VocabularyKanjiLink.kanji_item)
                .selectinload(KanjiItem.translations),
            )
        )
        return self.db.scalars(stmt).one_or_none()

    def get_vocabulary_by_slug(self, slug: str) -> VocabularyItem | None:
        return self.db.query(VocabularyItem).filter(VocabularyItem.slug == slug).first() or self.get_vocabulary(slug)

    def get_kanji(self, item_id: str) -> KanjiItem | None:
        item_id = resolve_content_id(self.db, "kanji", item_id)
        stmt = (
            select(KanjiItem)
            .where(KanjiItem.id == item_id)
            .options(
                selectinload(KanjiItem.translations),
                selectinload(KanjiItem.vocabulary_links)
                .selectinload(VocabularyKanjiLink.vocabulary_item)
                .selectinload(VocabularyItem.translations),
            )
        )
        return self.db.scalars(stmt).one_or_none()

    def get_kanji_by_character(self, character: str) -> KanjiItem | None:
        return self.db.query(KanjiItem).filter(KanjiItem.character == character).first()

    def get_grammar(self, item_id: str) -> GrammarItem | None:
        return self.db.get(GrammarItem, resolve_content_id(self.db, "grammar", item_id))

    def get_grammar_by_slug(self, slug: str) -> GrammarItem | None:
        return self.db.query(GrammarItem).filter(GrammarItem.slug == slug).first() or self.get_grammar(slug)

    def upsert_jlpt_level(self, code: str, rank: int, label: str, description: str | None = None) -> None:
        stmt = insert(JLPTLevel).values(code=code, rank=rank, label=label, description=description)
        stmt = stmt.on_conflict_do_update(index_elements=[JLPTLevel.code], set_={"rank": rank, "label": label, "description": description})
        self.db.execute(stmt)

    def upsert_vocabulary(self, payload: dict) -> VocabularyItem:
        payload = dict(payload)
        explicit = payload.pop("romaji", "")
        if explicit.strip():
            payload["romaji"] = explicit.strip()
        payload["romaji_search"] = romaji_search_key([payload.get("reading") or "", payload.get("japanese") or ""], explicit)
        stmt = insert(VocabularyItem).values(**payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=[VocabularyItem.slug],
            set_={k: payload[k] for k in payload if k != "slug"},
        ).returning(VocabularyItem)
        return self.db.scalars(stmt).one()

    def upsert_vocabulary_translation(self, payload: dict) -> None:
        stmt = insert(VocabularyTranslation).values(**payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=[VocabularyTranslation.vocabulary_item_id, VocabularyTranslation.locale],
            set_={k: payload[k] for k in payload if k not in {"vocabulary_item_id", "locale"}},
        )
        self.db.execute(stmt)

    def upsert_kanji(self, payload: dict) -> KanjiItem:
        payload = dict(payload)
        payload["romaji_search"] = romaji_search_key([*payload.get("onyomi", []), *payload.get("kunyomi", [])])
        stmt = insert(KanjiItem).values(**payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=[KanjiItem.character],
            set_={k: payload[k] for k in payload if k != "character"},
        ).returning(KanjiItem)
        return self.db.scalars(stmt).one()

    def upsert_kanji_translation(self, payload: dict) -> None:
        stmt = insert(KanjiTranslation).values(**payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=[KanjiTranslation.kanji_item_id, KanjiTranslation.locale],
            set_={k: payload[k] for k in payload if k not in {"kanji_item_id", "locale"}},
        )
        self.db.execute(stmt)

    def upsert_grammar(self, payload: dict) -> GrammarItem:
        payload = dict(payload)
        payload["romaji_search"] = normalize_romaji(payload.get("structure") or "")
        stmt = insert(GrammarItem).values(**payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=[GrammarItem.slug],
            set_={k: payload[k] for k in payload if k != "slug"},
        ).returning(GrammarItem)
        return self.db.scalars(stmt).one()

    def upsert_grammar_translation(self, payload: dict) -> None:
        stmt = insert(GrammarTranslation).values(**payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=[GrammarTranslation.grammar_item_id, GrammarTranslation.locale],
            set_={k: payload[k] for k in payload if k not in {"grammar_item_id", "locale"}},
        )
        self.db.execute(stmt)

    def upsert_example_translation(self, payload: dict) -> None:
        stmt = insert(ExampleSentenceTranslation).values(**payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=[ExampleSentenceTranslation.example_sentence_id, ExampleSentenceTranslation.locale],
            set_={"translation": payload["translation"]},
        )
        self.db.execute(stmt)

    def replace_vocabulary_links(self, vocabulary_id: str, links: list[dict]) -> None:
        self.db.query(VocabularyKanjiLink).filter(VocabularyKanjiLink.vocabulary_item_id == vocabulary_id).delete()
        for link in links:
            self.db.add(VocabularyKanjiLink(vocabulary_item_id=vocabulary_id, **link))

    def upsert_example(self, payload: dict) -> ExampleSentence:
        example_id = payload.pop("id", None)
        if example_id:
            existing = self.db.get(ExampleSentence, example_id)
            if existing:
                for key, value in payload.items():
                    setattr(existing, key, value)
                return existing
        lookup = self.db.query(ExampleSentence).filter(ExampleSentence.text == payload.get("text"))
        vocab_id = payload.get("vocabulary_item_id")
        grammar_id = payload.get("grammar_item_id")
        if vocab_id:
            lookup = lookup.filter(ExampleSentence.vocabulary_item_id == vocab_id)
        if grammar_id:
            lookup = lookup.filter(ExampleSentence.grammar_item_id == grammar_id)
        existing = lookup.first()
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            return existing
        example = ExampleSentence(**payload)
        self.db.add(example)
        return example

    def commit(self) -> None:
        self.db.commit()
