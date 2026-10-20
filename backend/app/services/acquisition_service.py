"""Initial recall practice is separate from the long-term FSRS review history."""

from datetime import datetime
from fsrs import State
from app.models.learning import LearningState
from app.services.fsrs_service import schedule_answer
from app.utils.enums import ContentType, ReviewStatus

REQUIRED_SUCCESSES = 5
INTERVENING_ANSWERS = 2
MEANING_TYPES = (ContentType.vocabulary, ContentType.kanji)


def acquiring(state: LearningState) -> bool:
    return bool(
        state.acquisition is not None
        and state.acquisition["successes"] < REQUIRED_SUCCESSES
    )


def begins_acquisition(state: LearningState) -> bool:
    if state.content_type not in MEANING_TYPES or state.acquisition is not None:
        return False
    # A previously established/relearning item is never restarted as a new item.
    return state.last_review_at is None or bool(
        state.fsrs_card and state.fsrs_card["state"] == int(State.Learning)
    )


def initial_successes(state: LearningState) -> int:
    return min(REQUIRED_SUCCESSES - 1, state.consecutive_correct or 0)


def remaining_successes(state: LearningState) -> int:
    return (
        REQUIRED_SUCCESSES - state.acquisition["successes"] if acquiring(state) else 0
    )


def ready_for_recall(state: LearningState, session_id: str, completed: int) -> bool:
    """Prefer two intervening answers; this never blocks an otherwise empty queue."""
    position = (
        state.acquisition["position"] if state.last_session_id == session_id else 0
    )
    return completed - position >= INTERVENING_ANSWERS


def memory_progress(state: LearningState, initial=False) -> dict:
    if state.acquisition is not None and (initial or acquiring(state)):
        successes = state.acquisition["successes"]
        return {
            "phase": "acquisition",
            "value": successes / REQUIRED_SUCCESSES,
            "successes": successes,
            "required_successes": REQUIRED_SUCCESSES,
        }
    # Stability, not post-answer retrievability (which would misleadingly be 100%).
    stability = (state.fsrs_card or {}).get("stability") or 0
    return {"phase": "consolidation", "value": min(1.0, stability / 90)}


def record_answer(
    state: LearningState, correct: bool, now: datetime, duration: int, position: int
) -> dict:
    if begins_acquisition(state):
        state.acquisition = {
            "successes": initial_successes(state),
            "position": position - 1,
        }
    if not acquiring(state):
        result = schedule_answer(state, correct, now, duration)
        return {**result, "scheduler": "fsrs6", "progress": memory_progress(state)}

    before = dict(state.acquisition)
    successes = before["successes"] + 1 if correct else 0
    state.acquisition = {"successes": successes, "position": position}
    if successes == REQUIRED_SUCCESSES:
        # Do not feed the rapid recognition attempts into FSRS as successive
        # successful long-term recalls. Start one real FSRS card at graduation.
        state.fsrs_card = None
        state.status = ReviewStatus.learning
        result = schedule_answer(state, True, now, duration)
        scheduler = "fsrs6"
    else:
        state.fsrs_card = None
        state.scheduler_version = "acquisition"
        state.status = ReviewStatus.learning
        state.last_review_at = now
        state.next_review_at = now  # pending initial practice, not a future FSRS review
        state.interval_days = 0
        state.review_revision = (state.review_revision or 0) + 1
        state.consecutive_correct = (
            (state.consecutive_correct or 0) + 1 if correct else 0
        )
        state.repetition_count = (state.repetition_count or 0) + 1 if correct else 0
        state.lapses_count = (state.lapses_count or 0) + (not correct)
        state.recent_results = [*(state.recent_results or []), correct][-5:]
        state.mastery = 0
        result = {
            "rating": 3 if correct else 1,
            "difficulty": None,
            "stability": None,
            "retrievability": None,
        }
        scheduler = "acquisition"
    return {
        **result,
        "scheduler": scheduler,
        "progress": memory_progress(state, initial=True),
        "acquisition_before": before,
        "acquisition_after": dict(state.acquisition),
    }
