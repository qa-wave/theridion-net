export interface KeyValuePair {
  key: string;
  value: string;
  enabled: boolean;
}

/**
 * Parses a block of text into key-value pairs.
 * Supports both "Key: Value" (headers style) and "key=value" (query params style).
 * Empty lines and lines starting with "#" are skipped.
 */
export function parseBulkText(text: string): KeyValuePair[] {
  const lines = text.split(/\r?\n/);
  const result: KeyValuePair[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    // Try "Key: Value" format first (colon separator)
    const colonIdx = trimmed.indexOf(":");
    if (colonIdx > 0) {
      const key = trimmed.slice(0, colonIdx).trim();
      const value = trimmed.slice(colonIdx + 1).trim();
      if (key) {
        result.push({ key, value, enabled: true });
        continue;
      }
    }

    // Fall back to "key=value" format
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx > 0) {
      const key = trimmed.slice(0, eqIdx).trim();
      const value = trimmed.slice(eqIdx + 1).trim();
      if (key) {
        result.push({ key, value, enabled: true });
        continue;
      }
    }

    // Line has no recognizable separator — treat whole line as key with empty value
    if (trimmed) {
      result.push({ key: trimmed, value: "", enabled: true });
    }
  }

  return result;
}

/**
 * Serializes key-value pairs back to "Key: Value" text (one pair per line).
 * Disabled rows are prefixed with "# ".
 */
export function serializePairsToText(pairs: KeyValuePair[]): string {
  return pairs
    .filter((p) => p.key || p.value)
    .map((p) => (p.enabled ? `${p.key}: ${p.value}` : `# ${p.key}: ${p.value}`))
    .join("\n");
}
