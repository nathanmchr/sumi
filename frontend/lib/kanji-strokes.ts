export type KanjiStrokeData = {
  character: string;
  view_box: number[];
  strokes: { path: string; number_transform: number[] }[];
  source: string;
  source_sha256: string;
  license: string;
};

export async function loadKanjiStrokes(character: string, level: string): Promise<KanjiStrokeData> {
  if (Array.from(character).length !== 1) throw new Error("Invalid kanji");
  if (!/^N[1-5]$/.test(level)) throw new Error("Invalid JLPT level");
  const code = character.codePointAt(0)!.toString(16).padStart(5, "0");
  const response = await fetch(`/kanji-strokes/${level.toLowerCase()}/${code}.json`, { signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error("Stroke data unavailable");
  const data = await response.json();
  if (data.character !== character || JSON.stringify(data.view_box) !== "[0,0,109,109]"
    || !Array.isArray(data.strokes) || !data.strokes.length || data.strokes.length > 40
    || !data.strokes.every((stroke: KanjiStrokeData["strokes"][number]) =>
      typeof stroke.path === "string" && /^[Mm][\s,0-9.eE+\-MmZzLlHhVvCcSsQqTtAa]+$/.test(stroke.path)
      && Array.isArray(stroke.number_transform) && stroke.number_transform.length === 6
      && stroke.number_transform.every(Number.isFinite))) {
    throw new Error("Invalid stroke data");
  }
  return data;
}
