from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.content import GrammarItem, VocabularyItem
from app.models.learning import (
    GrammarExercise,
    LearningState,
    ReviewHistory,
    StudyQuestion,
    StudySession,
)
from app.models.user import User
from app.schemas.quiz import AnswerOut, QuestionOut, QuizStartIn, QuizTurnOut
from app.services.fsrs_service import utc
from app.services.acquisition_service import (
    REQUIRED_SUCCESSES,
    MEANING_TYPES,
    acquiring,
    begins_acquisition,
    initial_successes,
    remaining_successes,
    ready_for_recall,
    record_answer,
    memory_progress,
)
from app.services.quiz_choices import RNG, choose_distractors
from app.services.vocabulary_audio import preferred_audio_url
from app.services.content_identity import resolve_content_id
from app.services.learning_scope import MODELS, level_codes, scoped_states_query, settings_levels
from app.utils.enums import ContentType

def now_utc():
    return datetime.now(timezone.utc)


def lock_user(db: Session, user_id: str) -> User:
    # Serializes session creation, issuing questions and answering, including first
    # reviews for items that do not yet have a LearningState row to lock.
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user:
        raise HTTPException(404, "User not found")
    return user


def owned_session(db: Session, user_id: str, session_id: str) -> StudySession:
    session = db.scalar(
        select(StudySession).where(
            StudySession.id == session_id, StudySession.user_id == user_id
        )
    )
    if not session or session.snapshot.get("scheduler") != "fsrs6":
        raise HTTPException(404, "Study session not found")
    return session


def latest_question(db: Session, session_id: str):
    return db.scalar(
        select(StudyQuestion)
        .where(StudyQuestion.session_id == session_id)
        .order_by(StudyQuestion.created_at.desc(), StudyQuestion.id.desc())
        .limit(1)
    )


def question_in_scope(db: Session, session: StudySession, question: StudyQuestion) -> bool:
    scope = session.snapshot
    kind = question.content_type
    if kind not in scope["categories"] or (
        scope.get("content_id") and question.content_id != scope["content_id"]
    ):
        return False
    item = db.get(MODELS[kind], question.content_id)
    return item is not None and item.jlpt_level_code in level_codes(scope, kind)


def ensure_introduction(db: Session, question: StudyQuestion) -> None:
    # Also upgrade questions issued before the discovery step was introduced.
    if (
        question.content_type != "vocabulary"
        or question.answered_at
        or "requires_introduction" in question.prompt
    ):
        return
    state = db.scalar(
        select(LearningState).where(
            LearningState.user_id == question.user_id,
            LearningState.content_type == ContentType.vocabulary,
            LearningState.content_id == question.content_id,
        )
    )
    question.prompt = {
        **question.prompt,
        "requires_introduction": state is None or state.last_review_at is None,
    }


def needs_introduction(question: StudyQuestion) -> bool:
    return bool(
        question.prompt.get("requires_introduction")
        and not question.prompt.get("question_started_at")
        and not question.answered_at
    )


def present_question(db: Session, question: StudyQuestion) -> QuestionOut:
    introducing = needs_introduction(question)
    public = {
        key: value
        for key, value in question.prompt.items()
        if key not in ("requires_introduction", "question_started_at")
    }
    if question.content_type == "vocabulary":
        item = db.get(VocabularyItem, question.content_id)
        if item is not None:
            # Resolve on presentation so already-issued questions benefit too.
            public["audio_url"] = preferred_audio_url(db, item)
    return QuestionOut(
        id=question.id,
        content_type=question.content_type,
        content_id=question.content_id,
        locale=question.locale,
        choices=[] if introducing else question.choices,
        expires_at=utc(question.expires_at),
        result=question.result,
        phase="introduction" if introducing else "question",
        introduction={
            "meaning": question.feedback["meaning"],
            "example": question.feedback.get("example"),
        }
        if introducing
        else None,
        **public,
    )


