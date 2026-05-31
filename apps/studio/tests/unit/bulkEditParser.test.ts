import { describe, it, expect } from "vitest";
import { parseBulkText, serializePairsToText, type KeyValuePair } from "../../src/lib/bulkEditParser";

describe("parseBulkText", () => {
  it("parses colon-separated headers", () => {
    const result = parseBulkText("Content-Type: application/json\nAccept: text/html");
    expect(result).toEqual([
      { key: "Content-Type", value: "application/json", enabled: true },
      { key: "Accept", value: "text/html", enabled: true },
    ]);
  });

  it("parses equals-separated query params", () => {
    const result = parseBulkText("page=1\nlimit=20");
    expect(result).toEqual([
      { key: "page", value: "1", enabled: true },
      { key: "limit", value: "20", enabled: true },
    ]);
  });

  it("skips empty lines", () => {
    const result = parseBulkText("X-A: 1\n\n\nX-B: 2");
    expect(result).toHaveLength(2);
    expect(result[0].key).toBe("X-A");
    expect(result[1].key).toBe("X-B");
  });

  it("skips #-prefixed comment lines", () => {
    const result = parseBulkText("# this is a comment\nX-A: 1");
    expect(result).toHaveLength(1);
    expect(result[0].key).toBe("X-A");
  });

  it("handles header values that contain colons", () => {
    const result = parseBulkText("Authorization: Bearer abc:def:ghi");
    expect(result).toHaveLength(1);
    expect(result[0].key).toBe("Authorization");
    expect(result[0].value).toBe("Bearer abc:def:ghi");
  });

  it("returns empty array for blank input", () => {
    expect(parseBulkText("")).toEqual([]);
    expect(parseBulkText("   \n  \n  ")).toEqual([]);
  });

  it("handles CRLF line endings", () => {
    const result = parseBulkText("X-A: 1\r\nX-B: 2");
    expect(result).toHaveLength(2);
  });

  it("sets enabled: true for all parsed pairs", () => {
    const result = parseBulkText("X-Foo: bar");
    expect(result[0].enabled).toBe(true);
  });

  it("handles mixed colon and equals separators in same block", () => {
    const result = parseBulkText("X-Header: value\nparam=123");
    expect(result).toEqual([
      { key: "X-Header", value: "value", enabled: true },
      { key: "param", value: "123", enabled: true },
    ]);
  });

  it("treats line without separator as key with empty value", () => {
    const result = parseBulkText("standalone-key");
    expect(result).toHaveLength(1);
    expect(result[0].key).toBe("standalone-key");
    expect(result[0].value).toBe("");
  });

  it("trims whitespace from keys and values", () => {
    const result = parseBulkText("  X-Padded  :  value with spaces  ");
    expect(result[0].key).toBe("X-Padded");
    expect(result[0].value).toBe("value with spaces");
  });
});

describe("serializePairsToText", () => {
  it("serializes pairs to Key: Value lines", () => {
    const pairs: KeyValuePair[] = [
      { key: "Accept", value: "application/json", enabled: true },
      { key: "X-Custom", value: "hello", enabled: true },
    ];
    expect(serializePairsToText(pairs)).toBe("Accept: application/json\nX-Custom: hello");
  });

  it("prefixes disabled pairs with # ", () => {
    const pairs: KeyValuePair[] = [
      { key: "X-Active", value: "yes", enabled: true },
      { key: "X-Disabled", value: "no", enabled: false },
    ];
    const result = serializePairsToText(pairs);
    expect(result).toContain("X-Active: yes");
    expect(result).toContain("# X-Disabled: no");
  });

  it("skips pairs where both key and value are empty", () => {
    const pairs: KeyValuePair[] = [
      { key: "", value: "", enabled: true },
      { key: "X-A", value: "1", enabled: true },
    ];
    expect(serializePairsToText(pairs)).toBe("X-A: 1");
  });

  it("returns empty string for empty array", () => {
    expect(serializePairsToText([])).toBe("");
  });

  it("round-trips through parseBulkText", () => {
    const original: KeyValuePair[] = [
      { key: "Content-Type", value: "application/json", enabled: true },
      { key: "Accept", value: "text/html", enabled: true },
    ];
    const text = serializePairsToText(original);
    const parsed = parseBulkText(text);
    expect(parsed).toEqual(original);
  });
});
