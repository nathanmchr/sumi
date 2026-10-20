"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { useI18n } from "@/lib/i18n";
import { loadKanjiStrokes, type KanjiStrokeData } from "@/lib/kanji-strokes";
import { KanjiPlayerControls } from "@/components/kanji-player-controls";
import styles from "./kanji-stroke-player.module.css";

const BASE_STROKES_PER_SECOND = 1.5;

function StrokePlayer({ data }: { data: KanjiStrokeData }) {
  const { t } = useI18n();
  const total = data.strokes.length;
  const position = useRef(total);
  const [progress, setProgress] = useState(total);
  const [playing, setPlaying] = useState(false);
  const [numbers, setNumbers] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => { setReducedMotion(preference.matches); setPlaying(false); };
    const hide = () => { if (document.hidden) setPlaying(false); };
    sync();
    preference.addEventListener("change", sync);
    document.addEventListener("visibilitychange", hide);
    return () => {
      preference.removeEventListener("change", sync);
      document.removeEventListener("visibilitychange", hide);
    };
  }, []);

  useEffect(() => {
    if (!playing) return;
    let frame: number;
    let previous: number | null = null;
    const tick = (time: number) => {
      const delta = previous === null ? 0 : Math.min(time - previous, 64);
      previous = time;
      position.current = Math.min(total, position.current + delta * speed * BASE_STROKES_PER_SECOND / 1000);
      setProgress(position.current);
      if (position.current >= total) setPlaying(false);
      else frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, total]);

  function seek(next: number) {
    setPlaying(false);
    position.current = Math.max(0, Math.min(next, total));
    setProgress(position.current);
  }

  const completed = Math.floor(progress);
  const current = reducedMotion ? completed : Math.min(total, Math.ceil(progress));
  const active = progress >= total ? -1 : Math.max(0, current - 1);

  return (
    <section className={styles.player} aria-label={t("strokes.title")}>
      <span className="sr-only" role="status">{t("strokes.progress", { current, total })}</span>
      <svg className={styles.canvas} viewBox={data.view_box.join(" ")} role="img"
        aria-label={t("strokes.diagram", { character: data.character })}>
        <g className={styles.grid} aria-hidden="true"><path d="M54.5 0v109M0 54.5h109" /></g>
        <g className={styles.ghost} aria-hidden="true">
          {data.strokes.map((stroke, index) => <path key={index} d={stroke.path} />)}
        </g>
        <g className={styles.ink} aria-hidden="true">
          {data.strokes.map((stroke, index) => {
            // The last 18% of each interval gives a short pause between strokes.
            const amount = reducedMotion
              ? (index < completed ? 1 : 0)
              : Math.max(0, Math.min(1, (progress - index) / 0.82));
            return <path key={index} data-stroke={index + 1} d={stroke.path} pathLength="1"
              strokeDasharray="1" strokeDashoffset={1 - amount}
              visibility={amount > 0 ? "visible" : "hidden"}
              className={index === active ? styles.active : undefined} />;
          })}
        </g>
        {numbers ? <g className={styles.numbers} aria-hidden="true">
          {data.strokes.map((stroke, index) => <text key={index}
            transform={`matrix(${stroke.number_transform.join(" ")})`}
            className={index === active ? styles.activeNumber : undefined}>{index + 1}</text>)}
        </g> : null}
      </svg>
      <KanjiPlayerControls playing={playing} partial={progress > 0 && progress < total}
        canPrevious={current > 0} canNext={progress < total} numbers={numbers} speed={speed}
        onPlay={() => {
          if (playing) { setPlaying(false); return; }
          if (position.current >= total) { position.current = 0; setProgress(0); }
          setPlaying(true);
        }}
        onPrevious={() => seek(current - 1)} onNext={() => seek(Math.floor(progress) + 1)}
        onReset={() => seek(0)} onNumbers={() => setNumbers(!numbers)} onSpeed={setSpeed} />
      {reducedMotion ? <p className={styles.note}>{t("strokes.reducedMotion")}</p> : null}
      <p className={styles.credit}>
        <a href="https://kanjivg.tagaini.net/" target="_blank" rel="noopener noreferrer">KanjiVG</a>
        {" · Ulrich Apel · "}<a href="/kanji-strokes/NOTICE.md" target="_blank" rel="noopener noreferrer">CC BY-SA 3.0</a>
      </p>
    </section>
  );
}

export function KanjiStrokePlayer({ character, level }: { character: string; level: string }) {
  const { t } = useI18n();
  const { data, error, isLoading, mutate } = useSWR(["kanji-strokes", level, character], () => loadKanjiStrokes(character, level), {
    revalidateOnFocus: false, shouldRetryOnError: false,
  });
  if (data) return <StrokePlayer key={character} data={data} />;
  return <div className={styles.fallback}>
    <div className="kanji-hero" lang="ja">{character}</div>
    <p className={styles.note} role="status">{t(error ? "strokes.unavailable" : "common.loading")}</p>
    {error ? <button className="button button--small" disabled={isLoading} onClick={() => { void mutate().catch(() => undefined); }}>{t("auth.retry")}</button> : null}
  </div>;
}
