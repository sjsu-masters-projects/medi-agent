import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { getConversationCopy } from "../../../../packages/shared/src/utils/care-conversations";
import { TranslationNote } from "@/components/features/translation-note";

/**
 * LOC-003 item 5, patient side. A patient reading a translation is entitled to know a
 * computer made it, that it may be wrong, and that their care team works from the original.
 *
 * Only approved clinical wording reaches a patient's Today, so the caveat belongs on
 * messages — never on a care plan a clinician verified.
 */

const en = getConversationCopy("en-US");
const es = getConversationCopy("es-MX");

afterEach(cleanup);

describe("patient translation note", () => {
    it("opens on tap, not hover alone", () => {
        render(<TranslationNote copy={en} modelId="gemini-test" />);
        expect(screen.queryByText(/computer made it/i)).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "About this translation" }));
        expect(screen.getByText(/A computer made it, not a person/)).toBeInTheDocument();
    });

    it("names the model that produced it", () => {
        render(<TranslationNote copy={en} modelId="gemini-test" />);
        fireEvent.click(screen.getByRole("button", { name: "About this translation" }));
        expect(screen.getByText("It was made by the gemini-test model.")).toBeInTheDocument();
    });

    it("says plainly when the model was not recorded", () => {
        render(<TranslationNote copy={en} />);
        fireEvent.click(screen.getByRole("button", { name: "About this translation" }));
        expect(screen.getByText(/was not recorded/)).toBeInTheDocument();
    });

    it("tells the patient the original is what counts", () => {
        render(<TranslationNote copy={en} modelId="gemini-test" />);
        fireEvent.click(screen.getByRole("button", { name: "About this translation" }));
        expect(screen.getByText(/original message is the one that counts/)).toBeInTheDocument();
        expect(screen.getByText(/numbers, doses and medication names/)).toBeInTheDocument();
        expect(screen.getByText(/ask your care team/)).toBeInTheDocument();
    });

    it("speaks Spanish to a Spanish-reading patient", () => {
        render(<TranslationNote copy={es} modelId="gemini-test" />);
        fireEvent.click(screen.getByRole("button", { name: "Acerca de esta traducción" }));
        expect(screen.getByText("Esta traducción es automática")).toBeInTheDocument();
        expect(screen.getByText(/La hizo una computadora, no una persona/)).toBeInTheDocument();
        expect(screen.getByText("La hizo el modelo gemini-test.")).toBeInTheDocument();
        expect(screen.getByText(/El mensaje original es el que cuenta/)).toBeInTheDocument();
    });

    it("closes again, returning the patient to their messages", () => {
        render(<TranslationNote copy={en} modelId="gemini-test" />);
        fireEvent.click(screen.getByRole("button", { name: "About this translation" }));
        fireEvent.keyDown(document, { key: "Escape" });
        expect(screen.queryByText(/A computer made it/)).not.toBeInTheDocument();
    });
});
