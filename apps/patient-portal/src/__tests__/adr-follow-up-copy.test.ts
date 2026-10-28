import { describe, expect, it } from "vitest";

import {
  formatFollowUpDate,
  getADRFollowUpCopy,
} from "@/content/adr-follow-up-copy";
import type { Locale } from "@/types";

type Leaf = string | ((...args: never[]) => string);

/** Flattens a copy object into `dotted.path -> leaf` entries. */
function collectLeaves(
  value: unknown,
  prefix = "",
  out = new Map<string, Leaf>(),
): Map<string, Leaf> {
  if (typeof value === "string" || typeof value === "function") {
    out.set(prefix, value as Leaf);
    return out;
  }
  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      collectLeaves(child, prefix ? `${prefix}.${key}` : key, out);
    }
    return out;
  }
  throw new Error(`Unexpected copy value at "${prefix}": ${String(value)}`);
}

// Sample arguments: symptom and medication strings, counts and formatted dates.
const SAMPLE_ARGS: readonly (string | number)[] = [
  "dizziness",
  "lisinopril",
  0,
  1,
  2,
  5,
  "October 12, 2026",
  "12 de octubre de 2026",
];

/** Every combination of sample arguments for a function of the given arity. */
function argumentCombinations(arity: number): (string | number)[][] {
  let combos: (string | number)[][] = [[]];
  for (let index = 0; index < arity; index += 1) {
    combos = combos.flatMap((combo) => SAMPLE_ARGS.map((arg) => [...combo, arg]));
  }
  return combos;
}

function outputs(leaf: Leaf): string[] {
  if (typeof leaf === "string") return [leaf];
  const call = leaf as (...args: (string | number)[]) => string;
  return argumentCombinations(leaf.length).map((args) => call(...args));
}

// Values that are intentionally the same in both locales.
const INTENTIONALLY_IDENTICAL = new Set(["answers.no"]);

const en = collectLeaves(getADRFollowUpCopy("en-US"));
const es = collectLeaves(getADRFollowUpCopy("es-MX"));

describe("ADR follow-up copy", () => {
  // Feature: adr-loop-gap-fixes, Property 3: Copy parity across locales
  describe("Property 3: copy parity across locales", () => {
    it("defines the same key paths in en-US and es-MX, both ways", () => {
      const enPaths = [...en.keys()].sort();
      const esPaths = [...es.keys()].sort();
      expect(enPaths.length).toBeGreaterThan(0);
      expect(enPaths.filter((path) => !es.has(path))).toEqual([]);
      expect(esPaths.filter((path) => !en.has(path))).toEqual([]);
    });

    it("uses the same leaf kind and arity for every path", () => {
      for (const [path, enLeaf] of en) {
        const esLeaf = es.get(path);
        expect(typeof esLeaf, path).toBe(typeof enLeaf);
        if (typeof enLeaf === "function" && typeof esLeaf === "function") {
          expect(esLeaf.length, path).toBe(enLeaf.length);
        }
      }
    });

    it("has a non-empty string or non-empty function output for every leaf", () => {
      for (const leaves of [en, es]) {
        for (const [path, leaf] of leaves) {
          for (const text of outputs(leaf)) {
            expect(typeof text, path).toBe("string");
            expect(text.trim().length, path).toBeGreaterThan(0);
          }
        }
      }
    });

    it("translates every prose value except the listed identical ones", () => {
      for (const [path, enLeaf] of en) {
        const esLeaf = es.get(path);
        if (esLeaf === undefined) throw new Error(`Missing es-MX path ${path}`);
        const enTexts = outputs(enLeaf);
        const esTexts = outputs(esLeaf);
        if (INTENTIONALLY_IDENTICAL.has(path)) {
          expect(esTexts, path).toEqual(enTexts);
          continue;
        }
        enTexts.forEach((text, index) => {
          expect(esTexts[index], path).not.toBe(text);
        });
      }
    });
  });

  it("keeps the en-US selector strings exactly", () => {
    const copy = getADRFollowUpCopy("en-US");
    expect(copy.answers).toEqual({
      yes: "Yes",
      no: "No",
      do_not_know: "I\u2019m not sure",
    });
    expect(copy.reviewAnswers).toBe("Review answers");
    expect(copy.send).toBe("Send to care team");
    expect(copy.edit).toBe("Edit");
  });

  it("keeps the three safety statements in both locales", () => {
    const enCopy = getADRFollowUpCopy("en-US");
    expect(enCopy.questions.reappeared_on_rechallenge.prompt).toContain(
      "Do not restart it to answer",
    );
    expect(enCopy.questions.dose_response.prompt).toContain(
      "Do not change your dose to answer",
    );
    expect(enCopy.caution).toBe(
      "Answer only from what has already happened. Do not restart, stop, or change a medicine just to answer these questions.",
    );

    const esCopy = getADRFollowUpCopy("es-MX");
    expect(esCopy.questions.reappeared_on_rechallenge.prompt).toContain(
      "No lo reinicies para responder",
    );
    expect(esCopy.questions.dose_response.prompt).toContain(
      "No cambies tu dosis para responder",
    );
    expect(esCopy.caution).toContain("No reinicies, suspendas ni cambies");
  });

  it("asks the two new questions retrospectively in both locales (PV-001-D)", () => {
    const enCopy = getADRFollowUpCopy("en-US");
    expect(enCopy.questions.improved_on_dechallenge.prompt).toContain(
      "Do not stop or skip it to answer",
    );
    expect(enCopy.questions.improved_on_dechallenge.prompt).toMatch(/^Before this request/);
    expect(enCopy.questions.event_after_drug.prompt).toContain("first start after you began");

    const esCopy = getADRFollowUpCopy("es-MX");
    expect(esCopy.questions.improved_on_dechallenge.prompt).toContain(
      "No lo suspendas ni lo omitas para responder",
    );
    expect(esCopy.questions.improved_on_dechallenge.prompt).toMatch(/^Antes de esta solicitud/);
    expect(esCopy.questions.event_after_drug.prompt).toContain("empezó por primera vez");
    for (const copy of [enCopy, esCopy]) {
      for (const question of Object.values(copy.questions)) {
        expect(question.label.trim()).not.toBe("");
        expect(question.evidencePrompt.trim()).not.toBe("");
      }
    }
  });

  it("falls back to en-US for an unsupported locale", () => {
    expect(getADRFollowUpCopy("fr-FR" as Locale)).toBe(
      getADRFollowUpCopy("en-US"),
    );
  });

  describe("formatFollowUpDate", () => {
    it("returns null for invalid input", () => {
      expect(formatFollowUpDate("", "en-US", "UTC")).toBeNull();
      expect(formatFollowUpDate("not-a-date", "en-US", "UTC")).toBeNull();
    });

    it("formats in the given timezone", () => {
      const iso = "2026-10-13T03:30:00Z";
      expect(formatFollowUpDate(iso, "en-US", "America/Los_Angeles")).toBe(
        "October 12, 2026",
      );
      expect(formatFollowUpDate(iso, "es-MX", "America/Los_Angeles")).toBe(
        "12 de octubre de 2026",
      );
    });

    it("falls back to UTC for an invalid or missing timezone", () => {
      const iso = "2026-10-13T03:30:00Z";
      expect(formatFollowUpDate(iso, "en-US", "Not/A_Zone")).toBe(
        "October 13, 2026",
      );
      expect(formatFollowUpDate(iso, "en-US", undefined)).toBe(
        "October 13, 2026",
      );
    });
  });
});
