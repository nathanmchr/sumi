"use client";

import { useId, type CSSProperties } from "react";
import { useI18n } from "@/lib/i18n";
import { JLPT_LEVELS } from "@/lib/jlpt";
import type { JLPTLevelCode } from "@/lib/types";
import styles from "./level-range-selector.module.css";

type Props = {
  label: string;
  minimum: JLPTLevelCode;
  maximum: JLPTLevelCode;
  onChange: (minimum: JLPTLevelCode, maximum: JLPTLevelCode) => void;
};

export function LevelRangeSelector({ label, minimum, maximum, onChange }: Props) {
  const id = useId();
  const { t } = useI18n();
  const lower = JLPT_LEVELS.indexOf(minimum);
  const upper = JLPT_LEVELS.indexOf(maximum);
  const bounds = minimum === maximum ? [minimum] : [minimum, maximum];
  return (
    <div className={styles.selector} role="group" aria-label={label}>
      <div className={styles.heading}>
        <strong>{label}</strong>
        <span className={`category-row__level ${styles.badge}`}>
          {bounds.map((level, index) => <span key={level}>{index > 0 && "→ "}{level} ({t(`settings.level${level}`)})</span>)}
        </span>
      </div>
      <div className={styles.slider} style={{ "--range-start": `${lower * 25}%`, "--range-end": `${upper * 25}%` } as CSSProperties}>
        <div className={styles.track} aria-hidden="true" />
        <input id={`${id}-min`} className={styles.minimum} type="range" min={0} max={4} step={1} value={lower}
          aria-label={`${label} — ${t("settings.minimumLevel")}`} aria-valuemin={0} aria-valuemax={upper} aria-valuetext={minimum}
          onChange={(event) => onChange(JLPT_LEVELS[Math.min(Number(event.target.value), upper)], maximum)} />
        <input id={`${id}-max`} className={styles.maximum} type="range" min={0} max={4} step={1} value={upper}
          aria-label={`${label} — ${t("settings.maximumLevel")}`} aria-valuemin={lower} aria-valuemax={4} aria-valuetext={maximum}
          onChange={(event) => onChange(minimum, JLPT_LEVELS[Math.max(Number(event.target.value), lower)])} />
        <span className={styles.handles} aria-hidden="true">
          <svg className={`${styles.handle} ${styles.handleMinimum}`} viewBox="0 0 15 28">
            <path d="M 14 1 A 13 13 0 0 0 14 27 Z" />
          </svg>
          <svg className={`${styles.handle} ${styles.handleMaximum}`} viewBox="0 0 15 28">
            <path d="M 14 1 A 13 13 0 0 0 14 27 Z" transform="translate(15 0) scale(-1 1)" />
          </svg>
        </span>
      </div>
      <div className={styles.ticks} aria-hidden="true">{JLPT_LEVELS.map((level, index) => <span key={level} style={{ left: `${index * 25}%` }} data-selected={index >= lower && index <= upper}>{level}</span>)}</div>
    </div>
  );
}
