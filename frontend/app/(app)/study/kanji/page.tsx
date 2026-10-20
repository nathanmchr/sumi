"use client";

import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { kanji } from "@/lib/api";
import { SearchBox } from "@/components/search-box";
import { JlptLevelList } from "@/components/jlpt-level-list";
import useSWR from "swr";
import { session } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { formatPowers } from "@/lib/format-text";

export default function KanjiPage() {
  const { t } = useI18n();
  const { data: currentSession } = useSWR("session", session);
  const contentLocale = currentSession?.settings.content_locale ?? "en";
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  return (
    <div className="stack">
      <header className="page-header">
        <div>
          <h1>{t("catalog.kanji")}</h1>
        </div>
      </header>
      <div className="catalog-toolbar">
        <SearchBox value={query} onChange={setQuery} placeholder={t("catalog.searchKanji")} />
      </div>

      <JlptLevelList
        query={deferredQuery}
        cacheKey={`kanji-library-${contentLocale}`}
        loadItems={(level, searchQuery) => kanji(level, searchQuery, contentLocale)}
        itemLabel="kanji"
        itemLabelPlural="kanji"
        gridClassName="content-grid content-grid--kanji"
        renderItem={(item) => (
            <Link key={item.id} href={`/study/kanji/${item.id}`} className="kanji-card">
              <strong>{item.character}</strong>
              <p>{formatPowers(item.meanings.slice(0, 3).join(", "))}</p>
            </Link>
        )}
      />
    </div>
  );
}
