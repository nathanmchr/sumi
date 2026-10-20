"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ApiError, answerQuizQuestion, beginQuizQuestion, getQuizTurn, nextQuizQuestion, session, startQuiz } from "@/lib/api";
import { FuriganaText } from "@/components/furigana-text";
import { MemoryBar } from "@/components/memory-bar";
import { AudioButton } from "@/components/audio-button";
import { ClozeText } from "@/components/cloze-text";
import { StudyAudioToggle, useStudyAudio } from "@/components/study-audio";
import { useI18n } from "@/lib/i18n";
import { formatPowers } from "@/lib/format-text";
import type { ContentType, QuizTurn } from "@/lib/types";

export default function StudySessionPage() {
  return <Suspense><QuizSession /></Suspense>;
}

function QuizSession() {
  const { locale, t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const sid = params.get("sid");
  const requestedCategory = params.get("category");
  const initialCategory = ["vocabulary", "kanji", "grammar"].includes(requestedCategory ?? "") ? requestedCategory as ContentType : undefined;
  const [category, setCategory] = useState<ContentType | "">(initialCategory ?? "");
  const [turn, setTurn] = useState<QuizTurn | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<"request" | "answer" | "expired" | "resume" | "begin" | null>(null);
  // Outcomes answered on this page, oldest first; earlier answers of a resumed session are unknown.
  const [outcomes, setOutcomes] = useState<boolean[]>([]);
  const busy = useRef(false);
  const choiceLock = useRef<string | null>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const { data: currentSession } = useSWR("session", session);
  const audio = useStudyAudio(currentSession?.user.id);
  const { mutate } = useSWRConfig();
  const question = turn?.question;
  const result = question?.result;
  const introducing = question?.phase === "introduction";
  const questionHeadingRef = useRef<HTMLHeadingElement>(null);
  const furiganaMode = currentSession?.settings.furigana_display_mode ?? "always";

  function acceptTurn(value: QuizTurn) {
    setTurn(value);
    const choice = value.question?.result?.selected_option_id ?? null;
    choiceLock.current = choice;
    setSelected(choice);
    setError(null);
  }

  useEffect(() => {
    if (!sid || sid === turn?.session_id) return;
    let cancelled = false;
    setPending(true);
    getQuizTurn(sid).then(value => { if (!cancelled) acceptTurn(value); })
      .catch(() => { if (!cancelled) setError("resume"); })
      .finally(() => { if (!cancelled) setPending(false); });
    return () => { cancelled = true; };
  }, [sid, turn?.session_id]);

  useEffect(() => { if (result) feedbackRef.current?.focus(); }, [result]);
  useEffect(() => { setOutcomes([]); }, [turn?.session_id]);

  // 1–9 picks a choice, Enter begins or continues. Controls with their own keyboard behaviour keep it.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey || event.repeat) return;
      if (event.target instanceof HTMLElement && event.target.closest("input, select, textarea, button, a")) return;
      if (!question || turn?.ended) return;
      if (event.key === "Enter") {
        if (introducing) { event.preventDefault(); void begin(); }
        else if (result) { event.preventDefault(); void advance(); }
        return;
      }
      const index = Number(event.key) - 1;
      if (!introducing && !result && Number.isInteger(index) && index >= 0 && index < question.choices.length) {
        event.preventDefault();
        void choose(question.choices[index].id);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  async function advance() {
    if (busy.current) return;
    busy.current = true;
    setPending(true);
    setError(null);
    try {
      const next = turn ? await nextQuizQuestion(turn.session_id) : await startQuiz({
        category: category || undefined,
        content_id: initialCategory ? params.get("item") ?? undefined : undefined,
        only_due: params.get("due") === "1",
      });
      acceptTurn(next);
      if (!turn) {
        const query = new URLSearchParams(params.toString());
        query.set("sid", next.session_id);
        router.replace(`/study/session?${query}`, { scroll: false });
      }
    } catch { setError("request"); }
    finally { busy.current = false; setPending(false); }
  }

  async function begin() {
    if (!question || busy.current) return;
    busy.current = true;
    setPending(true);
    setError(null);
    try {
      const next = await beginQuizQuestion(question.id);
      setTurn(previous => previous && ({ ...previous, question: next }));
    } catch (failure) {
      setError(failure instanceof ApiError && failure.status === 409 ? "expired" : "begin");
    } finally { busy.current = false; setPending(false); }
  }

  useEffect(() => {
    if (question?.phase === "question" && !question.result) questionHeadingRef.current?.focus();
  }, [question?.id, question?.phase]);

  async function choose(optionId: string, retry = false) {
    if (!question || introducing || result || busy.current || (choiceLock.current && !retry)) return;
    // Lock synchronously before rendering or sending anything; retries keep this ID.
    choiceLock.current = optionId;
    setSelected(optionId);
    busy.current = true;
    setPending(true);
    setError(null);
    try {
      const answer = await answerQuizQuestion(question.id, optionId);
      setTurn(previous => previous && ({ ...previous,
        completed_items: previous.completed_items + 1,
        planned_items: answer.planned_items ?? previous.planned_items,
        correct_answers: previous.correct_answers + Number(answer.correct),
        question: { ...question, result: answer },
      }));
      setOutcomes(previous => [...previous, answer.correct]);
      void mutate(key => typeof key === "string" ? ["dashboard", "recommendation"].includes(key) : Array.isArray(key) && ["due-items", "kanji-detail", "grammar-detail"].includes(key[0]));
    } catch (failure) {
      setError(failure instanceof ApiError && failure.status === 409 ? "expired" : "answer");
    } finally { busy.current = false; setPending(false); }
  }

  return <div className="stack quiz-page">
    <header className="page-header">
      <div><h1>{t("study.title")}</h1><p className="muted">{t("quiz.intro")}</p></div>
      <div className="study-session-controls"><StudyAudioToggle enabled={audio.enabled} onChange={audio.setEnabled} /><Link className="button" href="/dashboard">{t("study.exit")}</Link></div>
    </header>

    {!turn && !sid && <section className="panel stack">
      {!initialCategory && <label className="stack stack--compact">{t("quiz.category")}
        <select className="input" value={category} onChange={event => setCategory(event.target.value as ContentType | "")} disabled={pending}>
          <option value="">{t("quiz.mixed")}</option>
          <option value="vocabulary">{t("nav.vocabulary")}</option>
          <option value="kanji">{t("nav.kanji")}</option>
          <option value="grammar">{t("nav.grammar")}</option>
        </select>
      </label>}
      {params.get("due") === "1" && <p>{t("quiz.dueOnly")}</p>}
      <button className="button button--accent" disabled={pending || !currentSession} onClick={advance}>{t("quiz.start")}</button>
    </section>}

    {turn && !turn.ended && question && <article className="panel stack quiz-card" aria-busy={pending}>
      <div className="session-progress">
        {turn.planned_items <= 40 ? <ol className="quiz-squares" role="progressbar" aria-label={t("study.plan")}
          aria-valuemin={0} aria-valuemax={turn.planned_items} aria-valuenow={turn.completed_items}>
          {Array.from({ length: turn.planned_items }, (_, index) => {
            const known = index - (turn.completed_items - outcomes.length);
            const state = index < turn.completed_items ? (known >= 0 && !outcomes[known] ? "miss" : "done") : index === turn.completed_items ? "current" : "todo";
            return <li key={index} data-state={state} aria-hidden="true" />;
          })}
        </ol> : <progress value={turn.completed_items} max={turn.planned_items} aria-label={t("study.plan")} />}
        <span>{t("quiz.progress", { count: turn.completed_items, total: turn.planned_items })}</span>
      </div>
      {introducing && <div className="quiz-discovery-heading"><h3>{t("quiz.newWord")}</h3><p className="muted">{t("quiz.discoverFirst")}</p></div>}
      <div className={`quiz-prompt${question.kind === "cloze" || question.content_type === "grammar" ? "" : " quiz-prompt--word"}`}>
        <p className="context-label">{t(`nav.${question.content_type}`)} · {question.jlpt_level_code}</p>
        <h2 lang="ja" ref={questionHeadingRef} tabIndex={-1}>{question.furigana_segments.length ? <FuriganaText segments={question.furigana_segments} mode={furiganaMode} helper={currentSession?.settings.furigana_helper_enabled} /> : <ClozeText text={question.title} blankLabel={locale === "fr" ? "À compléter" : "Fill in the blank"} />}</h2>
        {question.content_type === "kanji" && question.reading && furiganaMode !== "hidden" && <p className={`quiz-reading quiz-reading--${furiganaMode}`} tabIndex={furiganaMode === "hover" ? 0 : undefined} lang="ja">{question.reading}</p>}
        {question.audio_url && <AudioButton key={question.id} src={question.audio_url} label={question.title} autoPlay={audio.enabled && question.content_type === "vocabulary"} />}
        {question.context && <p lang={question.locale}>{formatPowers(question.context)}</p>}
      </div>
      {introducing && question.introduction && <div className="quiz-discovery stack">
        <p className="quiz-discovery__meaning" lang={question.locale}>{formatPowers(question.introduction.meaning)}</p>
        {question.introduction.example && <div className="example-block">
          <strong lang="ja">{formatPowers(question.introduction.example.text)}</strong>
          <p lang={question.locale}>{formatPowers(question.introduction.example.translation)}</p>
        </div>}
        <button type="button" className="button button--accent" disabled={pending} onClick={begin}>{t("quiz.ready")}<span className="kbd" aria-hidden="true">↵</span></button>
      </div>}
      {!introducing && <fieldset className="quiz-choices" disabled={Boolean(selected) || pending}>
        <legend lang={question.locale}>{question.instruction}</legend>
        {question.choices.map((choice, index) => {
          const correct = result?.correct_option_id === choice.id;
          const wrong = Boolean(result && !result.correct && result.selected_option_id === choice.id);
          return <button key={choice.id} type="button" lang={question.kind === "cloze" ? "ja" : question.locale}
            className={`quiz-choice${correct ? " is-correct" : wrong ? " is-wrong" : selected === choice.id ? " is-selected" : ""}`}
            onClick={() => choose(choice.id)} aria-pressed={selected === choice.id}>
            <span className="kbd" aria-hidden="true">{index + 1}</span>
            <span>{formatPowers(choice.label)}</span>
            {correct && <small lang={locale}>✓ {t("quiz.solution")}</small>}
            {wrong && <small lang={locale}>✕ {t("quiz.chosen")}</small>}
          </button>;
        })}
      </fieldset>}
      {result && <div className={`quiz-feedback${result.correct ? " is-correct" : " is-wrong"}`} ref={feedbackRef} tabIndex={-1} role="status">
        <strong>{t(result.correct ? "quiz.correct" : "quiz.incorrect")}</strong>
        <div lang={question.locale}>
          <p><span lang="ja">{result.title}{result.reading ? ` · ${result.reading}` : ""}</span> — {formatPowers(result.meaning)}</p>
          {result.explanation && <p>{formatPowers(result.explanation)}</p>}
          {result.example ? <div className="example-block"><strong lang="ja">{formatPowers(result.example.text)}</strong><p>{formatPowers(result.example.translation)}</p></div>
            : !result.correct && <p className="muted" lang={locale}>{t("quiz.exampleMissing")}</p>}
        </div>
        <MemoryBar memory={result.memory} stability={result.stability} status={result.status} />
        <button className="button button--accent" disabled={pending} onClick={advance}>{t("quiz.next")}<span className="kbd" aria-hidden="true">↵</span></button>
      </div>}
      {!result && !introducing && <p className="quiz-keys" aria-hidden="true">{t("quiz.keys", { count: question.choices.length })}</p>}
    </article>}

    {turn?.ended && <section className="panel stack">
      <h2>{t("quiz.finished")}</h2>
      <p>{t("quiz.score", { correct: turn.correct_answers, count: turn.completed_items })}</p>
      {turn.acquired_items > 0 && <p>{t("quiz.acquiredCount", { count: turn.acquired_items })}</p>}
      {turn.acquiring_items > 0 && <p>{t("quiz.acquiringCount", { count: turn.acquiring_items })}</p>}
      <p>{t(turn.next_due_at ? "quiz.reviewLater" : "quiz.empty")}</p>
      {(!category || category === "grammar") && <p className="muted">{t("quiz.grammarCoverage", { count: turn.grammar_points_available })}</p>}
      <Link className="button" href="/review">{t("nav.reviews")}</Link>
    </section>}

    {pending && <p role="status" className="muted">{t("common.loading")}</p>}
    {error && <div className="panel stack" role="alert">
      <p>{t(error === "answer" ? "quiz.answerError" : error === "expired" ? "quiz.expired" : error === "resume" ? "quiz.resumeError" : error === "begin" ? "quiz.beginError" : "quiz.error")}</p>
      {error === "answer" && selected ? <button className="button" disabled={pending} onClick={() => choose(selected, true)}>{t("quiz.retry")}</button>
        : error === "begin" ? <button className="button" disabled={pending} onClick={begin}>{t("quiz.retry")}</button>
        : error === "resume" ? <a className="button" href="/study/session">{t("quiz.newSession")}</a>
        : <button className="button" disabled={pending} onClick={advance}>{t(error === "expired" ? "quiz.next" : "quiz.retry")}</button>}
    </div>}
  </div>;
}
