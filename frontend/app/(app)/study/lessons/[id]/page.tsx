"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import useSWR from "swr";
import { ApiError, session } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { advanceLesson, getLesson, lessonCopy, type LessonCommand, type LessonState } from "@/lib/lessons";
import { FuriganaText } from "@/components/furigana-text";
import { AudioButton } from "@/components/audio-button";
import { ClozeText } from "@/components/cloze-text";
import { useStudyAudio } from "@/components/study-audio";
import { LessonProgressHeader } from "@/components/lesson-progress-header";
import { CompletionConfetti } from "@/components/completion-confetti";
import type { FuriganaSegment, UserSettings } from "@/lib/types";
import styles from "../lessons.module.css";

const KanjiStrokePlayer = dynamic(() => import("@/components/kanji-stroke-player").then((module) => module.KanjiStrokePlayer));

function LessonJapanese({ japanese, segments, romaji, settings }: {
  japanese: string; segments?: FuriganaSegment[]; romaji?: string; settings?: UserSettings;
}) {
  return <span className={styles.readingText}>
    <span lang="ja">{segments?.length
      ? <FuriganaText segments={segments} mode={settings?.furigana_display_mode ?? "always"} helper={settings?.furigana_helper_enabled ?? false} />
      : japanese}</span>
    {settings?.romaji_enabled && romaji ? <span className={styles.romaji} lang="ja-Latn">{romaji}</span> : null}
  </span>;
}

export default function LessonPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { locale } = useI18n();
  const copy = lessonCopy[locale];
  const { data: auth } = useSWR("session", session);
  const audio = useStudyAudio(auth?.user.id);
  const contentLocale = auth?.settings.content_locale ?? locale;
  const [viewing, setViewing] = useState<number>();
  const { data, error, mutate } = useSWR(auth ? ["lesson", id, contentLocale, viewing] : null,
    () => getLesson(id, contentLocale, viewing), { revalidateOnFocus: false, shouldRetryOnError: false });
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [saveError, setSaveError] = useState("");
  const [celebrate, setCelebrate] = useState(false);
  useEffect(() => { setCelebrate(false); }, [id]);

  async function submit(command: LessonCommand) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true); setSaveError("");
    try {
      const result = await advanceLesson(id, contentLocale, command);
      await mutate(result, { revalidate: false });
      if (data && !data.lesson.completed && result.lesson.completed && result.lesson.completed_steps > 0) {
        setCelebrate(true);
      }
    } catch (failure) {
      setSaveError(failure instanceof ApiError && failure.status === 409 ? copy.conflict : copy.saveError);
    } finally { submitting.current = false; setBusy(false); }
  }
  async function reload() {
    setSaveError("");
    try { await mutate(); } catch { setSaveError(copy.saveError); }
  }
  if (!data) return <div className={styles.course}><Link href="/study/lessons">← {copy.back}</Link>
    <p role={error ? "alert" : "status"}>{error ? copy.error : copy.loading}</p>
    {error ? <button className="button" onClick={() => void reload()}>{copy.retry}</button> : null}</div>;
  return <div className={styles.player}>
    {celebrate && data.lesson.completed && !data.step && <CompletionConfetti />}
    <LessonProgressHeader title={data.lesson.title} completed={data.lesson.completed_steps} total={data.lesson.total_steps}
      viewing={data.viewing} audioEnabled={audio.enabled} onAudioChange={audio.setEnabled} />
    {saveError ? <div className={styles.feedback} role="alert"><p>{saveError}</p><button className="button button--small" disabled={busy} onClick={() => void reload()}>{copy.reload}</button></div> : null}
    <LessonContent key={`${id}:${contentLocale}:${data.viewing}:${data.step?.id ?? "complete"}`} state={data} settings={auth?.settings} busy={busy} autoPlay={audio.enabled}
      onSubmit={submit} onView={(index) => { setCelebrate(false); setSaveError(""); setViewing(index >= data.cursor ? undefined : index); }} onResume={() => setViewing(undefined)} />
  </div>;
}

