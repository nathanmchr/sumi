"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";

export default function HomePage() {
  const { t } = useI18n();
  const highlights = [t("landing.highlightTargets"), t("landing.highlightRecall"), t("landing.highlightFurigana")];
  return (
    <main className="landing">
      <section className="landing-hero">
        <div className="landing-hero__copy">
          <p className="eyebrow">{t("landing.eyebrow")}</p>
          <h1>{t("landing.title")}</h1>
          <p className="landing-hero__lede">{t("landing.intro")}</p>
          <div className="landing-actions">
            <Link className="button button--accent" href="/register">{t("auth.createAccount")}</Link>
            <Link className="button" href="/login">{t("auth.signIn")}</Link>
          </div>
          <ul className="landing-highlights">
            {highlights.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>

        <motion.div
          className="landing-preview"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        >
          <div className="preview-card preview-card--wide">
            <p className="preview-card__label">{t("landing.today")}</p>
            <strong>{t("landing.due")}</strong>
            <span>{t("landing.dueText")}</span>
          </div>
          <div className="preview-grid">
            <div className="preview-card">
              <p className="preview-card__label">{t("nav.vocabulary")}</p>
              <strong>N4</strong>
              <span>{t("landing.vocabText")}</span>
            </div>
            <div className="preview-card">
              <p className="preview-card__label">{t("nav.grammar")}</p>
              <strong>N3</strong>
              <span>{t("landing.grammarText")}</span>
            </div>
            <div className="preview-card">
              <p className="preview-card__label">{t("nav.kanji")}</p>
              <strong>N5</strong>
              <span>{t("landing.kanjiText")}</span>
            </div>
          </div>
        </motion.div>
      </section>
    </main>
  );
}
