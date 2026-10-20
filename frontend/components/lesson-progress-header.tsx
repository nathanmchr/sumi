"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { lessonCopy } from "@/lib/lessons";
import { StudyAudioToggle } from "@/components/study-audio";

export function LessonProgressHeader({ title, completed, total, viewing, audioEnabled, onAudioChange }: {
  title: string; completed: number; total: number; viewing: number;
  audioEnabled: boolean; onAudioChange: (enabled: boolean) => void;
}) {
  const { locale } = useI18n();
  const copy = lessonCopy[locale];
  const percent = Math.round(completed / total * 100);
  return <header className="lesson-progress">
    <div className="top">
      <Link className="back" href="/study/lessons" aria-label={copy.back} title={copy.back}>
        <span aria-hidden="true">←</span><span className="back-label">{copy.back}</span>
      </Link>
      <span className="title" title={title}>{title}</span>
      <div className="controls">
        <span className="count">{Math.min(viewing + 1, total)} / {total}</span>
        <StudyAudioToggle enabled={audioEnabled} onChange={onAudioChange} />
        <span>{percent}%</span>
      </div>
    </div>
    <progress aria-label={copy.progress} value={completed} max={total} />
    <style jsx>{`
      .lesson-progress { position: sticky; top: 0; z-index: 5; padding: 0 8px 6px; background: var(--bg); border-bottom: 1px solid var(--line); }
      .top { display: grid; grid-template-columns: 1fr minmax(0, 2fr) 1fr; align-items: center; gap: 16px; height: 44px; font-size: .85rem; line-height: 20px; }
      .back { display: inline-flex; align-items: center; justify-self: start; gap: 6px; height: 44px; white-space: nowrap; color: var(--text); text-decoration: none; }
      .title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center; color: var(--muted); }
      .controls { display: flex; align-items: center; justify-self: end; gap: 8px; height: 44px; white-space: nowrap; font-variant-numeric: tabular-nums; }
      .count { color: var(--muted); }
      progress { display: block; appearance: none; width: 100%; height: 4px; margin: 0; padding: 0; border: 0; border-radius: 999px; overflow: hidden; background: var(--progress-track); }
      progress::-webkit-progress-bar { background: var(--progress-track); }
      progress::-webkit-progress-value { background: var(--focus); border-radius: 999px; }
      progress::-moz-progress-bar { background: var(--focus); border-radius: 999px; }
      @media (max-width: 640px) {
        .top { grid-template-columns: 44px minmax(0, 1fr) auto; gap: 8px; font-size: .75rem; }
        .back { justify-content: center; width: 44px; }
        .back-label { display: none; }
        .title { text-align: left; }
        .controls { gap: 4px; }
      }
    `}</style>
  </header>;
}