function LessonContent({ state, settings, busy, autoPlay, onSubmit, onView, onResume }: {
  state: LessonState; settings?: UserSettings; busy: boolean; autoPlay: boolean;
  onSubmit: (command: LessonCommand) => Promise<void>; onView: (index: number) => void; onResume: () => void;
}) {
  const { locale } = useI18n();
  const copy = lessonCopy[locale];
  const [answer, setAnswer] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const action = useRef<HTMLButtonElement>(null);
  const composing = useRef(false);
  const compositionEndedAt = useRef(0);
  useEffect(() => {
    const handleEnter = (event: KeyboardEvent) => {
      if (event.key !== "Enter" || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.isComposing || event.keyCode === 229 || composing.current || Date.now() - compositionEndedAt.current < 50) return;
      const target = event.target instanceof Element ? event.target : null;
      // Preserve native activation of links, audio, previous, and other secondary controls.
      if (target?.closest("a, textarea, select, [contenteditable=true], input[type=checkbox]") ||
        (target?.closest("button") && target.closest("button") !== action.current)) return;
      if (target?.closest("input") && !form.current?.contains(target)) return;
      event.preventDefault();
      if (!event.repeat && action.current && !action.current.disabled) form.current?.requestSubmit(action.current);
    };
    document.addEventListener("keydown", handleEnter);
    return () => document.removeEventListener("keydown", handleEnter);
  }, []);
  useEffect(() => {
    const element = heading.current;
    if (!element) return;
    element.focus({ preventScroll: true });
    if (element.getBoundingClientRect().top < 100) element.scrollIntoView({ block: "start" });
  }, []);
  const { step, feedback } = state;
  const past = state.viewing < state.cursor;
  const question = step?.kind === "choice" || step?.kind === "recall";
  const kanjiMeanings = step?.kind === "kanji" ? (step.meaning ?? "").split(";").map(value => value.trim()).filter(Boolean) : [];
  if (!step) return <section className={styles.completed}>
    <span className={styles.completionMark} aria-hidden="true">✓</span>
    <h1 ref={heading} tabIndex={-1}>{state.lesson.is_recap ? copy.themeFinished : copy.finished}</h1><p>{state.lesson.is_recap ? copy.themeFinishedText : copy.finishedText}</p>
    <p className={styles.score}><strong>{state.correct} / {state.answered}</strong> {copy.score}</p>
    {state.recap_total ? <p><strong>{state.recap_correct} / {state.recap_total}</strong> {copy.recapScore}</p> : null}
    <p className={styles.note}>{copy.mastery}</p>
    <div className={styles.completionActions}>{state.next_lesson_id ? <Link className="button button--accent" href={`/study/lessons/${state.next_lesson_id}`}>{copy.nextLesson} →</Link> : <Link className="button button--accent" href="/study/lessons">{copy.back}</Link>}
      <button className="button" onClick={() => onView(0)}>{copy.reread}</button></div>
  </section>;
  return <section className={styles.lessonContent} aria-busy={busy}>
    <div className={styles.stepMeta}><span>{step.recap_category
      ? `${copy.recapCategories[step.recap_category]} · ${step.recap_section_index} / ${step.recap_section_total}`
      : step.recap ? copy.recap : `N5 · ${copy.step} ${state.viewing + 1}`}</span>{past ? <button onClick={onResume}>{copy.resume}</button> : step.review ? <span>{copy.reviewWord}</span> : null}</div>
    <h1 ref={heading} tabIndex={-1} className={styles.stepTitle}>{step.title}</h1>
    {step.source_lesson_title ? <p className={styles.note}>{copy.recapSource} {step.source_lesson_title}</p> : null}
    {step.body ? <p className={styles.body}>{step.body}</p> : null}
    {step.kind === "kanji" && step.character ? <div className={styles.kanjiLayout}>
      <KanjiStrokePlayer character={step.character} level="N5" />
      <div className={styles.kanjiDetails}><h2>{kanjiMeanings[0]}</h2>
        {kanjiMeanings.length > 1 ? <p className={styles.kanjiGlosses}>{kanjiMeanings.slice(1).join(" · ")}</p> : null}
        <dl className={styles.readings}><dt>{copy.on}</dt><dd lang="ja">{step.onyomi?.join(" · ") || "—"}</dd><dt>{copy.kun}</dt><dd lang="ja">{step.kunyomi?.join(" · ") || "—"}</dd></dl>
        {step.lines?.length ? <div className={styles.kanjiExamples}>{step.lines.map((line, index) => <p key={index}><LessonJapanese {...line} settings={settings} /><span>{line.translation}</span></p>)}</div> : null}
      </div>
    </div> : null}
    {step.japanese ? <div className={styles.japaneseBlock}>
      <p className={step.kind === "word" || step.kind === "choice" ? styles.japanese : styles.sentence} lang="ja">
        {step.segments?.length ? <FuriganaText segments={step.segments} mode={settings?.furigana_display_mode ?? "always"} helper={settings?.furigana_helper_enabled ?? false} /> : <ClozeText text={step.japanese} blankLabel={copy.answer} />}
      </p>
      {settings?.romaji_enabled && step.romaji ? <p className={styles.note} lang="ja-Latn">{step.romaji}</p> : null}
      {step.audio_url ? <AudioButton src={step.audio_url} label={step.japanese} autoPlay={autoPlay && step.kind !== "recall"} /> : null}
      {step.translation ? <p className={styles.translation}>{step.translation}</p> : null}
    </div> : null}
    {step.meaning && step.kind !== "kanji" ? <p className={styles.meaning}>{step.meaning}</p> : null}
    {step.reading_note ? <p className={styles.note}>{step.reading_note}</p> : null}
    {step.lines && step.kind !== "kanji" ? <div className={styles.dialogue}>{step.lines.map((line, index) => <div key={index}>
      {line.speaker ? <span className={styles.speaker}>{line.speaker}</span> : null}
      <div><p><LessonJapanese {...line} settings={settings} /></p><p className={styles.note}>{line.translation}</p></div>
    </div>)}</div> : null}
    <form ref={form} onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => {
      composing.current = false; compositionEndedAt.current = Date.now();
    }} onSubmit={(event) => {
      event.preventDefault();
      if (busy || composing.current || Date.now() - compositionEndedAt.current < 50) return;
      if (past) { onView(state.viewing + 1); return; }
      if (step.kind === "choice" && !feedback) return;
      if (question && !feedback && !answer.trim()) return;
      void onSubmit({ action: question && !feedback ? "answer" : "continue", step_id: step.id, revision: state.revision,
        ...(question && !feedback ? { answer } : {}) });
    }}>
      {step.prompt ? <p id="lesson-prompt" className={styles.prompt}>{step.prompt}</p> : null}
      {step.kind === "choice" ? <fieldset className={styles.options} disabled={busy || !!feedback || past} aria-describedby="lesson-prompt">
        <legend className="sr-only">{copy.answer}</legend>
        {step.options?.map((option) => {
          const selected = (feedback?.selected_option_id ?? answer) === option.id;
          const correct = feedback?.correct_option_id === option.id;
          const wrong = !!feedback && !feedback.correct && selected;
          return <button key={option.id} type="button" className={styles.option} aria-pressed={selected} data-selected={selected} data-result={correct ? "correct" : wrong ? "wrong" : undefined}
            onClick={() => {
              if (busy || feedback || past) return;
              setAnswer(option.id);
              void onSubmit({ action: "answer", step_id: step.id, revision: state.revision, answer: option.id });
            }}>
            <span className={styles.optionLabel}>{option.label}</span>
            {correct ? <span className="sr-only">{copy.correction}</span> : wrong ? <span className="sr-only">{copy.answer}</span> : null}
          </button>;
        })}
      </fieldset> : null}
      {step.kind === "recall" ? <label className={styles.recall}>{copy.answer}
        <input name="answer" value={answer} disabled={busy || !!feedback || past} onChange={(event) => setAnswer(event.target.value)} autoComplete="off" autoCapitalize="off" spellCheck={false} placeholder={copy.placeholder} aria-describedby="lesson-prompt" />
      </label> : null}
      {feedback?.correct ? step.kind === "recall"
        ? <div className={styles.feedback} data-correct="true" role="status">
          <strong>{copy.correct}</strong>
          <p>
            {feedback.japanese ? <>
              <LessonJapanese japanese={feedback.japanese} segments={feedback.segments} romaji={feedback.romaji} settings={settings} />
              {feedback.answer !== feedback.japanese ? <> · <span lang="ja">{feedback.answer}</span></> : null}
            </> : <span lang="ja">{feedback.answer}</span>}
          </p>
          {feedback.audio_url && feedback.japanese ? <AudioButton src={feedback.audio_url} label={feedback.japanese} autoPlay={autoPlay} /> : null}
        </div>
        : <span className="sr-only" role="status">{copy.correct}</span> : null}
      {feedback?.correct && step.kind !== "recall" && feedback.audio_url && feedback.japanese ? <AudioButton src={feedback.audio_url} label={feedback.japanese} autoPlay={autoPlay} /> : null}
      {feedback && !feedback.correct ? <div className={styles.feedback} data-correct="false" role="status" aria-live="polite">
        <span className="sr-only">{copy.incorrect}</span>
        <p className={styles.feedbackAnswer}>
          {feedback.japanese && feedback.meaning ? <>
            <LessonJapanese japanese={feedback.japanese} segments={feedback.segments} romaji={feedback.romaji} settings={settings} />
            {" — "}{feedback.meaning}
          </> : <strong>{feedback.answer}</strong>}
        </p>
        {feedback.explanation ? <p className={styles.note}>{feedback.explanation}</p> : null}
        {feedback.audio_url && feedback.japanese ? <AudioButton src={feedback.audio_url} label={feedback.japanese} autoPlay={autoPlay} /> : null}
      </div> : null}
      <footer className={styles.lessonFooter}>
        <button className="button" type="button" disabled={busy || state.viewing === 0} onClick={() => onView(state.viewing - 1)}>← {copy.previous}</button>
        {step.kind === "choice" && !feedback && !past ? (busy ? <span className={styles.note} role="status">{copy.saving}</span> : null) : <button ref={action} className="button button--accent" type="submit" aria-keyshortcuts="Enter" disabled={busy || (question && !feedback && !past && !answer.trim())}>
          {busy ? copy.saving : question && !feedback && !past ? copy.check : copy.next} <span aria-hidden="true">→</span>
        </button>}
      </footer>
    </form>
  </section>;
}
