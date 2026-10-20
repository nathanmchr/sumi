import { request } from "@/lib/api";
import type { FuriganaSegment, Locale } from "@/lib/types";

export type LessonSummary = {
  id: string; unit_id: string; unit_title: string; title: string; goal: string;
  position: number; minutes: number; total_steps: number; completed_steps: number;
  completed: boolean; recommended: boolean;
  is_recap?: boolean; locked?: boolean;
  vocabulary_count: number; grammar_count: number; kanji_count: number;
};
export type LessonStep = {
  id: string; kind: "read" | "word" | "grammar" | "kanji" | "dialogue" | "choice" | "recall";
  title: string; body?: string; japanese?: string; translation?: string;
  segments?: FuriganaSegment[]; romaji?: string; audio_url?: string;
  character?: string; meaning?: string; onyomi?: string[]; kunyomi?: string[];
  options?: { id: string; label: string }[]; prompt?: string; reading_note?: string;
  recap?: boolean; recap_category?: "vocabulary" | "grammar" | "kanji";
  source_lesson_id?: string; source_lesson_title?: string;
  recap_section_index?: number; recap_section_total?: number;
  lines?: { speaker?: string; japanese: string; translation: string; segments?: FuriganaSegment[]; romaji?: string }[]; review?: boolean;
};
export type LessonState = {
  lesson: LessonSummary; revision: number; cursor: number; viewing: number;
  step: LessonStep | null; feedback: {
    correct: boolean; answer: string; explanation: string;
    correct_option_id?: string; selected_option_id?: string | null;
    japanese?: string; meaning?: string; audio_url?: string; segments?: FuriganaSegment[]; romaji?: string;
  } | null;
  correct: number; answered: number; next_lesson_id: string | null;
  recap_total?: number; recap_answered?: number; recap_correct?: number;
};
export type LessonCommand = { action: "answer" | "continue"; step_id: string; revision: number; answer?: string };

export const getLessons = (locale: Locale) => request<LessonSummary[]>(`/lessons?level=N5&locale=${locale}`);
export const getLesson = (id: string, locale: Locale, step?: number) => request<LessonState>(
  `/lessons/${encodeURIComponent(id)}?locale=${locale}${step === undefined ? "" : `&step=${step}`}`);
export const advanceLesson = (id: string, locale: Locale, command: LessonCommand) => request<LessonState>(
  `/lessons/${encodeURIComponent(id)}/progress?locale=${locale}`, { method: "POST", body: JSON.stringify(command), signal: AbortSignal.timeout(15000) });

export const lessonCopy = {
  fr: {
    title: "Le japonais, pas à pas.", intro: "Des situations de tous les jours. Des mots, des structures et leurs kanjis, réunis dans un parcours N5.",
    course: "Parcours N5", lessons: "leçons", units: "unités", completed: "terminées", start: "Commencer", resume: "Reprendre", review: "Relire",
    recommended: "La prochaine étape", words: "mots", grammar: "grammaire", kanji: "kanjis", minutes: "min", back: "Toutes les leçons",
    loading: "Chargement du parcours…", error: "Impossible de charger les leçons.", retry: "Réessayer", empty: "Le parcours n'est pas encore disponible.",
    step: "Étape", of: "sur", progress: "Progression de la leçon", next: "Continuer", previous: "Précédent", check: "Vérifier", saving: "Enregistrement…",
    answer: "Ta réponse", placeholder: "En kana ou en romaji", correct: "Bien retrouvé.", incorrect: "À retenir pour la prochaine fois.", correction: "Réponse attendue",
    saveError: "La réponse n'a pas pu être confirmée. Réessaie, ou recharge la progression.", conflict: "La progression a changé. Recharge pour reprendre au bon endroit.", reload: "Recharger la progression",
    finished: "Une étape de plus.", finishedText: "Cette leçon est terminée. Tu peux relire les corrections, puis poursuivre à ton rythme.",
    score: "réponses justes au premier essai", mastery: "Terminer une leçon n'est pas la même chose que maîtriser ses contenus. Les révisions espacées restent un parcours distinct.",
    nextLesson: "La leçon suivante", reread: "Relire cette leçon", observing: "Relecture", reading: "Lecture", on: "Onyomi", kun: "Kunyomi", reviewWord: "Un mot déjà rencontré",
    recap: "Bilan cumulatif", recapSource: "Vu dans", recapScore: "au bilan cumulatif",
    recapCategories: { vocabulary: "Vocabulaire", grammar: "Grammaire", kanji: "Kanji" },
    grammarPoint: "point de grammaire", grammarPoints: "points de grammaire",
    themeRecapDescription: "Bilan exhaustif de tous les acquis", recapLocked: "Après les sous-leçons",
    themeFinished: "Thème terminé.", themeFinishedText: "Le bilan cumulatif est terminé. Tu peux relire tes corrections avant de passer au thème suivant.",
    prerequisites: "À suivre dans l'ordre, avec les kana comme base. Tu peux aussi ouvrir une leçon pour la relire.",
  },
  en: {
    title: "Japanese, one step at a time.", intro: "Everyday situations. Words, structures and their kanji, brought together in an N5 learning path.",
    course: "N5 learning path", lessons: "lessons", units: "units", completed: "completed", start: "Start", resume: "Resume", review: "Read again",
    recommended: "Your next step", words: "words", grammar: "grammar", kanji: "kanji", minutes: "min", back: "All lessons",
    loading: "Loading your learning path…", error: "Lessons could not be loaded.", retry: "Try again", empty: "The course is not available yet.",
    step: "Step", of: "of", progress: "Lesson progress", next: "Continue", previous: "Previous", check: "Check", saving: "Saving…",
    answer: "Your answer", placeholder: "In kana or romaji", correct: "You remembered it.", incorrect: "Something to remember next time.", correction: "Expected answer",
    saveError: "Your answer could not be confirmed. Try again, or reload your progress.", conflict: "Your progress changed. Reload to resume at the right step.", reload: "Reload progress",
    finished: "One step further.", finishedText: "This lesson is complete. Read your corrections again, then continue at your own pace.",
    score: "correct answers on the first try", mastery: "Completing a lesson is not the same as mastering its content. Spaced reviews remain a separate learning activity.",
    nextLesson: "Next lesson", reread: "Read this lesson again", observing: "Reading again", reading: "Reading", on: "Onyomi", kun: "Kunyomi", reviewWord: "A word you have met before",
    recap: "Cumulative test", recapSource: "From", recapScore: "on the cumulative test",
    recapCategories: { vocabulary: "Vocabulary", grammar: "Grammar", kanji: "Kanji" },
    grammarPoint: "grammar point", grammarPoints: "grammar points",
    themeRecapDescription: "A complete test of everything learned", recapLocked: "After the theme lessons",
    themeFinished: "Theme complete.", themeFinishedText: "The cumulative test is complete. Revisit your corrections before moving to the next theme.",
    prerequisites: "Follow the sequence, with kana as a foundation. You can also open a lesson to read it again.",
  },
};
