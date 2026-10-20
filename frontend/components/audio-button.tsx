"use client";

import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { resolveAudioSource } from "@/lib/audio";

type Props = {
  src: string;
  label: string;
  autoPlay?: boolean;
};

export function AudioButton({ src, label, autoPlay = false }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [failure, setFailure] = useState<"blocked" | "unavailable" | null>(null);
  const { t, locale } = useI18n();
  const actionLabel = `${t(isPlaying ? "detail.pauseAudio" : "detail.playAudio")} — ${label}`;

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    let cancelled = false;
    setFailure(null);
    // Defer the attempt so a Strict Mode cleanup cannot start a second playback.
    const timer = window.setTimeout(() => {
      if (autoPlay && !document.hidden) {
        void audio.play().catch(error => {
          if (!cancelled) setFailure(error?.name === "NotAllowedError" ? "blocked" : "unavailable");
        });
      }
    }, 0);
    const pauseHidden = () => { if (document.hidden) audio.pause(); };
    document.addEventListener("visibilitychange", pauseHidden);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", pauseHidden);
      audio.pause();
    };
  }, [src, autoPlay]);

  const toggleAudio = async () => {
    const audio = audioRef.current;
    if (!audio) return;

    if (!audio.paused) {
      audio.pause();
      return;
    }

    try {
      if (audio.ended) audio.currentTime = 0;
      await audio.play();
      setFailure(null);
    } catch {
      setIsPlaying(false);
      setFailure("unavailable");
    }
  };

  return (
    <>
      <button
        type="button"
        className={`audio-button${isPlaying ? " is-playing" : ""}`}
        aria-label={actionLabel}
        aria-pressed={isPlaying}
        title={actionLabel}
        onClick={toggleAudio}
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none">
          <path d="M5 9.5v5h3.25L13 18V6L8.25 9.5H5Z" />
          <path className="audio-button__wave audio-button__wave--near" d="M16 9a4.25 4.25 0 0 1 0 6" />
          <path className="audio-button__wave audio-button__wave--far" d="M18.5 6.5a7.8 7.8 0 0 1 0 11" />
        </svg>
      </button>
      <audio
        ref={audioRef}
        className="audio-button__media"
        src={resolveAudioSource(src)}
        preload="none"
        onPlay={() => { setIsPlaying(true); setFailure(null); }}
        onPause={() => setIsPlaying(false)}
        onEnded={() => setIsPlaying(false)}
      />
      {failure && <span className="audio-button__notice" role="status">{failure === "blocked"
        ? locale === "fr" ? "Lecture automatique bloquée. Appuie sur écouter." : "Autoplay blocked. Press listen."
        : locale === "fr" ? "Audio indisponible. Réessaie avec le bouton écouter." : "Audio unavailable. Try the listen button again."}</span>}
    </>
  );
}
