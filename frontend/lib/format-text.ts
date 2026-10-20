const SUPERSCRIPTS: Record<string, string> = {
  "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
  "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
  "+": "⁺", "-": "⁻", "−": "⁻",
};

/** Format integer powers in educational text without changing the source data. */
export function formatPowers(text: string | null | undefined): string {
  return (text ?? "").replace(
    /([\p{L}\p{N})])(?:\^|\*\*)(?:\{([+−-]?\d+)\}|\(([+−-]?\d+)\)|([+−-]?\d+)(?!\d|[.,]\d))/gu,
    (_match, base: string, braces: string, parentheses: string, plain: string) =>
      base + Array.from(braces ?? parentheses ?? plain, (character) => SUPERSCRIPTS[character]).join(""),
  );
}
