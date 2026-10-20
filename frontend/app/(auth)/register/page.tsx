"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import Link from "next/link";
import { useSWRConfig } from "swr";
import { ApiError, register } from "@/lib/api";
import { PrimaryButton, TextField } from "@/components/form";
import { useI18n } from "@/lib/i18n";

export default function RegisterPage() {
  const router = useRouter();
  const { t } = useI18n();
  const { mutate } = useSWRConfig();
  const [pending, startTransition] = useTransition();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="auth-bento">
      <section className="auth-card auth-card--form">
        <h1>{t("auth.registerTitle")}</h1>
        <p className="muted">{t("auth.registerIntro")}</p>
        <form
          className="stack stack--auth"
          onSubmit={(event) => {
            event.preventDefault();
            setError(null);
            startTransition(async () => {
              try {
                const authenticated = await register(email, fullName, password);
                await mutate((key) => key !== "session", undefined, { revalidate: false });
                await mutate("session", authenticated, { revalidate: false });
                router.replace("/onboarding");
              } catch (err) {
                setError(err instanceof ApiError && err.status !== 0 ? err.message : t("auth.unavailable"));
              }
            });
          }}
        >
          <TextField label={t("common.fullName")} value={fullName} onChange={setFullName} />
          <TextField label={t("common.email")} value={email} onChange={setEmail} type="email" />
          <TextField label={t("common.password")} value={password} onChange={setPassword} type="password" />
          {error ? <p className="error-text" role="alert">{error}</p> : null}
          <PrimaryButton type="submit" disabled={pending}>
            {pending ? t("auth.creating") : t("auth.createAccount")}
          </PrimaryButton>
        </form>
        <p className="auth-footer">
          {t("auth.hasAccount")} <Link href="/login">{t("auth.signIn")}</Link>
        </p>
      </section>

      <aside className="auth-side">
        <div className="auth-side__glyph">道</div>
        <strong>{t("auth.trackTitle")}</strong>
        <p>{t("auth.trackText")}</p>
      </aside>
    </div>
  );
}
