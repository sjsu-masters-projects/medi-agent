import { describe, expect, it } from "vitest";
import { sourceDocumentLabel } from "@/components/features/source-file";

describe("source document labels", () => {
    it("reuses the grounded English title without losing the original filename", () => {
        expect(sourceDocumentLabel({ file_name: "scan-01.pdf", display_title: {
            "en-US": "Lipid panel", "es-MX": "Perfil de lípidos",
        } })).toBe("Lipid panel (scan-01.pdf)");
    });
    it("does not substitute Spanish or invent a translation when English is missing", () => {
        expect(sourceDocumentLabel({ file_name: "scan-01.pdf", display_title: {
            "es-MX": "Perfil de lípidos",
        } })).toBe("scan-01.pdf");
    });
    it("handles legacy sources and avoids duplicated labels", () => {
        expect(sourceDocumentLabel({})).toBe("Uploaded document");
        expect(sourceDocumentLabel({ file_name: "scan.pdf", display_title: { "en-US": " scan.pdf " } })).toBe("scan.pdf");
        expect(sourceDocumentLabel({ file_name: "scan.pdf", display_title: { "en-US": " " } })).toBe("scan.pdf");
    });
});
