"use client";

import { useEffect, useState, type CSSProperties } from "react";
import styles from "./completion-confetti.module.css";

const colors = ["var(--accent)", "var(--accent-2)", "var(--accent-3)", "var(--focus)"];
const pieces = Array.from({ length: 56 }, (_, index) => ({
  "--left": `${(index * 47) % 100}%`,
  "--drift": `${((index * 31) % 161) - 80}px`,
  "--delay": `${(index % 8) * 55}ms`,
  "--duration": `${2200 + (index % 5) * 160}ms`,
  "--rotation": `${(index % 2 ? 1 : -1) * (360 + (index % 4) * 180)}deg`,
  backgroundColor: colors[index % colors.length],
} as CSSProperties));

export function CompletionConfetti() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (preference.matches) return;
    setVisible(true);
    const finish = () => {
      setVisible(false);
      window.clearTimeout(timer);
      preference.removeEventListener("change", onPreferenceChange);
    };
    const onPreferenceChange = () => { if (preference.matches) finish(); };
    const timer = window.setTimeout(finish, 3300);
    preference.addEventListener("change", onPreferenceChange);
    return () => {
      window.clearTimeout(timer);
      preference.removeEventListener("change", onPreferenceChange);
    };
  }, []);

  if (!visible) return null;
  return <div className={styles.confetti} aria-hidden="true" data-completion-confetti="">
    {pieces.map((style, index) => <span key={index} className={styles.piece} style={style} />)}
  </div>;
}
