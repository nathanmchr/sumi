"use client";

import useSWR from "swr";
import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { session, vocabulary } from "@/lib/api";
import type { FuriganaDisplayMode, VocabularyItem } from "@/lib/types";
import { FuriganaText } from "@/components/furigana-text";
import { JlptLevelList } from "@/components/jlpt-level-list";
import { SearchBox } from "@/components/search-box";
import { useI18n } from "@/lib/i18n";
import { formatPowers } from "@/lib/format-text";

function VocabularyCard({ item, mode, helper, romaji }: { item: VocabularyItem; mode: FuriganaDisplayMode; helper: boolean; romaji: boolean }) {
  const segments = item.furigana_segments.length
    ? item.furigana_segments
    : [{ surface: item.japanese, reading: item.reading }];

  return (
    <article className="content-card">
      <h3 lang="ja">
        <FuriganaText segments={segments} mode={mode} helper={helper} />
      </h3>
      {romaji && item.romaji?.trim() ? <p className="muted" lang="ja-Latn">{item.romaji}</p> : null}
      <p className="content-card__translation">{formatPowers(item.translation)}</p>
      <Link
        href={`/study/vocabulary/${item.id}`}
        className="content-card__link"
        aria-label={`${item.japanese}: ${formatPowers(item.translation)}`}
      />
    </article>
  );
}

export default function VocabularyPage() {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const { data: currentSession } = useSWR("session", () => session());
  const furiganaMode = currentSession?.settings.furigana_display_mode ?? "always";
  const contentLocale = currentSession?.settings.content_locale ?? "en";

  return (
    <div className="stack">
      <header className="page-header">
        <div>
          <h1>{t("catalog.vocabulary")}</h1>
        </div>
        <Link className="button button--small" href="/study/vocabulary/homophones">{t("homophones.open")}</Link>
      </header>

      <div className="catalog-toolbar">
        <SearchBox value={query} onChange={setQuery} placeholder={t("catalog.searchVocabulary")} />
      </div>

      <JlptLevelList
        query={deferredQuery}
        cacheKey={`vocabulary-library-${contentLocale}`}
        loadItems={(level, searchQuery) => vocabulary(level, searchQuery, contentLocale)}
        itemLabel={t("catalog.word")}
        itemLabelPlural={t("catalog.words")}
        gridClassName="content-grid content-grid--vocabulary"
        renderItem={(item) => <VocabularyCard item={item} mode={furiganaMode} helper={currentSession?.settings.furigana_helper_enabled ?? false} romaji={currentSession?.settings.romaji_enabled ?? false} />}
      />
    </div>
  );
}
