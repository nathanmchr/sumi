import type { ContentType } from "@/lib/types";

export function contentHref(contentType: ContentType, contentId: string) {
  if (contentType === "vocabulary") {
    return `/study/vocabulary/${contentId}`;
  }
  if (contentType === "kanji") {
    return `/study/kanji/${contentId}`;
  }
  return `/study/grammar/${contentId}`;
}

export function contentLabel(contentType: ContentType) {
  if (contentType === "vocabulary") return "Vocabulary";
  if (contentType === "kanji") return "Kanji";
  return "Grammar";
}
