export function trimString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function normalizeInlineWhitespace(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

export function normalizeCasefoldedWhitespace(value: string): string {
  return normalizeInlineWhitespace(value).toLowerCase();
}