def begin_question(db: Session, user_id: str, question_id: str) -> QuestionOut:
    lock_user(db, user_id)
    question = db.scalar(
        select(StudyQuestion).where(
            StudyQuestion.id == question_id, StudyQuestion.user_id == user_id
        )
    )
    if not question:
        raise HTTPException(404, "Question not found")
    session = owned_session(db, user_id, question.session_id)
    now = now_utc()
    if session.ended_at or not question_in_scope(db, session, question) or (
        not question.answered_at and utc(question.expires_at) <= now
    ):
        raise HTTPException(409, "Question expired; resume the session")
    ensure_introduction(db, question)
    if needs_introduction(question):
        # Reading a card never changes learning history, counters or due dates.
        # Retries preserve this timestamp and the already persisted choice order.
        question.prompt = {**question.prompt, "question_started_at": now.isoformat()}
    db.commit()
    return present_question(db, question)


def in_scope(state: LearningState, session: StudySession) -> bool:
    scope = session.snapshot
    return state.content_type.value in scope["categories"] and (
        not scope["content_id"] or state.content_id == scope["content_id"]
    )


def active_acquisition(states, session):
    return [
        state
        for state in states
        if in_scope(state, session)
        and acquiring(state)
        and state.last_session_id == session.id
    ]


def prepare_acquisition(db: Session, session: StudySession, states) -> None:
    if session.ended_at:
        return
    for state in states:
        # Resume initial words from an already open session, without globally
        # changing due dates or restarting established/relearning cards.
        if (
            in_scope(state, session)
            and state.last_session_id == session.id
            and state.last_review_at
            and begins_acquisition(state)
        ):
            position = (
                db.scalar(
                    select(func.count())
                    .select_from(StudyQuestion)
                    .where(
                        StudyQuestion.session_id == session.id,
                        StudyQuestion.answered_at <= state.last_review_at,
                    )
                )
                or 0
            )
            state.acquisition = {
                "successes": initial_successes(state),
                "position": position,
            }
    reserve = sum(
        remaining_successes(state) for state in active_acquisition(states, session)
    )
    session.planned_items = max(
        session.planned_items, session.completed_items + reserve
    )


def present_turn(
    db: Session, session: StudySession, question=None, unavailable=0
) -> QuizTurnOut:
    # A closed session may have an old snapshot. Its summary must not advertise
    # reminders for levels that have since been suspended.
    scope = {**session.snapshot, **settings_levels(db.get(User, session.user_id).settings)}
    states = db.scalars(
        scoped_states_query(session.user_id, scope).where(
            LearningState.next_review_at.is_not(None),
        )
    ).all()
    categories = session.snapshot["categories"]
    future = [
        utc(s.next_review_at)
        for s in states
        if s.content_type.value in categories
        and utc(s.next_review_at) > now_utc()
        and (
            not session.snapshot.get("content_id")
            or s.content_id == session.snapshot["content_id"]
        )
    ]
    correct_count = (
        db.scalar(
            select(func.count())
            .select_from(StudyQuestion)
            .where(
                StudyQuestion.session_id == session.id,
                StudyQuestion.answered_at.is_not(None),
                StudyQuestion.selected_option_id == StudyQuestion.correct_option_id,
            )
        )
        or 0
    )
    coverage = (
        db.scalar(select(func.count(func.distinct(GrammarExercise.grammar_item_id))).where(
            GrammarExercise.grammar_item_id.in_(select(GrammarItem.id).where(
                GrammarItem.jlpt_level_code.in_(level_codes(scope, "grammar"))
            ))
        ))
        or 0
    )
    acquired = set()
    for answered in db.scalars(
        select(StudyQuestion).where(
            StudyQuestion.session_id == session.id,
            StudyQuestion.answered_at.is_not(None),
        )
    ):
        progress = (answered.result or {}).get("memory") or {}
        if progress.get("phase") == "acquisition" and progress.get("value") == 1:
            acquired.add((answered.content_type, answered.content_id))
    return QuizTurnOut(
        session_id=session.id,
        acquired_items=len(acquired),
        acquiring_items=len(active_acquisition(states, session)),
        completed_items=session.completed_items,
        planned_items=session.planned_items,
        correct_answers=correct_count,
        ended=session.ended_at is not None,
        question=present_question(db, question) if question else None,
        next_due_at=min(future) if future else None,
        grammar_points_available=coverage,
        unavailable_items=unavailable,
    )


