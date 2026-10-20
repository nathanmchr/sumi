import type { JLPTLevelCode } from "@/lib/types";

export const JLPT_LEVELS: JLPTLevelCode[] = ["N5", "N4", "N3", "N2", "N1"];

export function formatLevelRange(minimum?: JLPTLevelCode, maximum?: JLPTLevelCode) {
  if (!maximum) return "—";
  return !minimum || minimum === maximum ? maximum : `${minimum}–${maximum}`;
}
