"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { homophones, session } from "@/lib/api";
import { resolveAudioSource } from "@/lib/audio";
import { formatPowers } from "@/lib/format-text";
import { useI18n } from "@/lib/i18n";
import type { HomophoneGroup, HomophoneWord } from "@/lib/types";
import styles from "./homophone-browser.module.css";

function PlaybackIcon({ active = false }: { active?: boolean }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
      {active ? <rect x="6" y="6" width="12" height="12" rx="2" /> : <path d="M8 5.5v13l11-6.5-11-6.5Z" />}
    </svg>
  );
}

function Comparison({ group }: { group: HomophoneGroup }) {
  const { t } = useI18n();
  const audioRef = useRef<HTMLAudioElement>(null);
  const queueRef = useRef<HomophoneWord[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runRef = useRef(0);
  const speedRef = useRef(1);
  const [speed, setSpeed] = useState(1);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [audioError, setAudioError] = useState(false);
  const playable = group.words.filter((word) => word.audio_url);
  const activeWord = group.words.find((word) => word.id === activeId);
  const sources = playable.map((word) => resolveAudioSource(word.audio_url!));
  const hasSharedAudio = new Set(sources).size < sources.length;

  useEffect(() => {
    const audio = audioRef.current;
    return () => {
      runRef.current++;
      if (timerRef.current) clearTimeout(timerRef.current);
      if (loadTimerRef.current) clearTimeout(loadTimerRef.current);
      audio?.pause();
      audio?.removeAttribute("src");
      audio?.load();
    };
  }, []);

  function stop() {
    runRef.current++;
    if (timerRef.current) clearTimeout(timerRef.current);
    if (loadTimerRef.current) clearTimeout(loadTimerRef.current);
    queueRef.current = [];
    audioRef.current?.pause();
    audioRef.current?.removeAttribute("src");
    audioRef.current?.load();
    setActiveId(null);
    setLoading(false);
  }

  function waitForAudio() {
    setLoading(true);
    if (loadTimerRef.current) clearTimeout(loadTimerRef.current);
    const run = runRef.current;
    loadTimerRef.current = setTimeout(() => {
      if (run !== runRef.current) return;
      stop();
      setAudioError(true);
    }, 15000);
  }

  async function playWord(word: HomophoneWord) {
    const audio = audioRef.current;
    if (!audio || !word.audio_url) return;
    const run = ++runRef.current;
    setActiveId(word.id);
    waitForAudio();
    setAudioError(false);
    audio.src = resolveAudioSource(word.audio_url);
    audio.playbackRate = speedRef.current;
    audio.preservesPitch = true;
    try {
      await audio.play();
      if (run === runRef.current) {
        if (loadTimerRef.current) clearTimeout(loadTimerRef.current);
        setLoading(false);
      }
    } catch {
      // A newer click or navigation may have intentionally interrupted play().
      if (run !== runRef.current) return;
      stop();
      setAudioError(true);
    }
  }

  function start(words: HomophoneWord[]) {
    stop();
    const [first, ...rest] = words;
    queueRef.current = rest;
    if (first) void playWord(first);
  }

  function playNext() {
    const next = queueRef.current.shift();
    if (!next) {
      stop();
      return;
    }
    const run = runRef.current;
    timerRef.current = setTimeout(() => {
      if (run === runRef.current) void playWord(next);
    }, 450);
  }

  return (
    <section className={styles.comparison} aria-labelledby="comparison-heading">
      <header className={styles.comparisonHeader}>
        <div>
          <p className={styles.readingLabel}>{t("homophones.sameReading")}</p>
          <h2 id="comparison-heading" lang="ja">{group.reading}</h2>
        </div>
        <span className={styles.soundMark} aria-hidden="true">
          {[18, 30, 42, 26, 36, 18].map((height, index) => <i key={index} style={{ height }} />)}
        </span>
      </header>

      <div className={styles.controls}>
        <button className="button button--accent button--small" type="button" disabled={!activeId && playable.length < 2}
          onClick={() => activeId ? stop() : start(playable)}>
          <PlaybackIcon active={Boolean(activeId)} />
          {t(activeId ? "homophones.stop" : "homophones.compare")}
        </button>
        <label className={styles.speed}>
          <span>{t("homophones.speed")}</span>
          <select value={speed} onChange={(event) => {
            const value = Number(event.target.value);
            speedRef.current = value;
            setSpeed(value);
            if (audioRef.current) audioRef.current.playbackRate = value;
          }}>
            <option value={1}>{t("homophones.normal")} · 1×</option>
            <option value={0.8}>{t("homophones.slow")} · 0.8×</option>
          </select>
        </label>
      </div>

      <ul className={styles.words}>
        {group.words.map((word, index) => (
          <li key={word.id} className={styles.word} data-playing={activeId === word.id}>
            <span className={styles.wordNumber} aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
            <div className={styles.wordBody}>
              <div className={styles.wordHeading}>
                <Link href={`/study/vocabulary/${word.id}`} className={styles.wordLink} aria-label={t("homophones.openWord", { word: word.japanese })}>
                  <span lang="ja">{word.japanese}</span>
                  <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M6 18 18 6M7 6h11v11" /></svg>
                </Link>
                <span className={styles.wordLevel}>{word.jlpt_level_code}</span>
              </div>
              <p lang={word.translation_locale}>{formatPowers(word.translation) || t("homophones.missingMeaning")}</p>
            </div>
            {word.audio_url ? (
              <button type="button" className={styles.playButton}
                aria-label={activeId === word.id ? t("homophones.stop") : t("homophones.listen", { word: word.japanese })}
                aria-pressed={activeId === word.id} aria-busy={activeId === word.id && loading}
                onClick={() => activeId === word.id ? stop() : start([word])}>
                <PlaybackIcon active={activeId === word.id} />
              </button>
            ) : <span className={styles.unavailable}>{t("homophones.noAudio")}</span>}
          </li>
        ))}
      </ul>

      <p role="status" className={styles.playbackStatus}>
        {activeWord ? t(loading ? "homophones.loadingAudio" : "homophones.playing", { word: activeWord.japanese }) : ""}
      </p>
      {audioError ? <p role="alert" className="error-text">{t("homophones.audioError")}</p> : null}
      {hasSharedAudio ? <p className={styles.sharedNote}>{t("homophones.sharedAudio")}</p> : null}
      <audio ref={audioRef} preload="none" onEnded={playNext}
        onWaiting={waitForAudio} onPlaying={() => {
          if (loadTimerRef.current) clearTimeout(loadTimerRef.current);
          setLoading(false);
        }}
        onError={() => {
          if (!audioRef.current?.error) return;
          stop();
          setAudioError(true);
        }} />
    </section>
  );
}

export function HomophoneBrowser({ initialQuery = "" }: { initialQuery?: string }) {
  const { t } = useI18n();
  const [input, setInput] = useState(initialQuery);
  const [{ query, offset }, setFilter] = useState({ query: initialQuery, offset: 0 });
  const [selected, setSelected] = useState<string | null>(null);
  const { data: currentSession } = useSWR("session", session);
  const contentLocale = currentSession?.settings.content_locale ?? "en";
  const { data, error, isLoading, mutate } = useSWR(
    ["homophones", query, contentLocale, offset], () => homophones(query, contentLocale, offset),
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );

  useEffect(() => {
    const timer = setTimeout(() => setFilter((previous) => previous.query === input.trim()
      ? previous : { query: input.trim(), offset: 0 }), 250);
    return () => clearTimeout(timer);
  }, [input]);

  const group = data?.groups.find((item) => item.reading === selected) ?? data?.groups[0];

  return (
    <div className={`stack ${styles.page}`}>
      <header className="page-header">
        <div><h1>{t("homophones.title")}</h1></div>
        <Link className="button button--small" href="/study/vocabulary">{t("detail.backVocabulary")}</Link>
      </header>
      <p className={styles.intro}>{t("homophones.intro")}</p>
      <div className={styles.searchRow}>
        <label className="search-box">
          <span className="sr-only">{t("homophones.search")}</span>
          <input type="search" className="input" value={input} maxLength={100}
            placeholder={t("homophones.search")} onChange={(event) => setInput(event.target.value)} />
        </label>
        <span className={styles.count} role="status">{data ? t(data.total === 1 ? "homophones.oneGroup" : "homophones.groups", { count: data.total }) : ""}</span>
      </div>

      {isLoading ? <p className={styles.empty} role="status">{t("common.loading")}</p> : error ? (
        <div className={styles.empty}>
          <p role="alert">{t("homophones.error")}</p>
          <button className="button button--small" onClick={() => { void mutate().catch(() => undefined); }}>{t("auth.retry")}</button>
        </div>
      ) : !group ? (
        <div className={styles.empty}><h2>{t("homophones.empty")}</h2><p>{t("homophones.emptyHint")}</p></div>
      ) : (
        <div className={styles.workbench}>
          <div className={styles.library}>
            <ul className={styles.groups} aria-label={t("homophones.sameReading")}>
              {data?.groups.map((item) => (
                <li key={item.reading}>
                  <button type="button" className={styles.group} aria-pressed={item.reading === group.reading}
                    aria-controls="comparison-heading" aria-label={t("homophones.groupLabel", { reading: item.reading, count: item.words.length })}
                    onClick={() => setSelected(item.reading)}>
                    <span className={styles.groupHeading}><strong lang="ja">{item.reading}</strong><span>{item.words.length}</span></span>
                    <span className={styles.groupWords} lang="ja">{item.words.map((word) => word.japanese).join(" · ")}</span>
                  </button>
                </li>
              ))}
            </ul>
            {data && data.total > data.limit ? (
              <nav className={styles.pagination} aria-label={t("homophones.sameReading")}>
                <button className={styles.pageButton} type="button" disabled={!offset} aria-label={t("homophones.previous")}
                  onClick={() => setFilter({ query, offset: Math.max(0, offset - data.limit) })}>←</button>
                <span>{t("homophones.page", { start: offset + 1, end: Math.min(offset + data.limit, data.total), total: data.total })}</span>
                <button className={styles.pageButton} type="button" disabled={offset + data.limit >= data.total} aria-label={t("homophones.next")}
                  onClick={() => setFilter({ query, offset: offset + data.limit })}>→</button>
              </nav>
            ) : null}
          </div>
          <Comparison key={`${query}:${contentLocale}:${group.reading}`} group={group} />
        </div>
      )}

      <aside className={styles.guidance}>
        <p>{t("homophones.accentNote")}</p>
        <a href="https://www.gavo.t.u-tokyo.ac.jp/ojad/eng/pages/usage" target="_blank" rel="noopener noreferrer">{t("homophones.reference")} ↗</a>
      </aside>
    </div>
  );
}