def get_turn(db: Session, user_id: str, session_id: str) -> QuizTurnOut:
    lock_user(db, user_id)
    session = owned_session(db, user_id, session_id)
    if session.ended_at:
        return present_turn(db, session)
    if session.snapshot.get("retry_at"):
        # Sessions saved by the previous waiting flow resume directly.
        return next_question(db, user_id, session_id)
    question = latest_question(db, session_id)
    if question and not question_in_scope(db, session, question):
        return next_question(db, user_id, session_id)
    states = list(
        db.scalars(scoped_states_query(user_id, session.snapshot))
    )
    prepare_acquisition(db, session, states)
    if question:
        ensure_introduction(db, question)
        if question.result and (
            not question.result.get("memory")
            or (
                question.result["memory"].get("phase") == "acquisition"
                and question.result["memory"].get("required_successes")
                != REQUIRED_SUCCESSES
            )
        ):
            state = next(
                (
                    state
                    for state in states
                    if (state.content_type.value, state.content_id)
                    == (question.content_type, question.content_id)
                ),
                None,
            )
            if state:
                question.result = {
                    **question.result,
                    "memory": memory_progress(state),
                    "planned_items": session.planned_items,
                }
    db.commit()
    return present_turn(db, session, question)


def start_session(db: Session, user_id: str, payload: QuizStartIn) -> QuizTurnOut:
    user = lock_user(db, user_id)
    categories = [payload.category.value] if payload.category else list(MODELS)
    content_id = str(payload.content_id) if payload.content_id else None
    if content_id:
        content_id = resolve_content_id(db, categories[0], content_id)
    if content_id and not db.get(MODELS[categories[0]], content_id):
        raise HTTPException(404, "Content not found")
    settings = user.settings
    scope = {
        "scheduler": "fsrs6",
        "categories": categories,
        "content_id": content_id,
        "only_due": payload.only_due,
        "locale": settings.content_locale,
        **settings_levels(settings),
    }
    active = db.scalars(
        select(StudySession).where(
            StudySession.user_id == user_id, StudySession.ended_at.is_(None)
        )
    ).all()
    for existing in active:
        previous_scope = {**existing.snapshot, "min_levels": existing.snapshot.get("min_levels", existing.snapshot.get("levels"))}
        if all(previous_scope.get(key) == value for key, value in scope.items()):
            # A double click or network retry resumes the same question/feedback.
            result = get_turn(db, user_id, existing.id)
            db.commit()
            return result
        if existing.snapshot.get("scheduler") == "fsrs6":
            existing.ended_at = now_utc()
    planned = payload.planned_items
    if content_id:
        state = db.scalar(
            select(LearningState).where(
                LearningState.user_id == user_id,
                LearningState.content_type == payload.category,
                LearningState.content_id == content_id,
            )
        )
        planned = (
            (
                remaining_successes(state)
                if state and acquiring(state)
                else REQUIRED_SUCCESSES
            )
            if payload.category in MEANING_TYPES
            and (state is None or acquiring(state) or begins_acquisition(state))
            else 1
        )
    elif payload.category != ContentType.grammar:
        planned = max(3 * REQUIRED_SUCCESSES, planned)
    session = StudySession(
        user_id=user_id,
        mode=payload.category.value if payload.category else "mixed",
        planned_items=planned,
        completed_items=0,
        estimated_minutes=settings.daily_goal_minutes,
        started_at=now_utc(),
        snapshot=scope,
    )
    db.add(session)
    db.flush()
    return next_question(db, user_id, session.id)


def localized_meaning(item, kind: str, locale: str) -> dict | None:
    translation = next((t for t in item.translations if t.locale == locale), None)
    if locale != "en" and translation is None:
        return None  # Never mix translation languages inside a question.
    if kind == "vocabulary":
        label = translation.translation if translation else item.translation
        canonical = item.translation
        surface, pos = item.japanese, item.part_of_speech
    else:
        label = " ; ".join(translation.meanings if translation else item.meanings)
        canonical = " ; ".join(item.meanings)
        surface, pos = item.character, None
    if not label.strip():
        return None
    return {
        "id": item.id,
        "label": label,
        "canonical": canonical,
        "surface": surface,
        "locale": locale,
        "level": item.jlpt_level_code,
        "pos": pos,
    }


