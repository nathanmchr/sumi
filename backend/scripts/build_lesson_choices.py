"""Build a deterministic, additive presentation supplement. Does not write to the DB."""

import argparse
import csv
import json

from import_n5_lessons import CATALOG, DATA, compile_course, digest, distractors_for
from app.services.lesson_choices import choice_signature


def build_supplements() -> dict:
    lessons, _ = compile_course()
    tables = {}
    for category in ("vocabulary", "grammar"):
        with (CATALOG / f"{category}.csv").open(encoding="utf-8-sig", newline="") as handle:
            tables[category] = [row for row in csv.DictReader(handle, delimiter=";") if row["Level"] == "N5"]
    vocabulary, grammar = tables["vocabulary"], tables["grammar"]
    words = {row["ID"]: row for row in vocabulary}
    fourth = json.loads((DATA / "n5_grammar_fourth_choices.json").read_text())
    grammar_labels = {row["ID"]: fourth[str(index)] for index, row in enumerate(grammar)}
    result = {}
    for lesson in lessons:
        for step in lesson["content"]["steps"]:
            if step["kind"] != "choice":
                continue
            if step["id"].startswith("recognise-"):
                label = distractors_for(words[step["source_id"]], vocabulary, count=3)[-1]
            else:
                value = grammar_labels[step["id"].removeprefix("apply-")]
                label = {"fr": value, "en": value}
            for locale in ("fr", "en"):
                assert label[locale].casefold() not in {o["label"][locale].casefold() for o in step["options"]}, step["id"]
            extra = {"id": digest([step["id"], label])[:16], "label": label}
            assert extra["id"] not in {o["id"] for o in step["options"]}
            result[choice_signature(step)] = extra
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = build_supplements()
    target = DATA / "n5_choice_supplements.json"
    if args.write:
        target.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    else:
        assert json.loads(target.read_text()) == result, "Rebuild the lesson choice supplement"
    print(f"Validated {len(result)} additive fourth choices")
