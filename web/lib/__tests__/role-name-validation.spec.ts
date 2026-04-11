import { describe, expect, it } from "vitest";

import { formatRoleName, validateCustomRoleName } from "@/lib/role-name-validation";

describe("role-name-validation", () => {
  it("formats role names for cleaner display", () => {
    expect(formatRoleName("warehouse associate")).toBe("Warehouse Associate");
    expect(formatRoleName("line-cook")).toBe("Line-Cook");
  });

  it("suggests common spelling corrections", () => {
    expect(
      validateCustomRoleName("Barrista", []),
    ).toEqual({
      ok: false,
      message: 'Did you mean "Barista"?',
    });
  });

  it("uses existing business roles for typo detection", () => {
    expect(
      validateCustomRoleName("Bartendar", ["Bartender"]),
    ).toEqual({
      ok: false,
      message: 'Did you mean "Bartender"?',
    });
  });

  it("allows clean custom roles", () => {
    expect(validateCustomRoleName("Shift Captain", ["Server"])).toEqual({
      ok: true,
      roleName: "Shift Captain",
    });
  });
});
