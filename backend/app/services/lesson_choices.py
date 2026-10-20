"""Add reviewed distractors without rewriting versioned lesson progress."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path


def choice_signature(step: dict) -> str:
    payload = [step["id"], step.get("japanese"), step["options"], step["correct_option"]]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


@lru_cache(maxsize=1)
def supplements() -> dict:
    return json.loads((Path(__file__).resolve().parents[1] / "data/n5_choice_supplements.json").read_text())


def lesson_options(step: dict) -> list[dict]:
    options = step["options"]
    if len(options) != 3:
        return options
    extra = supplements().get(choice_signature(step))
    if extra is None:
        return options
    # Keep all existing IDs, including the selected/correct IDs in old histories.
    result = [*options, extra]
    return sorted(result, key=lambda option: hashlib.sha256(
        f"{step['id']}:{option['id']}".encode()).hexdigest())
