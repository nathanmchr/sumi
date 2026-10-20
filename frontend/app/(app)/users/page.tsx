"use client";

import useSWR from "swr";
import { useEffect, useState, useTransition } from "react";
import { session, updateProfile } from "@/lib/api";
import { PrimaryButton, TextField } from "@/components/form";
import { Section } from "@/components/stat-card";
import { useI18n } from "@/lib/i18n";

export default function UserPage() {
  const { t } = useI18n();
  const { data, mutate } = useSWR("session", session);
  const [fullName, setFullName] = useState("");
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (data?.user.full_name && !fullName) {
      setFullName(data.user.full_name);
    }
  }, [data, fullName]);

  if (!data) {
    return <p className="muted">{t("profile.loading")}</p>;
  }

  return (
    <div className="stack">
      <header className="page-header">
        <div>
          <h1>{t("profile.title")}</h1>
          <p className="muted">{t("profile.intro")}</p>
        </div>
      </header>

      <Section title={t("profile.account")} description={t("profile.accountDescription")}>
        <div className="profile-card">
          <div className="profile-card__line">
            <span>{t("common.email")}</span>
            <strong>{data.user.email}</strong>
          </div>
          <div className="profile-card__line">
            <span>{t("profile.admin")}</span>
            <strong>{data.user.is_admin ? t("common.yes") : t("common.no")}</strong>
          </div>
        </div>
      </Section>

      <Section title={t("profile.displayName")} description={t("profile.displayNameDescription")}>
        <div className="stack">
          <TextField label={t("common.fullName")} value={fullName} onChange={setFullName} />
          {message ? <p className="muted">{message}</p> : null}
          <PrimaryButton
            disabled={pending || !fullName.trim() || fullName === data.user.full_name}
            onClick={() =>
              startTransition(async () => {
                await updateProfile(fullName.trim());
                await mutate();
                setMessage(t("profile.updated"));
              })
            }
          >
            {pending ? t("common.saving") : t("profile.save")}
          </PrimaryButton>
        </div>
      </Section>
    </div>
  );
}
