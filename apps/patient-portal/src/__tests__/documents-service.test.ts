import { describe, expect, it } from "vitest";
import { inferDocumentType } from "@/services/documents";
import { DocumentType } from "@/types";

describe("documents service", () => {
    it("infers clinical document types from uploaded filenames", () => {
        expect(
            inferDocumentType(new File(["test"], "vatsal-discharge-summary.pdf", {
                type: "application/pdf",
            })),
        ).toBe(DocumentType.DISCHARGE_SUMMARY);
        expect(
            inferDocumentType(new File(["test"], "blood-results.csv", {
                type: "text/csv",
            })),
        ).toBe(DocumentType.LAB_REPORT);
        expect(
            inferDocumentType(new File(["test"], "chest-xray.png", {
                type: "image/png",
            })),
        ).toBe(DocumentType.DIAGNOSTIC_REPORT);
    });
});