def item_example(item, locale: str):
    for example in getattr(item, "example_sentences", []):
        translation = next(
            (t for t in example.translations if t.locale == locale), None
        )
        if translation or locale == "en":
            return {
                "text": example.text,
                "translation": translation.translation
                if translation
                else example.translation,
                "reading": "",
            }
    return None


def build_question(
    db: Session, session: StudySession, kind: str, item, state, now: datetime
):
    locale = session.snapshot["locale"]
    if kind == "grammar":
        exercises = list(
            db.scalars(
                select(GrammarExercise).where(
                    GrammarExercise.grammar_item_id == item.id
                )
            )
        )
        exercises = [e for e in exercises if locale in e.translations]
        if not exercises:
            return None
        exercise = RNG.choice(exercises)
        translated = exercise.translations[locale]
        labels = [exercise.answer, *exercise.distractors]
        if (
            len(labels) != 4
            or len(set(labels)) != 4
            or exercise.prompt.count("___") != 1
        ):
            return None
        public = {
            "kind": "cloze",
            "title": exercise.prompt,
            "reading": "",
            "furigana_segments": [],
            "instruction": "Complétez la phrase."
            if locale == "fr"
            else "Complete the sentence.",
            "context": translated["context"],
            "jlpt_level_code": item.jlpt_level_code,
            "audio_url": None,
        }
        # Do not disclose the grammar title before answering: it is often the answer.
        meaning = next(
            (t.explanation for t in item.translations if t.locale == locale),
            item.explanation,
        )
        feedback = {
            "title": item.title,
            "reading": "",
            "meaning": meaning,
            "explanation": translated["explanation"],
            "example": {
                "text": exercise.completed_sentence,
                "translation": translated["translation"],
                "reading": "",
            },
        }
    else:
        target = localized_meaning(item, kind, locale)
        if not target:
            return None
        level = int(item.jlpt_level_code[1])
        levels = [f"N{n}" for n in range(max(1, level - 1), min(5, level + 1) + 1)]
        model = MODELS[kind]
        pool = db.scalars(
            select(model)
            .options(selectinload(model.translations))
            .where(model.jlpt_level_code.in_(levels))
        ).all()
        candidates = [
            m for candidate in pool if (m := localized_meaning(candidate, kind, locale))
        ]
        distractors = choose_distractors(target, candidates)
        if len(distractors) != 3:
            return None
        labels = [target["label"], *(d["label"] for d in distractors)]
        reading = (
            item.reading
            if kind == "vocabulary"
            else " / ".join([*item.onyomi, *item.kunyomi])
        )
        segments = (
            (item.furigana_segments or [{"surface": item.japanese, "reading": reading}])
            if kind == "vocabulary"
            else []
        )
        public = {
            "kind": "meaning",
            "title": target["surface"],
            "reading": reading,
            "furigana_segments": segments,
            "instruction": "Choisissez la bonne signification."
            if locale == "fr"
            else "Choose the correct meaning.",
            "context": "",
            "jlpt_level_code": item.jlpt_level_code,
            "audio_url": getattr(item, "audio_url", None),
        }
        feedback = {
            "title": target["surface"],
            "reading": reading,
            "meaning": target["label"],
            "explanation": "",
            "example": item_example(item, locale),
        }
    if kind == "vocabulary":
        public["requires_introduction"] = state is None or state.last_review_at is None
    options = [{"id": str(uuid4()), "label": label} for label in labels]
    correct_id = options[0]["id"]
    RNG.shuffle(options)
    question = StudyQuestion(
        user_id=session.user_id,
        session_id=session.id,
        content_type=kind,
        content_id=item.id,
        locale=locale,
        prompt=public,
        choices=options,
        correct_option_id=correct_id,
        feedback=feedback,
        baseline_revision=state.review_revision if state else 0,
        created_at=now,
        expires_at=now + timedelta(hours=24),
    )
    db.add(question)
    db.flush()
    return question


