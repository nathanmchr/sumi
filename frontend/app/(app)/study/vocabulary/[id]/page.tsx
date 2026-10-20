"use client";

import useSWR from "swr";
import Link from "next/link";
import { useParams } from "next/navigation";
import { session } from "@/lib/api";
import { AudioButton } from "@/components/audio-button";
import { FuriganaText } from "@/components/furigana-text";
import { StudyDetailHeader } from "@/components/study-detail-header";
import type { VocabularyItem } from "@/lib/types";
import type { Locale } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import { formatPowers } from "@/lib/format-text";

async function fetchVocabulary(id: string, locale: Locale): Promise<VocabularyItem> {
  const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"}/content/vocabulary/${id}?locale=${locale}`, { credentials: "include" });
  if (!response.ok) throw new Error("Vocabulary item not found");
  return response.json();
}

export default function VocabularyDetailPage() {
  const params = useParams<{ id: string }>();
  const { data: currentSession } = useSWR("session", () => session());
  const { t } = useI18n();
  const contentLocale = currentSession?.settings.content_locale ?? "en";
  const { data: item } = useSWR(["vocabulary-detail", params.id, contentLocale], () => fetchVocabulary(params.id, contentLocale));
  const furiganaMode = currentSession?.settings.furigana_display_mode ?? "always";
  const hasExamples = Boolean(item?.example_sentences.length);
  const hasLinkedKanji = Boolean(item?.kanji_links.length);

  return (
    <div className="stack">
      <StudyDetailHeader category="vocabulary" item={item} />

      {item ? (
        <article className="detail-card">
          <div className="detail-card__surface">
            <div className="detail-card__heading">
              <h2 lang="ja"><FuriganaText segments={item.furigana_segments.length ? item.furigana_segments : [{ surface: item.japanese, reading: item.reading }]} mode={furiganaMode} helper={currentSession?.settings.furigana_helper_enabled} /></h2>
              {item.audio_url ? <AudioButton src={item.audio_url} label={item.japanese} /> : null}
            </div>
            {currentSession?.settings.romaji_enabled && item.romaji?.trim() ? (
              <p className="detail-card__reading" lang="ja-Latn">{item.romaji}</p>
            ) : null}
            <p className="detail-card__translation">{formatPowers(item.translation)}</p>
            {item.notes ? <p className="muted">{formatPowers(item.notes)}</p> : null}
          </div>

          {hasExamples || hasLinkedKanji ? (
            <div className="detail-grid">
              {hasExamples ? (
                <div className="detail-card__block">
                  <h3>{t("detail.examples")}</h3>
                  {item.example_sentences.map((example) => (
                    <div key={example.id} className="example-block">
                      <FuriganaText segments={example.furigana_segments} mode={furiganaMode} helper={currentSession?.settings.furigana_helper_enabled} />
                      <p>{formatPowers(example.translation)}</p>
                    </div>
                  ))}
                </div>
              ) : null}
              {hasLinkedKanji ? (
                <div className="detail-card__block">
                  <h3>{t("detail.linkedKanji")}</h3>
                  <div className="stack stack--compact">
                    {item.kanji_links.map((link) => (
                      <Link key={link.kanji_id} href={`/study/kanji/${link.kanji_id}`} className="linked-row linked-row--kanji">
                        <span className="linked-row__identity">
                          <strong className="linked-row__kanji">{link.kanji_character}</strong>
                          <span className="tag">JLPT {link.jlpt_level_code}</span>
                        </span>
                        {link.meanings.length > 0 ? <span className="linked-row__meaning">{formatPowers(link.meanings.join(" / "))}</span> : null}
                      </Link>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="actions-row">
            <Link className="button button--accent" href={`/study/session?category=vocabulary&item=${item.id}`}>{t("quiz.practice")}</Link>
            <Link className="button button--quiet" href={`/study/vocabulary/homophones?q=${encodeURIComponent(item.reading)}`}>{t("homophones.open")}</Link>
          </div>
        </article>
      ) : null}
    </div>
  );
}
