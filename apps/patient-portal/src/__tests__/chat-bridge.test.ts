import { describe, expect, it, beforeEach } from "vitest";
import {
    buildDocumentChatHref,
    buildSuggestedDocumentQuestion,
    consumePendingChatDocumentContext,
    storePendingChatDocumentContext,
} from "@/services/chat-bridge";
import { Language } from "@/types";

describe("chat bridge helpers", () => {
    beforeEach(() => {
        window.sessionStorage.clear();
    });

    it("stores and consumes pending document context once", () => {
        storePendingChatDocumentContext({
            documentId: "doc-1",
            documentName: "Result.pdf",
            documentType: "lab_report",
            preferredLanguage: Language.EN,
            provider: "Care team",
            suggestedQuestion: "Help me understand this report.",
            summary: "Stable labs.",
        });

        expect(consumePendingChatDocumentContext("doc-1")).toMatchObject({
            documentId: "doc-1",
            documentName: "Result.pdf",
        });
        expect(consumePendingChatDocumentContext("doc-1")).toBeNull();
    });

    it("builds chat href and localized suggested questions", () => {
        expect(buildDocumentChatHref("doc-1")).toBe("/chat?document=doc-1");
        expect(
            buildSuggestedDocumentQuestion({
                documentName: "Result.pdf",
                documentType: "lab_report",
                preferredLanguage: Language.EN,
                provider: "Care team",
            }),
        ).toContain("Help me understand");
        expect(
            buildSuggestedDocumentQuestion({
                documentName: "Resultado.pdf",
                documentType: "lab_report",
                preferredLanguage: Language.ES,
                provider: "Care team",
            }),
        ).toContain("Ayúdame a entender");
    });

    it("rejects invalid stored document types", () => {
        window.sessionStorage.setItem(
            "patient-portal.chat.document-context.doc-2",
            JSON.stringify({
                documentId: "doc-2",
                documentName: "Broken.pdf",
                documentType: "made_up_type",
                preferredLanguage: Language.EN,
                suggestedQuestion: "Help me.",
            }),
        );

        expect(consumePendingChatDocumentContext("doc-2")).toBeNull();
    });
});