def next_question(db: Session, user_id: str, session_id: str) -> QuizTurnOut:
    lock_user(db, user_id)
    session = owned_session(db, user_id, session_id)
    if "retry_at" in session.snapshot:
        session.snapshot = {
            key: value for key, value in session.snapshot.items() if key != "retry_at"
        }
    now = now_utc()
    current = latest_question(db, session.id)
    if session.ended_at:
        return present_turn(db, session)
    states = list(
        db.scalars(scoped_states_query(user_id, session.snapshot))
    )
    prepare_acquisition(db, session, states)
    if current and not current.answered_at and utc(current.expires_at) > now and question_in_scope(db, session, current):
        ensure_introduction(db, current)
        db.commit()
        return present_turn(db, session, current)
    active = active_acquisition(states, session)
    reserve = sum(remaining_successes(state) for state in active)
    free_slots = session.planned_items - session.completed_items - reserve
    if session.completed_items >= session.planned_items and not active:
        session.ended_at = now
        db.commit()
        return present_turn(db, session)
    scope = session.snapshot
    by_item = {(state.content_type.value, state.content_id): state for state in states}
    active_ids = {state.id for state in active}
    due_candidates, repeats, deferred_repeats = [], [], []
    new_candidates = []
    for state in sorted(
        states,
        key=lambda state: (
            utc(state.next_review_at)
            if state.next_review_at
            else datetime.min.replace(tzinfo=timezone.utc)
        ),
    ):
        if not in_scope(state, session):
            continue
        if acquiring(state):
            cost = 0 if state.id in active_ids else remaining_successes(state)
            if cost > free_slots:
                continue
        else:
            if state.next_review_at and utc(state.next_review_at) > now:
                continue
            cost = (
                REQUIRED_SUCCESSES - initial_successes(state)
                if begins_acquisition(state)
                else 1
            )
            if cost > free_slots:
                continue
            if (
                current
                and current.answered_at
                and (state.content_type.value, state.content_id)
                == (current.content_type, current.content_id)
            ):
                continue
        candidate = (
            state.content_type.value,
            db.get(MODELS[state.content_type.value], state.content_id),
            state,
        )
        if state.last_review_at is None and not acquiring(state):
            # A placeholder state is still a first discovery, not a due review.
            kind, item, _ = candidate
            if not scope["only_due"] and item is not None:
                new_candidates.append(candidate)
            continue
        if acquiring(state) and not ready_for_recall(
            state, session.id, session.completed_items
        ):
            deferred_repeats.append(candidate)
        else:
            (repeats if state.id in active_ids else due_candidates).append(candidate)
    if not scope["only_due"] and free_slots > 0:
        categories = scope["categories"]
        offset = session.completed_items % len(categories)
        queues = []
        for kind in categories[offset:] + categories[:offset]:
            cost = REQUIRED_SUCCESSES if ContentType(kind) in MEANING_TYPES else 1
            if cost > free_slots:
                continue
            model = MODELS[kind]
            seen = [
                identifier for (category, identifier) in by_item if category == kind
            ]
            stmt = select(model).where(
                model.id.not_in(seen), model.jlpt_level_code.in_(level_codes(scope, kind))
            )
            if scope["content_id"]:
                stmt = stmt.where(model.id == scope["content_id"])
            if kind == "grammar":
                stmt = stmt.where(model.id.in_(select(GrammarExercise.grammar_item_id)))
            queues.append(
                [(kind, item, None) for item in db.scalars(stmt.order_by(model.source_order.asc().nulls_last(), model.jlpt_level_code.desc(), model.id))]
            )
        for index in range(max((len(queue) for queue in queues), default=0)):
            new_candidates.extend(
                queue[index] for queue in queues if index < len(queue)
            )
    # Stable sorting retains category rotation within each level, while lower
    # difficulty comes first across all discovery queues. Due reviews stay first.
    new_candidates.sort(key=lambda candidate: -int(candidate[1].jlpt_level_code[1]))
    # Fill a small cohort while reserving enough questions for every introduced
    # item, then recall them with intervening questions. Never open an endless
    # stream of new words which cannot finish acquisition in this session.
    # When nothing else can be asked, repeat the least recently practiced item
    # immediately instead of interrupting the session with a timer.
    deferred_repeats.sort(
        key=lambda candidate: (
            utc(candidate[2].last_review_at)
            if candidate[2].last_review_at
            else datetime.min.replace(tzinfo=timezone.utc),
            candidate[2].acquisition["position"]
            if candidate[2].last_session_id == session.id
            else 0,
        )
    )
    unavailable = 0
    for kind, item, state in (
        due_candidates + repeats + new_candidates + deferred_repeats
    ):
        if item is None:
            continue
        issued_at = (
            max(now, utc(current.created_at) + timedelta(microseconds=1))
            if current
            else now
        )
        question = build_question(db, session, kind, item, state, issued_at)
        if question:
            db.commit()
            return present_turn(db, session, question, unavailable)
        unavailable += 1
    session.ended_at = now
    db.commit()
    return present_turn(db, session, unavailable=unavailable)


