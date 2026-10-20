"use client";

import useSWR, { useSWRConfig } from "swr";
import { useEffect, useState } from "react";
import { session, updateSettings } from "@/lib/api";
import { PrimaryButton } from "@/components/form";
import { Section } from "@/components/stat-card";
import { LevelRangeSelector } from "@/components/level-range-selector";
import { FuriganaText } from "@/components/furigana-text";
import type { FuriganaDisplayMode, FuriganaSegment, Locale, UserSettings } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

const sunday: FuriganaSegment[] = [{ surface: "日", reading: "にち" }, { surface: "曜", reading: "よう" }, { surface: "日", reading: "び" }];
const today: FuriganaSegment[] = [{ surface: "今日", reading: "きょう" }];
const mother: FuriganaSegment[] = [{ surface: "お" }, { surface: "母", reading: "かあ" }, { surface: "さん" }];
const modes: FuriganaDisplayMode[] = ["always", "hover", "hidden"];
const categories = ["vocabulary", "grammar", "kanji"] as const;

function LanguageChoice({ name, label, value, onChange }: { name: string; label: string; value: Locale; onChange: (value: Locale) => void }) {
  return (
    <fieldset className="settings-language">
      <legend className="field__label">{label}</legend>
      <div className="settings-language__choices">
        {(["fr", "en"] as const).map((language) => (
          <label className="settings-choice settings-choice--language" key={language}>
            <input type="radio" name={name} value={language} checked={value === language} onChange={() => onChange(language)} />
            <span className="settings-choice__flag" aria-hidden="true">{language === "fr" ? "🇫🇷" : "🇬🇧"}</span>
            <strong lang={language}>{language === "fr" ? "Français" : "English"}</strong>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export default function SettingsPage() {
  const { data, mutate } = useSWR("session", session);
  const { mutate: refreshLearning } = useSWRConfig();
  const { setLocale, t } = useI18n();
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<"saved" | "error" | null>(null);

  useEffect(() => {
    if (data?.settings) setSettings((current) => current ?? { ...data.settings,
      vocabulary_min_level_code: data.settings.vocabulary_min_level_code ?? data.settings.vocabulary_level_code,
      grammar_min_level_code: data.settings.grammar_min_level_code ?? data.settings.grammar_level_code,
      kanji_min_level_code: data.settings.kanji_min_level_code ?? data.settings.kanji_level_code,
      romaji_enabled: data.settings.romaji_enabled ?? false,
      furigana_helper_enabled: data.settings.furigana_display_mode !== "hidden" && (data.settings.furigana_helper_enabled ?? false) });
  }, [data?.settings]);

  if (!settings) return <p className="muted">{t("common.loading")}</p>;
  const dirty = !!data && (Object.keys(settings) as (keyof UserSettings)[]).some((key) => settings[key] !== data.settings[key]);
  function change(patch: Partial<UserSettings>) {
    setSettings((current) => current ? { ...current, ...patch } : current);
    setResult(null);
  }
  async function save() {
    if (!settings || pending) return;
    setPending(true);
    setResult(null);
    try {
      const updated = await updateSettings(settings);
      await mutate((current) => current ? { ...current, settings: updated } : current, { revalidate: false });
      setSettings(updated);
      setLocale(updated.interface_locale);
      setResult("saved");
      void refreshLearning((key) => typeof key === "string"
        ? ["dashboard", "recommendation"].includes(key)
        : Array.isArray(key) && key[0] === "due-items").catch(() => undefined);
    } catch {
      setResult("error");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="stack settings-page" onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <header className="page-header">
        <div><h1>{t("settings.title")}</h1><p className="muted">{t("settings.intro")}</p></div>
      </header>
      <fieldset className="settings-fields stack" disabled={pending}>
        <Section className="settings-panel settings-panel--languages" title={t("settings.languages")} description={t("settings.languagesDescription")}>
          <div className="settings-language-grid">
            <div className="settings-preference">
              <LanguageChoice name="interface-language" label={t("settings.interfaceLanguage")} value={settings.interface_locale} onChange={(interface_locale) => change({ interface_locale })} />
              <div className="settings-preview" lang={settings.interface_locale}>
                <span className="settings-preview__label">{t("settings.preview")}</span>
                <strong>{settings.interface_locale === "fr" ? "Votre prochaine séance" : "Your next study session"}</strong>
                <span className="settings-preview__action">{settings.interface_locale === "fr" ? "Commencer à apprendre" : "Start learning"}<span aria-hidden="true">↗</span></span>
              </div>
            </div>
            <div className="settings-preference">
              <LanguageChoice name="content-language" label={t("settings.contentLanguage")} value={settings.content_locale} onChange={(content_locale) => change({ content_locale })} />
              <div className="settings-preview">
                <span className="settings-preview__label">{t("settings.preview")}</span>
                <strong className="settings-preview__word" lang="ja">今日</strong>
                <span lang={settings.content_locale}>{settings.content_locale === "fr" ? "aujourd’hui" : "today"}</span>
              </div>
            </div>
          </div>
        </Section>

        <Section className="settings-panel settings-panel--reading" title={t("settings.furigana")} description={t("settings.furiganaDescription")}>
          <fieldset className="settings-modes">
            <legend className="sr-only">{t("settings.furigana")}</legend>
            {modes.map((mode) => (
              <label className="settings-choice settings-choice--mode" key={mode}>
                <input type="radio" name="furigana-mode" value={mode} checked={settings.furigana_display_mode === mode} onChange={() => change({ furigana_display_mode: mode, ...(mode === "hidden" ? { furigana_helper_enabled: false } : {}) })} />
                <strong>{t(`settings.${mode}`)}</strong>
                <span className="muted">{t(`settings.${mode}Hint`)}</span>
              </label>
            ))}
          </fieldset>
          <div className="settings-helper">
            <label className="settings-helper__control">
              <span><strong>{t("settings.romaji")}</strong><span className="muted">{t("settings.romajiDescription")}</span></span>
              <input type="checkbox" role="switch" aria-label={t("settings.romaji")} checked={settings.romaji_enabled} onChange={(event) => change({ romaji_enabled: event.target.checked })} />
            </label>
            <label className="settings-helper__control" data-disabled={settings.furigana_display_mode === "hidden"}>
              <span><strong>Furigana helper</strong><span className="muted">{t(settings.furigana_display_mode === "hidden" ? "settings.helperUnavailable" : "settings.helperDescription")}</span></span>
              <input type="checkbox" role="switch" disabled={settings.furigana_display_mode === "hidden"} checked={settings.furigana_helper_enabled} onChange={(event) => change({ furigana_helper_enabled: event.target.checked })} />
            </label>
            <div className="settings-preview settings-preview--helper" tabIndex={0} aria-label={t("settings.helperPreview")}>
              <span className="settings-preview__label">{t("settings.preview")} · {t(`settings.${settings.furigana_display_mode}`)}</span>
              <div className="settings-preview__examples" lang="ja">
                {[sunday, today, mother].map((segments, index) => <FuriganaText key={index} segments={segments} mode={settings.furigana_display_mode} helper={settings.furigana_helper_enabled} />)}
              </div>
              <span className="muted">{t("settings.helperHint")}</span>
            </div>
          </div>
        </Section>

        <Section className="settings-panel settings-panel--targets" title={t("settings.targets")} description={t("settings.targetsDescription")}>
          <div className="settings-targets">
            {categories.map((category) => {
              const maximumKey = `${category}_level_code` as const;
              const minimumKey = `${category}_min_level_code` as const;
              return (
                <div className="settings-target" key={category}>
                  <LevelRangeSelector label={t(`nav.${category}`)} minimum={settings[minimumKey]} maximum={settings[maximumKey]}
                    onChange={(minimum, maximum) => change({ [minimumKey]: minimum, [maximumKey]: maximum })} />
                </div>
              );
            })}
          </div>
        </Section>
      </fieldset>
      <footer className="settings-save">
        <div aria-live="polite">
          {result === "error" ? <p className="error-text" role="alert">{t("settings.saveError")}</p> : <p>{t(result === "saved" ? "settings.saved" : dirty ? "settings.unsaved" : "settings.saveHint")}</p>}
        </div>
        <PrimaryButton type="submit" disabled={pending || !dirty}>{t(pending ? "common.saving" : "settings.save")}</PrimaryButton>
      </footer>
    </form>
  );
}
