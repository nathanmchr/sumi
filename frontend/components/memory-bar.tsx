"use client";

import { useI18n } from "@/lib/i18n";
import type { MemoryProgress, ReviewStatus } from "@/lib/types";

type Props = {
  memory?: MemoryProgress | null;
  stability: number | null;
  status: ReviewStatus;
};

export function MemoryBar({ memory, stability, status }: Props) {
  const { t } = useI18n();
  const initial = memory?.phase === "acquisition";
  const value = memory?.value ?? Math.min(1, (stability ?? 0) / 90);
  const label = t(initial ? "quiz.acquisition" : "quiz.consolidation");
  const detail = initial
    ? t("quiz.acquisitionCount", { count: memory.successes ?? 0, total: memory.required_successes ?? 5 })
    : t(`status.${status}`);

  return <div className="memory-progress">
    <progress className="memory-progress__bar" value={value} max={1} aria-label={label} aria-valuetext={detail} />
  </div>;
}
