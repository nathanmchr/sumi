"use client";

import { useState, type ReactNode } from "react";
import useSWR from "swr";
import type { JLPTLevelCode } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

const levelOrder: JLPTLevelCode[] = ["N5", "N4", "N3", "N2", "N1"];

type LevelItem = {
  id: string;
  jlpt_level_code: JLPTLevelCode;
};

type JlptLevelListProps<T extends LevelItem> = {
  query: string;
  cacheKey: string;
  loadItems: (level: JLPTLevelCode, query?: string) => Promise<T[]>;
  itemLabel: string;
  itemLabelPlural?: string;
  gridClassName?: string;
  renderItem: (item: T) => ReactNode;
};

type LevelSectionProps<T extends LevelItem> = JlptLevelListProps<T> & {
  level: JLPTLevelCode;
};

function LevelSection<T extends LevelItem>({ level, query, cacheKey, loadItems, itemLabel, itemLabelPlural = `${itemLabel}s`, gridClassName = "content-grid", renderItem }: LevelSectionProps<T>) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const isOpen = expanded || query.length > 0;
  const { data: items, error } = useSWR(
    isOpen ? [cacheKey, level, query] : null,
    () => loadItems(level, query || undefined),
  );
  const headingId = `level-${level.toLowerCase()}-${itemLabel}`;
  const countLabel = items
    ? `${items.length} ${items.length === 1 ? itemLabel : itemLabelPlural}`
    : isOpen
      ? t("catalog.loading")
      : t("catalog.viewList");

  return (
    <section className={`level-group${isOpen ? " level-group--open" : ""}`} aria-labelledby={headingId}>
      <button className="level-group__header" type="button" aria-expanded={isOpen} aria-controls={`${headingId}-content`} onClick={() => setExpanded((current) => !current)}>
        <h2 id={headingId}>{level}</h2>
        <span>{countLabel}<i aria-hidden="true" /></span>
      </button>
      {isOpen ? (
        <div id={`${headingId}-content`}>
          {error ? <p className="muted">{t("catalog.loadError")}</p> : null}
          {!items && !error ? <p className="muted">{t("catalog.loading")}</p> : null}
          {items?.length === 0 ? <p className="muted">{t("catalog.noMatch")}</p> : null}
          {items?.length ? (
            <div className={gridClassName}>
              {items.map((item) => <div key={item.id}>{renderItem(item)}</div>)}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export function JlptLevelList<T extends LevelItem>(props: JlptLevelListProps<T>) {
  return (
    <div className="level-library">
      {levelOrder.map((level) => <LevelSection key={level} {...props} level={level} />)}
    </div>
  );
}
