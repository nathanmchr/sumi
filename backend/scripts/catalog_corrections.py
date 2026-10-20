"""Apply explicitly reviewed edits to the original consolidation, never fuzzy merges."""

from __future__ import annotations

import csv
import hashlib
import io
import json


def rows_from(text):
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def csv_text(rows, headers):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def apply_reviewed_corrections(files, recipe):
    """Return corrected files, summary and reversible ledger; leave inputs untouched.

    Always replay from the unchanged source consolidation. Fingerprints and field
    preconditions stop a stale recipe instead of matching a new word by its spelling.
    """
    result = dict(files)
    for name, expected in recipe["baseline_sha256"].items():
        actual = hashlib.sha256(files[name].encode("utf-8")).hexdigest()
        if actual != expected:
            raise ValueError(f"Reviewed baseline changed: {name}")
    tables = {category: rows_from(files[f"{category}.csv"])
              for category in ("vocabulary", "grammar", "kanji")}
    by_id = {category: {row["ID"]: row for row in rows} for category, rows in tables.items()}
    originals = {category: {key: dict(row) for key, row in indexed.items()}
                 for category, indexed in by_id.items()}
    positions = {category: {row["ID"]: i for i, row in enumerate(rows)}
                 for category, rows in tables.items()}
    redirects = {}
    ledger = {"version": recipe["version"], "updates": [], "merges": [],
              "pending_audio": recipe.get("pending_audio", []),
              "audio_review": recipe.get("audio_review", []),
              "unresolved": recipe.get("unresolved", [])}

    def edit(row, changes):
        if changes.get("ID", row["ID"]) != row["ID"]:
            raise ValueError("A correction cannot replace a stable ID")
        if changes.get("Level", row["Level"]) != row["Level"]:
            raise ValueError("A correction cannot move the first introduction level")
        if any(key not in row or not isinstance(value, str) for key, value in changes.items()):
            raise ValueError("Invalid correction fields")
        row.update(changes)

    seen_updates = set()
    for operation in recipe["updates"]:
        category, identity = operation["category"], operation["id"]
        if (category, identity) in seen_updates:
            raise ValueError(f"Repeated update: {identity}")
        seen_updates.add((category, identity))
        row = by_id[category][identity]
        for field, expected in operation["expect"].items():
            if row[field] != expected:
                raise ValueError(f"Correction precondition failed: {identity}/{field}")
        before = dict(row)
        edit(row, operation["set"])
        ledger["updates"].append({**operation, "before": before, "after": dict(row)})

    merged_ids = set()
    for operation in recipe["merges"]:
        category, keep = operation["category"], operation["keep"]
        members = [keep, *operation["absorb"]]
        if len(members) < 2 or len(set(members)) != len(members):
            raise ValueError("A merge needs distinct, explicit member IDs")
        if any((category, identity) in merged_ids for identity in members):
            raise ValueError("Overlapping reviewed merges are not allowed")
        if keep != min(members, key=positions[category].__getitem__):
            raise ValueError("A merge must keep the first occurrence")
        merged_ids.update((category, identity) for identity in members)
        row = by_id[category][keep]
        before = [dict(by_id[category][identity]) for identity in members]
        edit(row, operation.get("set", {}))
        for identity in operation["absorb"]:
            redirects[(category, identity)] = keep
        ledger["merges"].append({**operation, "before": before, "after": dict(row)})

    for category, rows in tables.items():
        tables[category] = [row for row in rows if (category, row["ID"]) not in redirects]
        for row in tables[category]:
            if row["Level"] != originals[category][row["ID"]]["Level"]:
                raise ValueError("Introduction level changed")
        headers = next(csv.reader(io.StringIO(files[f"{category}.csv"]), delimiter=";"))
        result[f"{category}.csv"] = csv_text(tables[category], headers)

    provenance = rows_from(files["_audit/source-map.csv"])
    final_positions = {category: {row["ID"]: i for i, row in enumerate(rows, 1)}
                       for category, rows in tables.items()}
    for source in provenance:
        category, previous = source["Category"], source["CanonicalID"]
        source["OriginalCanonicalID"] = previous
        source["CanonicalID"] = redirects.get((category, previous), previous)
        source["CanonicalOrder"] = str(final_positions[category][source["CanonicalID"]])
    result["_audit/source-map.csv"] = csv_text(provenance, list(provenance[0]))
    merges, summary = [], {}
    for category, rows in tables.items():
        refs = [source for source in provenance if source["Category"] == category]
        grouped = {}
        for source in refs:
            grouped.setdefault(source["CanonicalID"], []).append(source)
        if list(grouped) != [row["ID"] for row in rows]:
            raise ValueError("First-occurrence order changed")
        for position, row in enumerate(rows, 1):
            sources = grouped[row["ID"]]
            if len(sources) > 1:
                merges.append({"Category": category, "ID": row["ID"], "Position": position,
                               "Word": row["Kanji"] or row.get("Kana", ""), "Level": row["Level"],
                               "KanjiLevel": row.get("KanjiLevel", ""),
                               "Sources": " | ".join(f"{s['SourceFile']}:{s['SourceRow']}" for s in sources)})
        summary[category] = {"source_rows": len(refs), "rows": len(rows),
                             "absorbed_rows": len(refs) - len(rows),
                             "merge_groups": sum(len(group) > 1 for group in grouped.values())}
    result["_audit/merges.csv"] = csv_text(merges, ["Category", "ID", "Position", "Word", "Level", "KanjiLevel", "Sources"])
    ledger["redirects"] = [{"category": category, "from": previous, "to": current}
                           for (category, previous), current in redirects.items()]
    ledger["baseline_sha256"] = recipe["baseline_sha256"]
    ledger["result_sha256"] = {f"{category}.csv": hashlib.sha256(result[f"{category}.csv"].encode()).hexdigest()
                                for category in tables}
    result["_audit/corrections.json"] = json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"
    return result, summary, ledger