def answer_question(
    db: Session, user_id: str, question_id: str, option_id: str
) -> AnswerOut:
    lock_user(db, user_id)
    question = db.scalar(
        select(StudyQuestion).where(
            StudyQuestion.id == question_id, StudyQuestion.user_id == user_id
        )
    )
    if not question:
        raise HTTPException(404, "Question not found")
    if question.answered_at:
        if option_id != question.selected_option_id:
            raise HTTPException(409, "This question has already been answered")
        return AnswerOut.model_validate(question.result)
    session = owned_session(db, user_id, question.session_id)
    now = now_utc()
    if session.ended_at or utc(question.expires_at) <= now or not question_in_scope(db, session, question):
        raise HTTPException(409, "Question expired; resume the session")
    ensure_introduction(db, question)
    if needs_introduction(question):
        db.commit()
        raise HTTPException(409, "Read the introduction and begin the question first")
    if option_id not in {choice["id"] for choice in question.choices}:
        raise HTTPException(422, "Choose an option belonging to this question")
    kind = ContentType(question.content_type)
    state = db.scalar(
        select(LearningState).where(
            LearningState.user_id == user_id,
            LearningState.content_type == kind,
            LearningState.content_id == question.content_id,
        )
    )
    if (state.review_revision if state else 0) != question.baseline_revision:
        raise HTTPException(
            409, "This item has already been reviewed in another question"
        )
    if not state:
        state = LearningState(
            user_id=user_id, content_type=kind, content_id=question.content_id
        )
        db.add(state)
        db.flush()
    correct = option_id == question.correct_option_id
    started_at = question.prompt.get("question_started_at")
    response_started = (
        utc(datetime.fromisoformat(started_at))
        if started_at
        else utc(question.created_at)
    )
    duration = max(0, int((now - response_started).total_seconds() * 1000))
    memory = record_answer(state, correct, now, duration, session.completed_items + 1)
    state.last_session_id = session.id
    session.completed_items += 1
    states = list(
        db.scalars(scoped_states_query(user_id, session.snapshot))
    )
    reserve = sum(
        remaining_successes(item) for item in active_acquisition(states, session)
    )
    session.planned_items = max(
        session.planned_items, session.completed_items + reserve
    )
    result = AnswerOut(
        question_id=question.id,
        memory=memory["progress"],
        planned_items=session.planned_items,
        selected_option_id=option_id,
        correct_option_id=question.correct_option_id,
        correct=correct,
        **question.feedback,
        status=state.status,
        next_review_at=state.next_review_at,
        difficulty=memory["difficulty"],
        stability=memory["stability"],
        retrievability=memory["retrievability"],
    )
    question.selected_option_id, question.answered_at = option_id, now
    question.result = result.model_dump(mode="json")
    db.add(
        ReviewHistory(
            user_id=user_id,
            content_type=kind,
            content_id=question.content_id,
            rating=memory["rating"],
            correct=correct,
            response_time_ms=duration,
            session_id=session.id,
            review_window="short" if state.interval_days < 1 else "long",
            payload={
                "scheduler": memory["scheduler"],
                "question_id": question.id,
                "option_id": option_id,
                "choices": question.choices,
                "locale": question.locale,
                **memory,
            },
        )
    )
    db.commit()
    return result
