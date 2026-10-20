"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, login, type AuthSession } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { User } from "@/lib/types";

export function SessionReconnect({ user, onConnected, onDismiss }: {
  user: User; onConnected: (session: AuthSession) => Promise<void>; onDismiss: () => void;
}) {
  const { locale } = useI18n();
  const fr = locale === "fr";
  const dialog = useRef<HTMLDialogElement>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  return <dialog ref={dialog} aria-labelledby="reconnect-title" aria-describedby="reconnect-description"
    onCancel={(event) => { event.preventDefault(); if (!busy) onDismiss(); }}>
    <form onSubmit={async (event) => {
      event.preventDefault();
      if (busy) return;
      setBusy(true); setError("");
      try {
        const authenticated = await login(user.email, password);
        if (authenticated.user.id !== user.id) {
          // Never resume an old account's unsaved actions under a new identity.
          window.location.assign("/dashboard");
          return;
        }
        await onConnected(authenticated);
      } catch (failure) {
        setError(failure instanceof ApiError && failure.status === 401
          ? (fr ? "Mot de passe incorrect." : "Incorrect password.")
          : (fr ? "Connexion indisponible. Réessaie dans un instant." : "Connection unavailable. Please try again shortly."));
      } finally { setBusy(false); }
    }}>
      <h2 id="reconnect-title">{fr ? "Reconnecte-toi pour continuer" : "Sign in again to continue"}</h2>
      <p id="reconnect-description">{fr
        ? "Ta progression enregistrée est conservée. Ta page et ta saisie restent ouvertes."
        : "Your saved progress is safe. Your page and current input stay open."}</p>
      <label>{fr ? "Adresse e-mail" : "Email"}<input type="email" autoComplete="username" value={user.email} readOnly /></label>
      <label>{fr ? "Mot de passe" : "Password"}<input type="password" autoComplete="current-password" autoFocus required
        value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy} /></label>
      {error ? <p className="error-text" role="alert">{error}</p> : null}
      <div className="actions">
        <button type="button" className="button" disabled={busy} onClick={onDismiss}>{fr ? "Plus tard" : "Later"}</button>
        <button type="submit" className="button button--accent" disabled={busy}>{busy
          ? (fr ? "Connexion…" : "Signing in…") : (fr ? "Se reconnecter" : "Sign in again")}</button>
      </div>
    </form>
    <style jsx>{`
      dialog { width: min(460px, calc(100% - 32px)); max-height: calc(100dvh - 32px); padding: 28px; border: 1px solid var(--line); border-radius: 24px; background: var(--paper); color: var(--text); box-shadow: var(--shadow-soft); }
      dialog::backdrop { background: rgb(20 30 35 / .4); }
      h2 { margin: 0 0 12px; font-size: 1.5rem; line-height: 1.3; }
      p { margin: 0 0 20px; line-height: 1.5; color: var(--muted); }
      label { display: grid; gap: 8px; margin-block: 16px; font-size: .85rem; }
      input { min-width: 0; width: 100%; padding: 12px; border: 1px solid var(--line); border-radius: 12px; background: var(--bg); color: var(--text); font: inherit; }
      input:read-only { color: var(--muted); }
      .actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 12px; margin-top: 24px; }
    `}</style>
  </dialog>;
}
