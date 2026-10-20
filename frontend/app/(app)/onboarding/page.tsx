"use client";

import { useRouter } from "next/navigation";
import useSWR from "swr";
import { useEffect, useState, useTransition } from "react";
import { session, updateSettings } from "@/lib/api";
import { LevelRangeSelector } from "@/components/level-range-selector";
import { PrimaryButton } from "@/components/form";
import { Section } from "@/components/stat-card";
import type { FuriganaDisplayMode, UserSettings } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

export default function OnboardingPage() {
  const router = useRouter();
  const { setLocale, t } = useI18n();
  const { data, mutate } = useSWR("session", session, { revalidateOnFocus: false });
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    if (data?.settings && !settings) {
      setSettings(data.settings);
    }
  }, [data, settings]);

  if (!settings) {
    return <p className="muted">{t("common.loading")}</p>;
  }

  return (
    <div className="stack">
      <header className="page-header">
        <div>
          <h1>{t("onboarding.title")}</h1>
          <p className="muted">{t("onboarding.intro")}</p>
        </div>
      </header>

      <Section title={t("settings.languages")} description={t("settings.languagesDescription")}>
        <div className="settings-grid settings-grid--languages">
          <label className="field">
            <span className="field__label">{t("settings.interfaceLanguage")}</span>
            <select className="input" value={settings.interface_locale} onChange={(event) => {
              const value = event.target.value as UserSettings["interface_locale"];
              setSettings({ ...settings, interface_locale: value });
              setLocale(value);
            }}>
              <option value="en">{t("settings.english")}</option>
              <option value="fr">{t("settings.french")}</option>
            </select>
          </label>
          <label className="field">
            <span className="field__label">{t("settings.contentLanguage")}</span>
            <select className="input" value={settings.content_locale} onChange={(event) => setSettings({ ...settings, content_locale: event.target.value as UserSettings["content_locale"] })}>
              <option value="en">{t("settings.english")}</option>
              <option value="fr">{t("settings.french")}</option>
            </select>
          </label>
        </div>
      </Section>

      <Section title={t("settings.targets")} description={t("onboarding.targetsDescription")}>
        <div className="settings-grid">
          <LevelRangeSelector label={t("nav.vocabulary")} minimum={settings.vocabulary_min_level_code ?? settings.vocabulary_level_code} maximum={settings.vocabulary_level_code} onChange={(minimum, maximum) => setSettings({ ...settings, vocabulary_min_level_code: minimum, vocabulary_level_code: maximum })} />
          <LevelRangeSelector label={t("nav.grammar")} minimum={settings.grammar_min_level_code ?? settings.grammar_level_code} maximum={settings.grammar_level_code} onChange={(minimum, maximum) => setSettings({ ...settings, grammar_min_level_code: minimum, grammar_level_code: maximum })} />
          <LevelRangeSelector label={t("nav.kanji")} minimum={settings.kanji_min_level_code ?? settings.kanji_level_code} maximum={settings.kanji_level_code} onChange={(minimum, maximum) => setSettings({ ...settings, kanji_min_level_code: minimum, kanji_level_code: maximum })} />
        </div>
      </Section>

      <Section title={t("onboarding.readingAid")} description={t("onboarding.readingAidDescription")}>
        <div className="segmented">
          {(["always", "hover", "hidden"] as FuriganaDisplayMode[]).map((mode) => (
            <button key={mode} type="button" className={`segmented__item ${settings.furigana_display_mode === mode ? "is-active" : ""}`} onClick={() => setSettings({ ...settings, furigana_display_mode: mode })}>
              {t(`settings.${mode}` as "settings.always" | "settings.hover" | "settings.hidden")}
            </button>
          ))}
        </div>
      </Section>

      <Section title={t("onboarding.dailyPace")} description={t("onboarding.dailyPaceDescription")}>
        <label className="field">
          <span className="field__label">{t("onboarding.minutes")}</span>
          <input
            className="input"
            type="number"
            min={5}
            max={240}
            value={settings.daily_goal_minutes}
            onChange={(event) => setSettings({ ...settings, daily_goal_minutes: Number(event.target.value) })}
          />
        </label>
      </Section>

      <div className="actions-row">
        <PrimaryButton
          disabled={pending}
          onClick={() =>
            startTransition(async () => {
              await updateSettings(settings);
              await mutate();
              router.push("/dashboard");
            })
          }
        >
          {pending ? t("common.saving") : t("onboarding.start")}
        </PrimaryButton>
      </div>
    </div>
  );
}
