"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import Link from "next/link";
import { useSWRConfig } from "swr";
import { ApiError, login } from "@/lib/api";
import { PrimaryButton, TextField } from "@/components/form";
import { useI18n } from "@/lib/i18n";

export default function LoginPage() {
  const router = useRouter();
  const { t } = useI18n();
  const { mutate } = useSWRConfig();
  const [pending, startTransition] = useTransition();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="auth-bento">
      <section className="auth-card auth-card--form">
        <h1>{t("auth.signIn")}</h1>
        <p className="muted">{t("auth.loginIntro")}</p>
        <form
          className="stack stack--auth"
          onSubmit={(event) => {
            event.preventDefault();
            setError(null);
            startTransition(async () => {
              try {
                const authenticated = await login(email, password);
                await mutate((key) => key !== "session", undefined, { revalidate: false });
                await mutate("session", authenticated, { revalidate: false });
                router.replace("/dashboard");
              } catch (err) {
                setError(err instanceof ApiError && err.status !== 0 ? err.message : t("auth.unavailable"));
              }
            });
          }}
        >
          <TextField label={t("common.email")} value={email} onChange={setEmail} type="email" />
          <TextField label={t("common.password")} value={password} onChange={setPassword} type="password" />
          {error ? <p className="error-text" role="alert">{error}</p> : null}
          <PrimaryButton type="submit" disabled={pending}>
            {pending ? t("auth.signingIn") : t("auth.signIn")}
          </PrimaryButton>
        </form>
        <p className="auth-footer">
          {t("auth.noAccount")} <Link href="/register">{t("auth.createOne")}</Link>
        </p>
      </section>

      <aside className="auth-side">
        <div className="auth-side__glyph">復</div>
        <strong>{t("auth.recallTitle")}</strong>
        <p>{t("auth.recallText")}</p>
      </aside>
    </div>
  );
}
