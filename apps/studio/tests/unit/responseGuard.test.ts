import { describe, it, expect } from "vitest";
import { LARGE_RESPONSE_BYTES } from "../../src/components/ResponsePanel";

describe("LARGE_RESPONSE_BYTES threshold", () => {
  it("is exactly 1_000_000 bytes (1 MB)", () => {
    expect(LARGE_RESPONSE_BYTES).toBe(1_000_000);
  });

  it("treats a 999_999 byte payload as small", () => {
    expect(999_999 < LARGE_RESPONSE_BYTES).toBe(true);
  });

  it("treats a 1_000_000 byte payload as large", () => {
    expect(1_000_000 >= LARGE_RESPONSE_BYTES).toBe(true);
  });

  it("treats a 2 MB payload as large", () => {
    expect(2_000_000 >= LARGE_RESPONSE_BYTES).toBe(true);
  });
});
