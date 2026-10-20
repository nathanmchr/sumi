"use client";

import { useTransition } from "react";
import type { JLPTLevelCode } from "@/lib/types";
import clsx from "clsx";

type Props = {
  label: string;
  value: JLPTLevelCode;
  onChange: (value: JLPTLevelCode) => void;
};

const levels: JLPTLevelCode[] = ["N5", "N4", "N3", "N2", "N1"];

export function LevelSelector({ label, value, onChange }: Props) {
  const [, startTransition] = useTransition();

  return (
    <div className="field" role="group" aria-label={label}>
      <span className="field__label">{label}</span>
      <div className="segmented">
        {levels.map((level) => (
          <button
            key={level}
            type="button"
            aria-pressed={level === value}
            className={clsx("segmented__item", level === value && "is-active")}
            onClick={() => startTransition(() => onChange(level))}
          >
            {level}
          </button>
        ))}
      </div>
    </div>
  );
}

