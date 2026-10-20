"""Publish one final assessment per theme without changing taught content or answers."""
from datetime import datetime, timezone
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, load_only

from app.models.lesson import Lesson, LessonProgress


def is_theme_recap(lesson: Lesson) -> bool:
    return lesson.content.get("kind") == "theme_recap"


def require_completed_theme(db: Session, lesson: Lesson, user_id: str) -> None:
    if not is_theme_recap(lesson):
        return
    required = set(lesson.content["prerequisite_ids"])
    completed = set(db.scalars(select(Lesson.id).join(LessonProgress).where(
        Lesson.id.in_(required), LessonProgress.user_id == user_id,
        LessonProgress.version == Lesson.version, LessonProgress.completed_at.is_not(None))))
    if completed != required:
        raise HTTPException(403, "Complete all lessons in this theme before taking its cumulative test")


def publish_theme_recaps(db: Session) -> dict[str, int]:
    # Same lock order as lesson commands: content first, progress second.
    lessons = list(db.scalars(select(Lesson).order_by(Lesson.position).with_for_update()))
    if any(lesson.position <= 0 for lesson in lessons):
        raise ValueError("Lesson positions must be positive before publishing theme recaps")
    by_id = {lesson.id: lesson for lesson in lessons}
    groups = {}
    for lesson in lessons:
        if not is_theme_recap(lesson):
            groups.setdefault((lesson.level, lesson.content["unit_id"]), []).append(lesson)
    report = dict(created=0, reordered=0, normalized_progress=0)
    ordered = []
    cumulative = {key: set() for key in ("vocabulary_ids", "grammar_ids", "kanji_ids")}
    for (level, unit), parts in groups.items():
        for part in parts:
            for key in cumulative:
                cumulative[key].update(part.content[key])
        first = parts[0].content
        identity = f"{level.lower()}-{unit}-recap"
        if len(identity) > 100:
            raise ValueError("Theme recap ID exceeds the lesson ID limit")
        content = dict(kind="theme_recap", unit_id=unit, unit_title=first["unit_title"],
            title={"fr": "Bilan cumulatif", "en": "Cumulative test"},
            goal={"fr": "Reprendre tous les acquis de ce thème et des thèmes précédents terminés.",
                  "en": "Revisit everything learned in this theme and earlier completed themes."},
            minutes=max(1, sum(map(len, cumulative.values())) // 2), steps=[],
            vocabulary_ids=[], grammar_ids=[], kanji_ids=[], prerequisite_ids=[p.id for p in parts])
        version = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        recap = by_id.get(identity)
        if recap:
            if not is_theme_recap(recap):
                raise ValueError(f"Recap ID conflicts with an existing lesson: {identity}")
            if recap.version != version:
                if db.scalar(select(LessonProgress.user_id).where(LessonProgress.lesson_id == identity).limit(1)):
                    raise ValueError(f"Cannot rewrite a theme recap with saved progress: {identity}")
                recap.content, recap.version = content, version
        else:
            recap = Lesson(id=identity, level=level, position=max((l.position for l in lessons), default=0) + report["created"] + 1,
                           content=content, version=version)
            db.add(recap)
            report["created"] += 1
        ordered.extend([*parts, recap])
    if any(is_theme_recap(l) and l.id not in {item.id for item in ordered} for l in lessons):
        raise ValueError("A published recap has no corresponding theme; refusing to discard it")
    db.flush()
    if any(item.position != position for position, item in enumerate(ordered, 1)):
        # Two passes avoid transient collisions on the unique integer position column.
        db.execute(update(Lesson).values(position=-Lesson.position).execution_options(synchronize_session=False))
        for position, item in enumerate(ordered, 1):
            db.execute(update(Lesson).where(Lesson.id == item.id).values(position=position))
        report["reordered"] = len(ordered)
    bases = {part.id: len(part.content["steps"]) for parts in groups.values() for part in parts}
    for progress, archived_count in db.execute(select(LessonProgress,
        func.coalesce(func.json_array_length(LessonProgress.recap_steps), 0)
    ).options(load_only(LessonProgress.cursor, LessonProgress.completed_at, LessonProgress.revision,
                        LessonProgress.last_command)).where(LessonProgress.lesson_id.in_(bases)).with_for_update()):
        total = bases[progress.lesson_id]
        if progress.cursor > total + archived_count:
            raise ValueError("Progress cursor is outside its saved lesson; refusing to reinterpret it")
        if progress.cursor > total or (progress.cursor == total and not progress.completed_at):
            progress.cursor = total
            progress.completed_at = progress.completed_at or datetime.now(timezone.utc)
            progress.revision += 1
            progress.last_command = None
            # Original inline questions and answers remain stored as historical records.
            report["normalized_progress"] += 1
    db.flush()
    return report
