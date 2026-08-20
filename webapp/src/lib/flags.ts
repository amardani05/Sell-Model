import { ScoreRow } from "./types";

// Top red flags derived from a scores.json row.
//
// scores.json already carries every direction aligned peer neutral z score
// (the `<factor>__n` columns), so the hover summary and the overlay's flag
// column can be built without the much larger drill down payload. Keeping this
// in one place means the two views cannot drift apart, and it matches what the
// drill down panel shows once it loads.
export interface TopFlag { factor: string; z: number; }

export function topFlagsFromScore(row: ScoreRow | undefined, k = 3, minZ = -Infinity): TopFlag[] {
  if (!row) return [];
  const flags: TopFlag[] = [];
  for (const key of Object.keys(row)) {
    if (!key.endsWith("__n")) continue;
    const v = row[key];
    if (typeof v !== "number" || !Number.isFinite(v)) continue;
    flags.push({ factor: key.slice(0, -3), z: v });
  }
  return flags
    .filter((f) => f.z > minZ)
    .sort((a, b) => b.z - a.z)
    .slice(0, k);
}
