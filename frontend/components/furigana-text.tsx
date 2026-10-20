"use client";

import type { FuriganaDisplayMode, FuriganaSegment } from "@/lib/types";
import clsx from "clsx";

type Props = {
  segments: FuriganaSegment[];
  mode: FuriganaDisplayMode;
  helper?: boolean;
  onKanjiClick?: (kanjiId: string) => void;
  className?: string;
};

const KANJI_PATTERN = /[\p{Script=Han}々〆]/u;
const KANJI_GROUP_PATTERN = /^[\p{Script=Han}々〆]+$/u;

export function FuriganaText({ segments, mode, helper = false, onKanjiClick, className }: Props) {
  const items = segments ?? [];
  let readingIndex = 0;

  return (
    <span className={clsx("furigana", `furigana--${mode}`, helper && mode !== "hidden" && "furigana--helper", className)}>
      {items.map((segment, index) => {
        const characters = Array.from(segment.surface);
        const linkedIds = segment.kanji_ids ?? [];
        const idsByCharacter = linkedIds.length === characters.length;
        const idsByKanji = linkedIds.length === characters.filter((character) => KANJI_PATTERN.test(character)).length;
        let kanjiOffset = 0;
        const rubyText = KANJI_GROUP_PATTERN.test(segment.surface) ? segment.reading?.trim() : undefined;
        const content = characters.map((character, charIndex) => {
          const isKanji = KANJI_PATTERN.test(character);
          const kanjiId = idsByCharacter ? linkedIds[charIndex] : idsByKanji && isKanji ? linkedIds[kanjiOffset] : undefined;
          if (isKanji) kanjiOffset++;
          return onKanjiClick && isKanji && kanjiId ? (
            <button
              key={`${character}-${charIndex}`}
              type="button"
              className="furigana__kanji"
              onClick={() => onKanjiClick(kanjiId)}
            >
              {character}
            </button>
          ) : character;
        });

        return (
          <span key={`${segment.surface}-${index}`} className={clsx("furigana__segment", rubyText && `furigana__segment--tone-${readingIndex++ % 4}`)}>
            {rubyText ? (
              <ruby className="furigana__token">
                <span className="furigana__base">{content}</span>
                <rt>{rubyText}</rt>
              </ruby>
            ) : <span className="furigana__token"><span className="furigana__base">{content}</span></span>}
          </span>
        );
      })}
    </span>
  );
}
