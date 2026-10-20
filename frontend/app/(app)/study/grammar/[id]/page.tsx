"use client";

import useSWR from "swr";
import Link from "next/link";
import { useParams } from "next/navigation";
import { session } from "@/lib/api";
import { StudyDetailHeader } from "@/components/study-detail-header";
import type { GrammarItem, Locale } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import { formatPowers } from "@/lib/format-text";

async function fetchGrammar(id: string, locale: Locale): Promise<GrammarItem> {
  const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"}/content/grammar/${id}?locale=${locale}`, { credentials: "include" });
  if (!response.ok) throw new Error("Grammar item not found");
  return response.json();
}

export default function GrammarDetailPage() {
  const params = useParams<{ id: string }>();
  const { data: currentSession } = useSWR("session", session);
  const { t } = useI18n();
  const contentLocale = currentSession?.settings.content_locale ?? "en";
  const { data: item } = useSWR(["grammar-detail", params.id, contentLocale], () => fetchGrammar(params.id, contentLocale));
  const examples = (item?.examples ?? []).filter((example) => example.text?.trim() || example.translation?.trim() || example.note?.trim());
  const counterExamples = (item?.counter_examples ?? []).filter((example) => example.title?.trim() || example.text?.trim() || example.explanation?.trim());
  const hasStructure = Boolean(item?.structure?.trim());
  const hasNuances = Boolean(item?.nuances?.trim());

  return (
    <div className="stack">
      <StudyDetailHeader category="grammar" item={item} />

      {item ? (
        <article className="detail-card">
          <div className="detail-card__surface">
            <h2>{item.title}</h2>
            <p>{formatPowers(item.explanation)}</p>
            {hasStructure || hasNuances ? (
              <div className="detail-grid">
                {hasStructure ? (
                  <div className="detail-card__block">
                    <h3>{t("detail.structure")}</h3>
                    <p>{formatPowers(item.structure)}</p>
                  </div>
                ) : null}
                {hasNuances ? (
                  <div className="detail-card__block">
                    <h3>{t("detail.nuances")}</h3>
                    <p>{formatPowers(item.nuances)}</p>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          {examples.length > 0 || counterExamples.length > 0 ? (
            <div className="detail-grid">
              {examples.length > 0 ? (
                <div className="detail-card__block">
                  <h3>{t("detail.examples")}</h3>
                  {examples.map((example, index) => (
                    <div key={index} className="example-block">
                      {example.text?.trim() ? <strong>{formatPowers(example.text)}</strong> : null}
                      {example.translation?.trim() ? <p>{formatPowers(example.translation)}</p> : null}
                      {example.note?.trim() ? <p className="muted">{formatPowers(example.note)}</p> : null}
                    </div>
                  ))}
                </div>
              ) : null}
              {counterExamples.length > 0 ? (
                <div className="detail-card__block">
                  <h3>{t("detail.counterExamples")}</h3>
                  {counterExamples.map((example, index) => (
                    <div key={index} className="example-block">
                      {example.title?.trim() ? <p>{formatPowers(example.title)}</p> : null}
                      {example.text?.trim() ? <strong>{formatPowers(example.text)}</strong> : null}
                      {example.explanation?.trim() ? <p>{formatPowers(example.explanation)}</p> : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          {item.exercisable ? (<Link className="button button--accent" href={`/study/session?category=grammar&item=${item.id}`}>{t("quiz.practice")}</Link>) : <p className="muted">{t("quiz.noExercise")}</p>}
        </article>
      ) : null}
    </div>
  );
}
