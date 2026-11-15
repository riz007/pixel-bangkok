const CATEGORIES: Record<string, { label: string; glyph: string }> = {
  temple: { label: "Temple", glyph: "▲" },
  landmark: { label: "Landmark", glyph: "★" },
  pier: { label: "Pier", glyph: "⚓" },
  historic: { label: "Historic site", glyph: "◆" },
  market: { label: "Market", glyph: "●" },
  neighbourhood: { label: "Neighbourhood", glyph: "■" },
};

export function categoryInfo(category: string): { label: string; glyph: string } {
  return CATEGORIES[category] ?? { label: category, glyph: "•" };
}
