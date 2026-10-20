"use client";

import type { CSSProperties } from "react";
import { useI18n } from "@/lib/i18n";

type Props = {
  playing: boolean;
  partial: boolean;
  canPrevious: boolean;
  canNext: boolean;
  numbers: boolean;
  speed: number;
  onPlay: () => void;
  onPrevious: () => void;
  onNext: () => void;
  onReset: () => void;
  onNumbers: () => void;
  onSpeed: (speed: number) => void;
};

export function KanjiPlayerControls(props: Props) {
  const { t, locale } = useI18n();
  const playLabel = t(props.playing ? "strokes.pause" : props.partial ? "strokes.resume" : "strokes.play");
  return <div className="transport" data-kanji-controls>
    <div className="primary">
      <button type="button" className="play" aria-pressed={props.playing} onClick={props.onPlay}>
        <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          {props.playing ? <path d="M6 5h4v14H6zm8 0h4v14h-4z" /> : <path d="M8 5v14l11-7Z" />}
        </svg>
        {playLabel}
      </button>
      <label className="speed" style={{ "--position": `${(props.speed - 0.5) * 100}%` } as CSSProperties}>
        <span className="speed-caption"><span>{locale === "fr" ? "Vitesse" : "Speed"}</span><span>{props.speed}×</span></span>
        <input type="range" min="0.5" max="1.5" step="0.25" value={props.speed}
          aria-label={t("strokes.speed")} aria-valuetext={`${props.speed}×`}
          onChange={event => props.onSpeed(Number(event.target.value))} />
      </label>
    </div>
    <div className="secondary">
      <div className="group">
        <button type="button" className="tool" disabled={!props.canPrevious} aria-label={t("strokes.previous")}
          title={t("strokes.previous")} onClick={props.onPrevious}>
          <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="m14 7-5 5 5 5M5 7v10" /></svg>
        </button>
        <button type="button" className="tool" disabled={!props.canNext} aria-label={t("strokes.next")}
          title={t("strokes.next")} onClick={props.onNext}>
          <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="m10 7 5 5-5 5M19 7v10" /></svg>
        </button>
      </div>
      <div className="group">
        <button type="button" className="tool" aria-label={t("strokes.restart")} title={t("strokes.restart")} onClick={props.onReset}>
          <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M3 10a9 9 0 1 1 2.6 8.4M3 4v6h6" /></svg>
        </button>
        <button type="button" className="tool" aria-label={t("strokes.numbers")} title={t("strokes.numbers")}
          aria-pressed={props.numbers} onClick={props.onNumbers}>
          <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="m10 4-3 16M17 4l-3 16M5 9h15M4 15h15" /></svg>
        </button>
      </div>
    </div>
    {/* These scoped styles travel with the controls, not the lazy canvas CSS chunk. */}
    <style jsx>{`
      .transport { padding-top: 20px; width: 100%; min-width: 0; }
      .primary { display: grid; grid-template-columns: 112px minmax(0, 1fr); align-items: center; gap: 16px; }
      .play { display: inline-flex; align-items: center; justify-content: center; gap: 8px; width: 100%; height: 44px; padding: 0 10px; border: 1px solid var(--line); border-radius: 999px; background: var(--accent); color: var(--bg-ink, #07251f); box-shadow: 0 4px 0 var(--line); font: inherit; font-size: .85rem; font-weight: 700; cursor: pointer; }
      .play:hover { filter: brightness(.96); }
      .play:active { transform: translateY(2px); box-shadow: 0 2px 0 var(--line); }
      .play svg, .tool svg { flex: none; display: block; }
      .speed { display: flex; flex-direction: column; justify-content: center; min-width: 0; height: 44px; }
      .speed-caption { display: flex; justify-content: space-between; gap: 4px; color: var(--muted); font-size: .7rem; line-height: 16px; font-variant-numeric: tabular-nums; }
      .speed input { appearance: none; -webkit-appearance: none; display: block; width: 100%; min-width: 0; height: 28px; padding: 0; margin: 0; border: 0; border-radius: 0; background: transparent; box-shadow: none; cursor: pointer; }
      .speed input::-webkit-slider-runnable-track { height: 4px; border: 0; border-radius: 999px; background: linear-gradient(to right, var(--focus) var(--position), var(--progress-track) var(--position)); }
      .speed input::-webkit-slider-thumb { appearance: none; -webkit-appearance: none; width: 16px; height: 16px; margin-top: -6px; border: 2px solid var(--focus); border-radius: 50%; background: var(--paper); box-shadow: none; }
      .speed input::-moz-range-track { height: 4px; border: 0; border-radius: 999px; background: var(--progress-track); }
      .speed input::-moz-range-progress { height: 4px; border-radius: 999px; background: var(--focus); }
      .speed input::-moz-range-thumb { width: 12px; height: 12px; border: 2px solid var(--focus); border-radius: 50%; background: var(--paper); box-shadow: none; }
      .secondary { display: flex; align-items: center; justify-content: space-between; margin-top: 16px; padding-top: 8px; border-top: 1px solid var(--line); }
      .group { display: flex; align-items: center; gap: 4px; }
      .tool { display: inline-grid; place-items: center; width: 44px; height: 44px; padding: 0; border: 0; border-radius: 12px; background: transparent; color: var(--muted); cursor: pointer; }
      .tool:hover:not(:disabled), .tool[aria-pressed="true"] { background: var(--mint); color: var(--focus); }
      .tool:disabled { opacity: .3; cursor: default; }
      button:focus-visible, input:focus-visible { outline: 2px solid var(--focus); outline-offset: 3px; }
      @media (prefers-reduced-motion: reduce) { .play:active { transform: none; } }
    `}</style>
  </div>;
}
