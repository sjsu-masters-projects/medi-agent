import { describe, expect, it } from "vitest";
import { recordTitle } from "@/components/features/record-row";

const file = "Morgan-Ellis-01-Hidratacion-es-MX-2026-10-09.pdf";

describe("record titles", () => {
    it("shows the drafted title in the reader's language", () => {
        const document = { fileName: file, displayTitle: { "en-US": "Hydration instructions", "es-MX": "Indicaciones de hidratación" } };
        expect(recordTitle(document, "en-US", "Morgan Ellis")).toBe("Hydration instructions");
        expect(recordTitle(document, "es-MX", "Morgan Ellis")).toBe("Indicaciones de hidratación");
    });

    it("falls back to the cleaned file name when no title was drafted", () => {
        expect(recordTitle({ fileName: file }, "en-US", "Morgan Ellis")).toBe("Hidratacion");
        expect(recordTitle({ fileName: file, displayTitle: { "es-MX": "Indicaciones" } }, "en-US", "Morgan Ellis")).toBe("Hidratacion");
    });
});
