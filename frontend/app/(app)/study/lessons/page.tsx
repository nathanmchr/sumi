"use client";

import Link from "next/link";
import useSWR from "swr";
import { session } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { getLessons, lessonCopy, type LessonSummary } from "@/lib/lessons";
import styles from "./lessons.module.css";

export default function LessonsPage() {
  const { locale } = useI18n();
  const copy = lessonCopy[locale];
  const { data: auth } = useSWR("session", session);
  const contentLocale = auth?.settings.content_locale ?? locale;
  const { data, error, mutate } = useSWR(auth ? ["lessons", contentLocale] : null, () => getLessons(contentLocale));
  const units = new Map<string, LessonSummary[]>();
  for (const lesson of data ?? []) units.set(lesson.unit_id, [...(units.get(lesson.unit_id) ?? []), lesson]);
  const completed = data?.filter((item) => item.completed).length ?? 0;
  const recommended = data?.find((item) => item.recommended);
  return <div className={styles.course}>
    <header className={styles.courseHeader}>
      <span className={styles.level}>N5</span>
      <h1>{copy.title}</h1><p>{copy.intro}</p>
      {data?.length ? <div className={styles.courseProgress}>
        <span>{completed} / {data.length} {copy.lessons} {copy.completed}</span>
        <progress aria-label={copy.course} value={completed} max={data.length} />
      </div> : null}
    </header>
    {error ? <p role="alert">{copy.error} <button className="button button--small" onClick={() => void mutate()}>{copy.retry}</button></p>
      : !data ? <p role="status">{copy.loading}</p>
      : !data.length ? <p>{copy.empty}</p> : <>
        {recommended ? <section className={styles.recommended}>
          <div><span className={styles.quietLabel}>{copy.recommended}</span><h2>{recommended.title}</h2><p>{recommended.goal}</p></div>
          <Link className="button button--accent" href={`/study/lessons/${recommended.id}`}>{recommended.completed_steps ? copy.resume : copy.start}<span aria-hidden="true"> →</span></Link>
        </section> : null}
        <p className={styles.note}>{copy.prerequisites}</p>
        <div className={styles.units}>{[...units.values()].map((lessons, index) => {
          const totals = lessons.filter(lesson => !lesson.is_recap).reduce((sum, lesson) => ({
            vocabulary: sum.vocabulary + lesson.vocabulary_count,
            grammar: sum.grammar + lesson.grammar_count,
            kanji: sum.kanji + lesson.kanji_count,
          }), { vocabulary: 0, grammar: 0, kanji: 0 });
          return <section key={lessons[0].unit_id} className={styles.unit}>
          <header className="unit-heading"><span className="unit-number">{String(index + 1).padStart(2, "0")}</span>
            <div><h2>{lessons[0].unit_title}</h2>
              <p>{lessons[0].goal}</p></div>
            <span className="unit-count">{lessons.filter((l) => l.completed).length}/{lessons.length}</span>
            <p className="unit-stats">{totals.vocabulary} {copy.words} · {totals.grammar} {totals.grammar === 1 ? copy.grammarPoint : copy.grammarPoints} · {totals.kanji} {copy.kanji}</p>
          </header>
          <ol className={styles.lessonList}>{lessons.map((lesson, part) => {
            const content = <>
              <span className={styles.lessonNumber} data-complete={lesson.completed}>{lesson.completed ? "✓" : part + 1}</span>
              <div className={styles.rowBody}><strong>{lesson.title}</strong><span>{lesson.is_recap
                ? lesson.locked ? copy.recapLocked : copy.themeRecapDescription
                : <>{lesson.vocabulary_count} {copy.words} · {lesson.grammar_count} {copy.grammar} · {lesson.kanji_count} {copy.kanji}</>}</span></div>
              {!lesson.locked ? <span className={styles.rowTime}>{lesson.minutes} {copy.minutes}</span> : null}
              {!lesson.locked ? <span className={styles.rowAction}>{lesson.completed ? copy.review : lesson.completed_steps ? copy.resume : copy.start}<span aria-hidden="true"> →</span></span> : null}
            </>;
            return <li key={lesson.id}>{lesson.locked
              ? <div className={styles.lessonRow} data-recap={lesson.is_recap} aria-disabled="true">{content}</div>
              : <Link href={`/study/lessons/${lesson.id}`} className={styles.lessonRow} data-recap={lesson.is_recap}>{content}</Link>}
            </li>;
          })}</ol>
        </section>;
        })}</div>
      </>}
    <style jsx>{`
      .unit-heading { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 12px 18px; padding: 25px 28px; }
      .unit-heading h2 { font-size: 1.25rem; letter-spacing: -.025em; margin: 0 0 6px; }
      .unit-heading p { margin: 0; color: var(--muted); font-size: .9rem; line-height: 1.5; }
      .unit-number { color: var(--focus); font-size: 1.45rem; font-weight: 650; font-variant-numeric: tabular-nums; }
      .unit-count { color: var(--muted); font-size: .8rem; white-space: nowrap; }
      .unit-heading .unit-stats { grid-column: 1 / -1; font-size: .8rem; }
      @media (max-width: 640px) { .unit-heading { padding: 20px 16px; gap: 12px; } }
    `}</style>
  </div>;
}
