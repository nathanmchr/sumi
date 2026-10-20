"""FSRS-6 scheduling. Existing dates are untouched until a verified answer."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256

from fsrs import Card, Rating, Scheduler, State

from app.models.learning import LearningState
from app.utils.enums import ReviewStatus

SCHEDULER = Scheduler(
    desired_retention=0.9,
    learning_steps=(timedelta(minutes=10), timedelta(hours=4)),
    relearning_steps=(timedelta(minutes=10),),
    enable_fuzzing=False,
)


def utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def memory_card(state: LearningState, now: datetime) -> Card:
    if state.fsrs_card:
        return Card.from_dict(state.fsrs_card)
    card_id = int.from_bytes(sha256(state.id.encode()).digest()[:8], "big")
    # Legacy intervals provide an initial estimate, not a fabricated review history.
    # Bootstrap only when answering; never write this estimate during reads/migration.
    if state.last_review_at and state.status in (
        ReviewStatus.known,
        ReviewStatus.master,
        ReviewStatus.review,
        ReviewStatus.fragile,
    ):
        return Card(
            card_id=card_id,
            state=State.Review,
            stability=max(1.0, float(state.interval_days or 1)),
            difficulty=5.0,
            last_review=utc(state.last_review_at),
            due=utc(state.next_review_at) if state.next_review_at else now,
        )
    return Card(card_id=card_id, due=now)


def memory_status(state: LearningState, now: datetime) -> ReviewStatus:
    if not state.fsrs_card:
        return state.status
    card = Card.from_dict(state.fsrs_card)
    if card.state == State.Learning:
        return ReviewStatus.learning
    if card.state == State.Relearning:
        return ReviewStatus.relearning
    results = state.recent_results or []
    probability = SCHEDULER.get_card_retrievability(card, current_datetime=utc(now))
    if results.count(False) >= 2 or probability < 0.8:
        return ReviewStatus.fragile
    streak = state.consecutive_correct or 0
    if (card.stability or 0) >= 90 and streak >= 5 and False not in results:
        return ReviewStatus.master
    if (card.stability or 0) >= 7 and streak >= 3:
        return ReviewStatus.known
    return ReviewStatus.review


def schedule_answer(
    state: LearningState, correct: bool, now: datetime, duration_ms: int
) -> dict:
    now = utc(now)
    card = memory_card(state, now)
    before = card.to_dict()
    rating = Rating.Good if correct else Rating.Again
    card, log = SCHEDULER.review_card(
        card, rating, review_datetime=now, review_duration=duration_ms
    )
    state.fsrs_card = card.to_dict()
    state.scheduler_version = "fsrs6"
    state.consecutive_correct = (state.consecutive_correct or 0) + 1 if correct else 0
    state.recent_results = [*(state.recent_results or []), correct][-5:]
    state.repetition_count = (state.repetition_count or 0) + 1 if correct else 0
    state.lapses_count = (state.lapses_count or 0) + (not correct)
    state.review_revision = (state.review_revision or 0) + 1
    state.last_review_at = now
    state.next_review_at = card.due
    state.interval_days = max(0, (card.due - now).days)
    state.status = memory_status(state, now)
    # A display indicator, separate from FSRS's actual probability of recall.
    state.mastery = min(1.0, (card.stability or 0) / 90) * min(
        1.0, state.consecutive_correct / 5
    )
    return {
        "before": before,
        "after": card.to_dict(),
        "review_log": log.to_dict(),
        "rating": int(rating),
        "difficulty": card.difficulty,
        "stability": card.stability,
        "retrievability": SCHEDULER.get_card_retrievability(card, current_datetime=now),
    }
