"use client";

import { useSyncExternalStore } from "react";
import { useI18n } from "@/lib/i18n";

const changeEvent = "study-audio-change";
const fallback = new Map<string, boolean>();
function subscribe(listener: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key === null) fallback.clear();
    else fallback.delete(event.key);
    listener();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(changeEvent, listener);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(changeEvent, listener);
  };
}
const serverSnapshot = () => false;

export function useStudyAudio(userId?: string) {
  const key = userId ? `mirai:study-audio:${userId}` : null;
  const enabled = useSyncExternalStore(subscribe, () => {
    if (!key) return false;
    if (fallback.has(key)) return fallback.get(key)!;
    try { return window.localStorage.getItem(key) !== "off"; }
    catch { return fallback.get(key) ?? true; }
  }, serverSnapshot);
  function setEnabled(value: boolean) {
    if (!key) return;
    fallback.set(key, value);
    try { window.localStorage.setItem(key, value ? "on" : "off"); } catch { /* Private storage may be unavailable. */ }
    window.dispatchEvent(new Event(changeEvent));
  }
  return { enabled, setEnabled };
}

export function StudyAudioToggle({ enabled, onChange }: { enabled: boolean; onChange: (value: boolean) => void }) {
  const { locale } = useI18n();
  const label = locale === "fr" ? "Audio automatique" : "Automatic audio";
  const hint = locale === "fr" ? (enabled ? "Désactiver l'audio automatique" : "Activer l'audio automatique")
    : (enabled ? "Disable automatic audio" : "Enable automatic audio");
  return <><button type="button" className="study-audio-toggle" aria-label={label} title={hint}
    aria-pressed={enabled} onClick={() => onChange(!enabled)}>
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 9v6h4l5 4V5L8 9H4Z" />
      {enabled ? <><path d="M16 9a5 5 0 0 1 0 6" /><path d="M19 6a9 9 0 0 1 0 12" /></> : <path d="m3 3 18 18" />}
    </svg>
  </button>
    <style jsx>{`
      .study-audio-toggle { appearance: none; -webkit-appearance: none; display: inline-grid; place-items: center; width: 44px; min-width: 44px; height: 44px; padding: 0; border: 0; border-radius: 50%; background: transparent; box-shadow: none; color: var(--muted); cursor: pointer; flex-shrink: 0; }
      .study-audio-toggle svg { display: block; width: 22px; height: 22px; flex: none; }
      .study-audio-toggle[aria-pressed="true"] { color: var(--focus); }
      .study-audio-toggle:hover { background: var(--tint); }
      .study-audio-toggle:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
    `}</style>
  </>;
}
