import { describe, expect, it } from "vitest";
import { inferDocumentType } from "@/services/documents";
import { DocumentType } from "@/types";

describe("documents service", () => {
    it("does not infer a clinical document type from an uploaded filename", () => {
        expect(
            inferDocumentType(new File(["test"], "vatsal-discharge-summary.pdf", {
                type: "application/pdf",
            })),
        ).toBe(DocumentType.OTHER);
        expect(
            inferDocumentType(new File(["test"], "blood-results.csv", {
                type: "text/csv",
            })),
        ).toBe(DocumentType.OTHER);
        expect(
            inferDocumentType(new File(["test"], "chest-xray.png", {
                type: "image/png",
            })),
        ).toBe(DocumentType.OTHER);
    });
});
