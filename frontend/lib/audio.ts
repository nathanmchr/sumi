export function resolveAudioSource(src: string): string {
  if (/^(?:https?:)?\/\//.test(src) || src.startsWith("data:") || src.startsWith("blob:")) return src;

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
  try {
    return new URL(src, new URL(apiUrl).origin).toString();
  } catch {
    return src;
  }
}
