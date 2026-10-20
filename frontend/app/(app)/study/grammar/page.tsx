"use client";

import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { grammar } from "@/lib/api";
import { SearchBox } from "@/components/search-box";
import { JlptLevelList } from "@/components/jlpt-level-list";
import useSWR from "swr";
import { session } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { formatPowers } from "@/lib/format-text";

export default function GrammarPage() {
  const { t } = useI18n();
  const { data: currentSession } = useSWR("session", session);
  const contentLocale = currentSession?.settings.content_locale ?? "en";
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  return (
    <div className="stack">
      <header className="page-header">
        <div>
          <h1>{t("catalog.grammar")}</h1>
        </div>
      </header>
      <div className="catalog-toolbar">
        <SearchBox value={query} onChange={setQuery} placeholder={t("catalog.searchGrammar")} />
      </div>

      <JlptLevelList
        query={deferredQuery}
        cacheKey={`grammar-library-${contentLocale}`}
        loadItems={(level, searchQuery) => grammar(level, searchQuery, contentLocale)}
        itemLabel={t("catalog.point")}
        itemLabelPlural={t("catalog.points")}
        gridClassName="content-grid content-grid--grammar"
        renderItem={(item) => (
            <Link key={item.id} href={`/study/grammar/${item.id}`} className="grammar-card">
              <strong lang="ja">{item.title}</strong>
              <p lang={item.translation_locale}>{formatPowers(item.explanation)}</p>
            </Link>
        )}
      />
    </div>
  );
}
