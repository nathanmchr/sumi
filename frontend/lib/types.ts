export type JLPTLevelCode = "N5" | "N4" | "N3" | "N2" | "N1";
export type Locale = "en" | "fr";
export type ContentType = "vocabulary" | "kanji" | "grammar";
export type ReviewStatus = "new" | "relearning" | "learning" | "fragile" | "known" | "review" | "master";
export type FuriganaDisplayMode = "always" | "hover" | "hidden";

export type User = {
  id: string;
  email: string;
  full_name: string;
  is_admin: boolean;
};

export type UserSettings = {
  user_id: string;
  vocabulary_level_code: JLPTLevelCode;
  vocabulary_min_level_code: JLPTLevelCode;
  grammar_level_code: JLPTLevelCode;
  grammar_min_level_code: JLPTLevelCode;
  kanji_level_code: JLPTLevelCode;
  kanji_min_level_code: JLPTLevelCode;
  furigana_display_mode: FuriganaDisplayMode;
  furigana_helper_enabled: boolean;
  romaji_enabled: boolean;
  daily_goal_minutes: number;
  interface_locale: Locale;
  content_locale: Locale;
};

export type JLPTLevel = {
  code: JLPTLevelCode;
  rank: number;
  label: string;
  description?: string | null;
};

export type ExampleSentence = {
  id: string;
  text: string;
  translation: string;
  furigana_segments: FuriganaSegment[];
  audio_url?: string | null;
  translation_locale: Locale;
};

export type FuriganaSegment = {
  surface: string;
  reading?: string;
  kanji_ids?: string[];
};

export type VocabularyItem = {
  catalog_id?: string | null;
  source_order?: number | null;
  kanji_level_code?: JLPTLevelCode | null;
  id: string;
  slug: string;
  japanese: string;
  reading: string;
  romaji: string;
  furigana_segments: FuriganaSegment[];
  translation: string;
  part_of_speech: string;
  jlpt_level_code: JLPTLevelCode;
  mastery: number;
  status: ReviewStatus;
  audio_url?: string | null;
  notes?: string | null;
  translation_locale: Locale;
  example_sentences: ExampleSentence[];
  kanji_links: {
    kanji_id: string;
    kanji_character: string;
    kanji_slug: string;
    jlpt_level_code: JLPTLevelCode;
    meanings: string[];
    position?: number | null;
    is_primary: boolean;
  }[];
};

export type HomophoneWord = Pick<VocabularyItem, "id" | "japanese" | "translation" | "translation_locale" | "jlpt_level_code" | "audio_url">;

export type HomophoneGroup = { reading: string; words: HomophoneWord[] };

export type HomophonePage = { groups: HomophoneGroup[]; total: number; offset: number; limit: number };

export type KanjiItem = {
  catalog_id?: string | null;
  source_order?: number | null;
  id: string;
  character: string;
  slug: string;
  meanings: string[];
  onyomi: string[];
  kunyomi: string[];
  radicals: string[];
  mnemonic?: string | null;
  jlpt_level_code: JLPTLevelCode;
  mastery: number;
  status: ReviewStatus;
  linked_vocabulary: {
    vocabulary_id: string;
    vocabulary_japanese: string;
    vocabulary_reading: string;
    jlpt_level_code: JLPTLevelCode;
    furigana_segments: FuriganaSegment[];
    translation: string;
    audio_url?: string | null;
  }[];
  translation_locale: Locale;
};

export type GrammarItem = {
  catalog_id?: string | null;
  source_order?: number | null;
  exercisable: boolean;
  id: string;
  slug: string;
  title: string;
  jlpt_level_code: JLPTLevelCode;
  explanation: string;
  structure: string;
  nuances: string;
  counter_examples: { title?: string; text?: string; explanation?: string }[];
  examples: { text?: string; translation?: string; note?: string }[];
  mastery: number;
  status: ReviewStatus;
  translation_locale: Locale;
};

export type DashboardStats = {
  learned_items: number;
  due_reviews: number;
  streak_days: number;
  study_days: string[];
  estimated_session_minutes: number;
  progression_by_category: Record<string, number>;
  recommendation: string;
};

export type SearchResult = {
  content_type: ContentType;
  id: string;
  title: string;
  subtitle: string;
  jlpt_level_code: JLPTLevelCode;
  url: string;
};

export type DueItem = {
  content_type: ContentType;
  content_id: string;
  title: string;
  subtitle: string;
  jlpt_level_code: JLPTLevelCode;
  next_review_at?: string | null;
  status: ReviewStatus;
};

export type SessionRecommendation = {
  minutes: number;
  target_items: number;
  focus: ContentType[];
  rationale: string;
};

export type QuizStart = {
  category?: ContentType;
  content_id?: string;
  only_due?: boolean;
  planned_items?: number;
};

export type MemoryProgress = {
  phase: "acquisition" | "consolidation";
  value: number;
  successes?: number | null;
  required_successes?: number | null;
};

export type QuizAnswer = {
  memory?: MemoryProgress | null;
  planned_items?: number | null;
  question_id: string;
  selected_option_id: string;
  correct_option_id: string;
  correct: boolean;
  title: string;
  reading: string;
  meaning: string;
  explanation: string;
  example?: { text: string; translation: string; reading: string } | null;
  status: ReviewStatus;
  next_review_at: string | null;
  difficulty: number | null;
  stability: number | null;
  retrievability: number | null;
};

export type QuizQuestion = {
  phase: "introduction" | "question";
  introduction?: { meaning: string; example?: { text: string; translation: string; reading: string } | null } | null;
  id: string;
  content_type: ContentType;
  content_id: string;
  kind: "meaning" | "cloze";
  title: string;
  reading: string;
  furigana_segments: FuriganaSegment[];
  instruction: string;
  context: string;
  jlpt_level_code: JLPTLevelCode;
  locale: Locale;
  audio_url?: string | null;
  choices: { id: string; label: string }[];
  expires_at: string;
  result?: QuizAnswer | null;
};

export type QuizTurn = {
  acquired_items: number;
  acquiring_items: number;
  session_id: string;
  completed_items: number;
  planned_items: number;
  correct_answers: number;
  ended: boolean;
  question?: QuizQuestion | null;
  next_due_at?: string | null;
  grammar_points_available: number;
  unavailable_items: number;
};
