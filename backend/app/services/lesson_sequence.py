"""Small discovery/practice blocks, with stable resume order for each learner."""
from fastapi import HTTPException

from app.models.lesson import Lesson, LessonProgress


def gradual_steps(steps: list[dict]) -> list[dict]:
    words = [step for step in steps if step["kind"] == "word"]
    by_id = {step["id"]: step for step in steps}
    if not words or not any(f"recognise-{word.get('source_id')}" in by_id for word in words):
        return steps
    result = []
    added = set()

    def add(step):
        if step is not None and step["id"] not in added:
            result.append(step)
            added.add(step["id"])

    def grammar_pair(step):
        add(step)
        add(by_id.get(step["id"].replace("grammar-", "apply-", 1)))

    for step in steps:
        if step["kind"] == "read" and step["id"] != "reflect":
            add(step)
    word_ids = {word["source_id"] for word in words}
    for step in steps:
        # Pending checks of already-seen words come before further discoveries on resume.
        if step["id"].startswith("recognise-") and step.get("source_id") not in word_ids:
            add(step)
    grammars = [step for step in steps if step["kind"] == "grammar"]
    kanji = [step for step in steps if step["kind"] == "kanji"]
    previous_block = []
    for start in range(0, len(words), 2):
        block = words[start:start + 2]
        for word in block:
            add(word)
        for word in block:
            add(by_id.get(f"recognise-{word['source_id']}"))
        if grammars:
            grammar_pair(grammars.pop(0))
        if kanji:
            add(kanji.pop(0))
        # Delay production until another block has intervened, rather than echoing a word.
        for word in previous_block:
            add(by_id.get(f"recall-{word['source_id']}"))
        previous_block = block
    for step in grammars:
        grammar_pair(step)
    for step in kanji:
        add(step)
    for step in steps:
        if step["kind"] == "recall":
            add(step)
    for step in steps:
        if step["kind"] == "dialogue":
            add(step)
    for step in steps:
        if step["id"] != "reflect":
            add(step)
    add(by_id.get("reflect"))
    return result


def ordered_steps(lesson: Lesson, progress: LessonProgress | None) -> list[dict]:
    steps = lesson.content["steps"]
    if progress and progress.step_order is not None:
        by_id = {step["id"]: step for step in steps}
        if len(progress.step_order) != len(steps) or set(progress.step_order) != set(by_id):
            raise HTTPException(409, "Lesson step order is incompatible; contact support")
        return [by_id[identity] for identity in progress.step_order]
    # Old cursors refer to the original sequence. Keep their completed prefix and
    # current step (including an already-submitted answer) before adapting the rest.
    keep = min(len(steps), progress.cursor + 1) if progress and (progress.revision or progress.cursor) else 0
    return steps[:keep] + gradual_steps(steps[keep:])
