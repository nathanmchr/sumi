"use client";

import useSWR from "swr";
import Link from "next/link";
import { useParams } from "next/navigation";
import { session } from "@/lib/api";
import { AudioButton } from "@/components/audio-button";
import { KanjiStrokePlayer } from "@/components/kanji-stroke-player";
import { FuriganaText } from "@/components/furigana-text";
import { StudyDetailHeader } from "@/components/study-detail-header";
import type { KanjiItem, Locale } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import { formatPowers } from "@/lib/format-text";

async function fetchKanji(id: string, locale: Locale): Promise<KanjiItem> {
  const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"}/content/kanji/${id}?locale=${locale}`, { credentials: "include" });
  if (!response.ok) throw new Error("Kanji item not found");
  return response.json();
}

export default function KanjiDetailPage() {
  const params = useParams<{ id: string }>();
  const { data: currentSession } = useSWR("session", session);
  const { t } = useI18n();
  const contentLocale = currentSession?.settings.content_locale ?? "en";
  const furiganaMode = currentSession?.settings.furigana_display_mode ?? "always";
  const { data: item } = useSWR(["kanji-detail", params.id, contentLocale], () => fetchKanji(params.id, contentLocale));
  const hasLinkedVocabulary = Boolean(item?.linked_vocabulary.length);
  const hasReadings = Boolean(item && (item.onyomi.length > 0 || item.kunyomi.length > 0));

  return (
    <div className="stack">
      <StudyDetailHeader category="kanji" item={item} />

      {item ? (
        <article className="detail-card">
          <div className="detail-card__surface detail-card__surface--kanji detail-card__surface--strokes">
            <KanjiStrokePlayer key={item.id} character={item.character} level={item.jlpt_level_code} />
            <div className="kanji-detail-identity">
            {item.meanings.length > 0 ? <p>{formatPowers(item.meanings.join(" / "))}</p> : null}
            {hasReadings ? (
              <div className="tag-row">
                {item.onyomi.map((reading) => (
                  <span key={reading} className="tag">{reading}</span>
                ))}
                {item.kunyomi.map((reading) => (
                  <span key={reading} className="tag">{reading}</span>
                ))}
              </div>
            ) : null}
            {item.mnemonic ? <p className="muted">{formatPowers(item.mnemonic)}</p> : null}
            </div>
          </div>

          {hasLinkedVocabulary ? (
            <div className="detail-grid">
              <div className="detail-card__block">
                <h3>{t("detail.linkedVocabulary")}</h3>
                <div className="stack stack--compact">
                  {item.linked_vocabulary.map((entry) => (
                    <div key={entry.vocabulary_id} className="linked-row linked-row--audio">
                      <Link href={`/study/vocabulary/${entry.vocabulary_id}`} className="linked-row__content">
                        <span className="linked-row__identity">
                          <strong className="linked-row__japanese">
                            {entry.furigana_segments.length > 0 ? (
                              <FuriganaText segments={entry.furigana_segments} mode={furiganaMode} helper={currentSession?.settings.furigana_helper_enabled} />
                            ) : entry.vocabulary_japanese}
                          </strong>
                          <span className="tag">JLPT {entry.jlpt_level_code}</span>
                        </span>
                        <span className="linked-row__meaning">{formatPowers(entry.translation)}</span>
                      </Link>
                      {entry.audio_url ? <AudioButton src={entry.audio_url} label={entry.vocabulary_japanese} /> : null}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : null}

          <Link className="button button--accent" href={`/study/session?category=kanji&item=${item.id}`}>{t("quiz.practice")}</Link>
          <p className="muted">
            <a href="/data-sources/kanji.md" target="_blank" rel="noreferrer">KANJIDIC2 · EDRDG · CC BY-SA 4.0</a>
          </p>
        </article>
      ) : null}
    </div>
  );
}
