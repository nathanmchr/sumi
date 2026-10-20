"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import type { ContentType, JLPTLevelCode, ReviewStatus } from "@/lib/types";

type Props = {
  category: ContentType;
  item?: { jlpt_level_code: JLPTLevelCode; mastery: number; status: ReviewStatus };
};

const backLabels = {
  vocabulary: "detail.backVocabulary",
  kanji: "detail.backKanji",
  grammar: "detail.backGrammar",
} as const;

export function StudyDetailHeader({ category, item }: Props) {
  const { t } = useI18n();

  return (
    <header className="page-header">
      <div>
        <h1>{t(`nav.${category}`)}</h1>
        {item ? (
          <div className="detail-header__meta">
            <span className="tag">JLPT {item.jlpt_level_code}</span>
            <span>{t("detail.mastery")} <strong>{Math.round(item.mastery * 100)}%</strong></span>
            <span className="muted">{t(`status.${item.status}`)}</span>
          </div>
        ) : null}
      </div>
      <Link className="button" href={`/study/${category}`}>{t(backLabels[category])}</Link>
    </header>
  );
}
