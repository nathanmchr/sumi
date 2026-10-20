"use client";

import useSWR from "swr";
import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { search, session } from "@/lib/api";
import { SearchBox } from "@/components/search-box";
import { Section } from "@/components/stat-card";
import { useI18n } from "@/lib/i18n";
import { formatPowers } from "@/lib/format-text";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const { t } = useI18n();
  const { data: currentSession } = useSWR("session", session);
  const contentLocale = currentSession?.settings.content_locale ?? "en";
  const deferredQuery = useDeferredValue(query);
  const { data: results } = useSWR(deferredQuery.trim().length > 0 ? ["search", deferredQuery, contentLocale] : null, () => search(deferredQuery, contentLocale));

  return (
    <div className="stack">
      <header className="page-header">
        <div>
          <h1>{t("search.title")}</h1>
        </div>
      </header>
      <div className="catalog-toolbar">
        <SearchBox value={query} onChange={setQuery} placeholder={t("search.placeholder")} />
      </div>
      <Section title={t("search.results")} description={t("search.resultsDescription")}>
        <div className="result-list">
          {(results ?? []).map((result) => (
            <Link key={`${result.content_type}-${result.id}`} href={result.url} className="result-row">
              <div>
                <strong>{result.title}</strong>
                <p>{formatPowers(result.subtitle)}</p>
              </div>
              <span>{result.jlpt_level_code}</span>
            </Link>
          ))}
        </div>
      </Section>
    </div>
  );
}
