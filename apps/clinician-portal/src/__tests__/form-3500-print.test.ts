import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(__dirname, "../app/globals.css"), "utf8");

function printBlock(): string {
    const start = css.indexOf("@media print");
    expect(start).toBeGreaterThan(-1);
    let depth = 0;
    for (let index = css.indexOf("{", start); index < css.length; index += 1) {
        if (css[index] === "{") depth += 1;
        if (css[index] === "}") depth -= 1;
        if (depth === 0) return css.slice(start, index + 1);
    }
    throw new Error("Unterminated @media print block");
}

describe("Form 3500 print stylesheet", () => {
    const block = printBlock();

    it("prints on US Letter with half-inch margins", () => {
        expect(block).toMatch(/@page\s*\{\s*size:\s*Letter;\s*margin:\s*0\.5in;\s*\}/);
    });

    it("hides navigation and actions", () => {
        expect(block).toMatch(/nav,\s*aside,\s*\[data-print-hide\]\s*\{\s*display:\s*none !important;/);
        // Only the preview and its ancestors print when a preview is open.
        expect(block).toContain(".ma-print-root");
        expect(block).toMatch(/\*:has\(\.ma-print-root\)\s*\{[^}]*overflow:\s*visible !important;/);
    });

    it("keeps each section together", () => {
        expect(block).toMatch(/\.ma-print-section\s*\{\s*break-inside:\s*avoid;\s*\}/);
    });

    it("fixes the not-submitted footer to the bottom of every page", () => {
        expect(block).toMatch(/\.ma-print-footer\s*\{[^}]*position:\s*fixed;[^}]*bottom:\s*0;/);
    });

    it("uses colour tokens, not hex literals, in print rules", () => {
        expect(block).not.toMatch(/#[0-9A-Fa-f]{3,8}\b/);
    });
});
