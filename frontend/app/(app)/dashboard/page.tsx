"use client";

import useSWR from "swr";
import Link from "next/link";
import { dashboard, dueItems, session, sessionRecommendation } from "@/lib/api";
import { contentHref } from "@/lib/content";
import { ProgressBar } from "@/components/progress-bar";
import { StatCard } from "@/components/stat-card";
import { useI18n } from "@/lib/i18n";
import { formatLevelRange } from "@/lib/jlpt";
import { formatPowers } from "@/lib/format-text";

export default function DashboardPage() {
  const { locale, t } = useI18n();
  const { data: currentSession } = useSWR("session", session);
  const contentLocale = currentSession?.settings.content_locale ?? "en";
  const { data: stats } = useSWR("dashboard", () => dashboard());
  const { data: due, error: dueError } = useSWR(["due", contentLocale], () => dueItems(contentLocale));
  const { data: recommendation } = useSWR("recommendation", () => sessionRecommendation());

  const totalProgress = stats ? (stats.progression_by_category.vocabulary + stats.progression_by_category.grammar + stats.progression_by_category.kanji) / 3 : 0;
  const trackLevels = {
    vocabulary: formatLevelRange(currentSession?.settings.vocabulary_min_level_code, currentSession?.settings.vocabulary_level_code),
    grammar: formatLevelRange(currentSession?.settings.grammar_min_level_code, currentSession?.settings.grammar_level_code),
    kanji: formatLevelRange(currentSession?.settings.kanji_min_level_code, currentSession?.settings.kanji_level_code),
  };

  return (
    <div className="dashboard-page dashboard-bento">
      <section className="bento-tile bento-tile--hero">
        <div className="dashboard-hero__copy">
          <p className="eyebrow">{t("dashboard.today")}</p>
          <h1>{t("dashboard.title")}</h1>
          <p>{t("dashboard.intro")}</p>
          <div className="dashboard-hero__actions">
            <Link className="button button--accent" href="/study/session">{t("dashboard.start")}<span aria-hidden="true">→</span></Link>
            <Link className="button button--quiet" href="/review">{t("dashboard.reviewQueue")}</Link>
          </div>
        </div>
      </section>

      <section className="bento-tile bento-tile--session">
        <p className="eyebrow">{t("dashboard.recommended")}</p>
        <strong>{recommendation?.minutes ?? stats?.estimated_session_minutes ?? 15}<span className="session-unit">min</span></strong>
        <span>{locale === "fr" ? t("dashboard.defaultRecommendation") : recommendation?.rationale ?? stats?.recommendation ?? t("dashboard.defaultRecommendation")}</span>
        <div className="tag-row">
          {(recommendation?.focus ?? ["vocabulary", "kanji"]).map((focus) => (
            <span key={focus} className="tag">{t(focus === "vocabulary" ? "nav.vocabulary" : focus === "grammar" ? "nav.grammar" : "nav.kanji")}</span>
          ))}
        </div>
      </section>

      <section className="bento-tile bento-tile--metrics dashboard-metrics" aria-label={t("dashboard.learned")}>
        <StatCard label={t("dashboard.learned")} value={stats?.learned_items ?? "—"} hint={t("dashboard.learnedHint")} tone="accent" />
        <StatCard label={t("dashboard.due")} value={stats?.due_reviews ?? "—"} hint={t("dashboard.dueHint")} />
        <StatCard label={t("dashboard.streak")} value={`${stats?.streak_days ?? "—"} ${t("dashboard.days")}`} hint={t("dashboard.streakHint")} tone="success" />
      </section>

      <section className="bento-tile bento-tile--progress">
        <div className="bento-tile__header">
          <div>
            <h2>{t("dashboard.masteryMap")}</h2>
          </div>
        </div>
        <div className="progress-showcase">
          <div className="progress-showcase__score">
            <span>{stats ? `${Math.round(totalProgress)}%` : "—"}</span>
            <p>{t("dashboard.averageMastery")}</p>
          </div>
          <div className="progress-showcase__bar">
            <ProgressBar value={totalProgress} showLabel={false} label={t("dashboard.averageMastery")} />
          </div>
        </div>
        <div className="category-bars category-bars--dashboard">
          {(["vocabulary", "grammar", "kanji"] as const).map((key) => (
            <Link key={key} href={`/study/${key}`} className="category-row">
              <div className="category-row__head">
                <span className="category-row__identity">
                  <span>{t(key === "vocabulary" ? "nav.vocabulary" : key === "grammar" ? "nav.grammar" : "nav.kanji")}</span>
                  <span className="category-row__level">{trackLevels[key] ?? "—"}</span>
                </span>
                <strong>{stats ? `${Math.round(stats.progression_by_category?.[key] ?? 0)}%` : "—"}<span className="category-row__arrow" aria-hidden="true">↗</span></strong>
              </div>
              <ProgressBar value={stats?.progression_by_category?.[key] ?? 0} showLabel={false} label={t(key === "vocabulary" ? "nav.vocabulary" : key === "grammar" ? "nav.grammar" : "nav.kanji")} />
            </Link>
          ))}
        </div>
      </section>

      <section className="bento-tile bento-tile--due">
        <div className="bento-tile__header">
          <div>
            <h2>{t("dashboard.recallQueue")}</h2>
          </div>
          <Link href="/review" className="bento-pill">{t("common.open")}<span aria-hidden="true">↗</span></Link>
        </div>
        <div className="queue-list queue-list--compact">
          {(due ?? []).slice(0, 5).map((item) => (
            <Link key={`${item.content_type}-${item.content_id}`} href={contentHref(item.content_type, item.content_id)} className="queue-row">
              <div>
                <strong>{item.title}</strong>
                <p>{formatPowers(item.subtitle)}</p>
              </div>
              <span>{item.jlpt_level_code}</span>
            </Link>
          ))}
        </div>
        {dueError ? <p className="muted">{t("catalog.loadError")}</p> : !due ? <p className="muted">{t("catalog.loading")}</p> : due.length === 0 ? (
          <div className="queue-empty">
            <span className="queue-empty__mark" aria-hidden="true">✓</span>
            <p>{t("dashboard.emptyQueue")}</p>
            <Link className="button button--small" href="/study/vocabulary">{t("nav.vocabulary")}<span aria-hidden="true">→</span></Link>
          </div>
        ) : null}
      </section>

      <section className="bento-tile bento-tile--note">
        <strong>{t("dashboard.noteTitle")}</strong>
        <p>{t("dashboard.noteText")}</p>
      </section>
    </div>
  );
}
