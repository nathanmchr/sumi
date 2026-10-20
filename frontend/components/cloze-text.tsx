import { Fragment } from "react";

export function ClozeText({ text, blankLabel }: { text: string; blankLabel: string }) {
  return <>{text.split(/(_{3,})/).map((part, index) => /^_{3,}$/.test(part)
    ? <svg key={index} data-cloze-blank role="img" aria-label={blankLabel} focusable="false"
        width="2.4em" height="0.85em" viewBox="0 0 100 24" preserveAspectRatio="none"
        style={{ display: "inline-block", verticalAlign: "baseline", marginInline: ".14em" }}>
        <line x1="0" y1="22" x2="100" y2="22" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
    : <Fragment key={index}>{part}</Fragment>)}</>;
}
