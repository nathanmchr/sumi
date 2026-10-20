"use client";

import Link from "next/link";
import useSWR from "swr";
import { dueItems, session } from "@/lib/api";
import { Section } from "@/components/stat-card";
import { useI18n } from "@/lib/i18n";

export default function ReviewPage() {
  const { t } = useI18n();
  const { data: currentSession } = useSWR("session", session);
  const contentLocale = currentSession?.settings.content_locale ?? "en";
  const { data, error } = useSWR(currentSession ? ["due-items", contentLocale] : null, () => dueItems(contentLocale));
  return <div className="stack">
    <header className="page-header">
      <div><h1>{t("review.title")}</h1><p className="muted">{t("quiz.intro")}</p></div>
      <Link className="button button--accent" href="/study/session?due=1">{t("review.start")}</Link>
    </header>
    <Section title={t("review.queue")} description={t("review.ready", { count: data?.length ?? 0 })}>
      {!data && !error && <p role="status">{t("common.loading")}</p>}
      {error && <p role="alert">{t("quiz.error")}</p>}
      <div className="queue-list">{data?.map(item =>
        <Link key={`${item.content_type}-${item.content_id}`} className="queue-row queue-row--button"
          href={`/study/session?category=${item.content_type}&item=${item.content_id}&due=1`}>
          <div><strong lang="ja">{item.title}</strong><p>{t(`nav.${item.content_type}`)} · {t(`status.${item.status}`)}</p></div>
          <span>{item.jlpt_level_code}</span>
        </Link>
      )}</div>
      {data?.length === 0 && <p className="muted">{t("review.empty")}</p>}
    </Section>
  </div>;
}
