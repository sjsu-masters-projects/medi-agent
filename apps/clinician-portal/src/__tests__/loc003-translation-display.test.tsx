import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
    OriginalText,
    TranslationBadge,
    TranslationInfo,
    UntranslatedBadge,
} from "@/components/ui/translation-note";
import { PatientPhonePreview } from "@/components/features/patient-preview";
import {
    EvidenceGlossLine,
    glossFor,
    mayNeedGloss,
    normaliseExcerpt,
    useEvidenceGlosses,
} from "@/components/features/evidence-gloss";
import {
    factFields,
    ExtractedFactCandidates,
    isFactTranslatedFromSpanish,
    isFactUntranslated,
} from "@/components/features/extracted-fact-candidates";
import { ChatTranscript } from "@/components/features/chat-transcript";
import {
    confirmedTranslationFor,
    sendBlocker,
    type PreviewState,
} from "@/components/features/reply-preview";
import {
    fetchEvidenceGlosses,
    translateTranscriptMessage,
    type EvidenceGloss,
    type ExtractedDocumentFact,
} from "@/services/clinicians";
import { ChatRole } from "@/types";

vi.mock("@/services/clinicians", () => ({
    fetchEvidenceGlosses: vi.fn(),
    translateTranscriptMessage: vi.fn(),
}));

const glossApi = vi.mocked(fetchEvidenceGlosses);
const translateApi = vi.mocked(translateTranscriptMessage);

beforeEach(() => {
    glossApi.mockReset();
    translateApi.mockReset();
});
afterEach(cleanup);

/* ── Item 5: "may contain errors" and the model behind the text ─────────── */

describe("translation provenance", () => {
    it("labels English patient preview as translated from Spanish", () => {
        render(<PatientPhonePreview locale="en-US" wording={{ title: "Drink water" }} translated />);
        expect(screen.getByText("Translated from Spanish")).toBeInTheDocument();
        expect(screen.queryByText("Translated from English")).not.toBeInTheDocument();
    });
    it("always offers the model's caveat beside translated text", async () => {
        render(<TranslationBadge modelId="gemini-test" />);
        expect(screen.getByText("Translated from Spanish")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: /may contain errors/i }));
        expect(await screen.findByText(/automatic and may contain errors/i)).toBeInTheDocument();
        expect(screen.getByText(/Produced by gemini-test/)).toBeInTheDocument();
    });

    it("says so plainly when no model was recorded, rather than implying one", async () => {
        render(<TranslationInfo />);
        fireEvent.click(screen.getByRole("button", { name: /may contain errors/i }));
        expect(await screen.findByText(/was not recorded/i)).toBeInTheDocument();
    });

    it("marks offline-stub wording as never approvable for a patient", async () => {
        render(<TranslationInfo modelId="offline-translation-stub" />);
        fireEvent.click(screen.getByRole("button", { name: /may contain errors/i }));
        expect(await screen.findByText(/never approve this as patient-facing wording/i)).toBeInTheDocument();
    });

    it("keeps the caveat reachable by keyboard, not hover alone", async () => {
        render(<TranslationInfo modelId="gemini-test" />);
        const trigger = screen.getByRole("button", { name: /may contain errors/i });
        expect(trigger).toHaveAttribute("aria-expanded", "false");
        fireEvent.click(trigger);
        expect(trigger).toHaveAttribute("aria-expanded", "true");
        fireEvent.keyDown(document, { key: "Escape" });
        await waitFor(() => expect(trigger).toHaveAttribute("aria-expanded", "false"));
    });
});

/* ── Item 6: untranslated facts, with the original one tap away ─────────── */

function fact(changes: Partial<ExtractedDocumentFact> = {}): ExtractedDocumentFact {
    return {
        id: "fact-1",
        fact_type: "obligation",
        value: { description: "Tome un vaso de agua con cada comida", frequency: "cada comida" },
        review_state: "pending_review",
        ...changes,
    } as ExtractedDocumentFact;
}

describe("untranslated facts", () => {
    it("keeps translation disclosures separate from evidence selection", () => {
        const select = vi.fn();
        const { container } = render(<ExtractedFactCandidates facts={[fact({
            display_locale: "es-MX", display_value: { description: "Drink water" },
        })]} selectedFactId={null} onSelect={select} />);
        expect(container.querySelector("button button")).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: /may contain errors/i }));
        expect(select).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: /Select.*evidence/i }));
        expect(select).toHaveBeenCalledWith("fact-1");
    });
    it("treats a Spanish fact with no English display fields as untranslated", () => {
        expect(isFactUntranslated(fact({ display_locale: "es-MX" }))).toBe(true);
        expect(isFactUntranslated(fact({ display_locale: "es-MX", display_value: {} }))).toBe(true);
    });

    it("does not call a translated or an English fact untranslated", () => {
        const translated = fact({ display_locale: "es-MX", display_value: { description: "Drink water" } });
        expect(isFactUntranslated(translated)).toBe(false);
        expect(isFactTranslatedFromSpanish(translated)).toBe(true);
        expect(isFactUntranslated(fact({ display_locale: "en-US" }))).toBe(false);
    });

    it("says why, and points at the source, instead of leaving Spanish looking like English", async () => {
        render(<UntranslatedBadge />);
        expect(screen.getByText("Not translated")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: /why this was not translated/i }));
        expect(await screen.findByText(/did not pass its safety check/i)).toBeInTheDocument();
        expect(screen.getByText(/bilingual colleague/i)).toBeInTheDocument();
    });

    it("keeps the printed original beside each translated field", () => {
        const fields = factFields(
            fact({ display_locale: "es-MX", display_value: { description: "Drink a glass of water with each meal" } }),
        );
        const description = fields.find((field) => field.key === "description");
        expect(description?.value).toBe("Drink a glass of water with each meal");
        expect(description?.original).toBe("Tome un vaso de agua con cada comida");
        // A field the model left alone has nothing to reveal.
        expect(fields.find((field) => field.key === "frequency")?.original).toBeUndefined();
    });

    it("hides the original until it is asked for, then shows it in Spanish", () => {
        render(<OriginalText>Tome un vaso de agua</OriginalText>);
        const toggle = screen.getByRole("button", { name: /show original Spanish/i });
        const region = screen.getByText("Tome un vaso de agua");
        expect(region).toHaveAttribute("lang", "es-MX");
        expect(region).not.toBeVisible();
        fireEvent.click(toggle);
        expect(region).toBeVisible();
        expect(screen.getByRole("button", { name: /hide original Spanish/i })).toBeInTheDocument();
    });
});

/* ── Item 1: the phone-style patient preview ─────────────────────────────── */

const WORDING = { title: "Caminar 20 minutos", instructions: "Camina después de la cena", frequency: "a diario" };

describe("patient phone preview", () => {
    it("shows the patient's own wording in their language", () => {
        render(<PatientPhonePreview locale="es-MX" wording={WORDING} />);
        expect(screen.getByText("Caminar 20 minutos")).toBeInTheDocument();
        expect(screen.getByText("Camina después de la cena")).toBeInTheDocument();
        expect(screen.getByText("a diario")).toBeInTheDocument();
        expect(screen.getByText("Español (México)", { exact: false })).toBeInTheDocument();
    });

    it("labels the frame in the patient's language, using the app's approved chrome", () => {
        render(<PatientPhonePreview locale="es-MX" wording={WORDING} />);
        expect(screen.getByText("Hoy")).toBeInTheDocument();
        expect(screen.getByText("Marcar como completada")).toBeInTheDocument();
        cleanup();
        render(<PatientPhonePreview locale="en-US" wording={{ title: "Walk 20 minutes" }} />);
        expect(screen.getByText("Today")).toBeInTheDocument();
        expect(screen.getByText("Mark as Done")).toBeInTheDocument();
    });

    it("marks a translated preview as AI wording, with the model behind it", async () => {
        render(<PatientPhonePreview locale="es-MX" modelId="gemini-test" translated wording={WORDING} />);
        expect(screen.getByText("Translated from English")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: /may contain errors/i }));
        expect(await screen.findByText(/Produced by gemini-test/)).toBeInTheDocument();
    });

    it("does not mark source wording as a translation", () => {
        render(<PatientPhonePreview locale="es-MX" wording={WORDING} />);
        expect(screen.queryByText(/Translated from/)).not.toBeInTheDocument();
    });

    it("asks for the wording instead of showing an empty phone", () => {
        render(<PatientPhonePreview locale="es-MX" wording={{ title: "  ", instructions: "" }} />);
        expect(screen.getByText(/Write the Español \(México\) wording/)).toBeInTheDocument();
    });

    it("never offers the preview button as a real control", () => {
        render(<PatientPhonePreview locale="en-US" wording={{ title: "Walk" }} />);
        expect(screen.queryByRole("button", { name: "Mark as Done" })).not.toBeInTheDocument();
    });
});

/* ── Item 2: English glosses beside original excerpts ───────────────────── */

const SPANISH_EXCERPT = "Tome 1 tableta de Metformina 500 mg dos veces al día";

function gloss(changes: Partial<EvidenceGloss> = {}): EvidenceGloss {
    return {
        excerpt_id: "address-1",
        excerpt: SPANISH_EXCERPT,
        gloss: "Take 1 tablet of Metformina 500 mg twice daily",
        model_id: "gemini-test",
        ...changes,
    };
}

function GlossHarness({ excerpts, patientId = "patient-1" }: { excerpts: Array<string | null | undefined>; patientId?: string }) {
    const glosses = useEvidenceGlosses(patientId, excerpts);
    return (
        <>
            {excerpts.map((excerpt, index) => (
                <div key={index}>
                    <span>{excerpt}</span>
                    <EvidenceGlossLine gloss={glossFor(glosses, excerpt)} />
                </div>
            ))}
        </>
    );
}

describe("evidence glosses", () => {
    it("retries canceled in-flight excerpts when the list grows", async () => {
        glossApi.mockReturnValueOnce(new Promise(() => {}));
        glossApi.mockResolvedValue({ glosses: [gloss()] });
        const { rerender } = render(<GlossHarness excerpts={[SPANISH_EXCERPT]} />);
        await waitFor(() => expect(glossApi).toHaveBeenCalledTimes(1));
        rerender(<GlossHarness excerpts={[SPANISH_EXCERPT, "No tome agua"]} />);
        expect(await screen.findByText("Take 1 tablet of Metformina 500 mg twice daily")).toBeInTheDocument();
        expect(glossApi.mock.calls[1][1]).toContain(SPANISH_EXCERPT);
    });

    it("does not strand an excerpt after StrictMode cleanup", async () => {
        glossApi.mockResolvedValue({ glosses: [gloss()] });
        render(<StrictMode><GlossHarness excerpts={[SPANISH_EXCERPT]} /></StrictMode>);
        expect(await screen.findByText("Take 1 tablet of Metformina 500 mg twice daily")).toBeInTheDocument();
    });

    it("does not reuse the previous patient's displayed gloss", async () => {
        glossApi.mockResolvedValueOnce({ glosses: [gloss()] });
        const { rerender } = render(<GlossHarness excerpts={[SPANISH_EXCERPT]} />);
        await screen.findByText("In English");
        glossApi.mockReturnValue(new Promise(() => {}));
        rerender(<GlossHarness excerpts={[SPANISH_EXCERPT]} patientId="patient-2" />);
        expect(screen.queryByText("In English")).not.toBeInTheDocument();
        await waitFor(() => expect(glossApi).toHaveBeenLastCalledWith("patient-2", [SPANISH_EXCERPT]));
    });
    it("only asks about text that reads as Spanish", () => {
        expect(mayNeedGloss(SPANISH_EXCERPT)).toBe(true);
        expect(mayNeedGloss("Take 1 tablet twice daily by mouth")).toBe(false);
        expect(mayNeedGloss("   ")).toBe(false);
        expect(mayNeedGloss(null)).toBe(false);
    });

    it("treats whitespace differences as the same excerpt", () => {
        expect(normaliseExcerpt("Tome  1\n tableta")).toBe("Tome 1 tableta");
    });

    it("shows the gloss under the untouched original", async () => {
        glossApi.mockResolvedValue({ glosses: [gloss()] });
        render(<GlossHarness excerpts={[SPANISH_EXCERPT]} />);
        expect(screen.getByText(SPANISH_EXCERPT)).toBeInTheDocument();
        expect(await screen.findByText("Take 1 tablet of Metformina 500 mg twice daily")).toBeInTheDocument();
        expect(screen.getByText("In English")).toBeInTheDocument();
        // The excerpt itself is never replaced.
        expect(screen.getByText(SPANISH_EXCERPT)).toBeInTheDocument();
    });

    it("asks once for an excerpt quoted several times", async () => {
        glossApi.mockResolvedValue({ glosses: [gloss()] });
        render(<GlossHarness excerpts={[SPANISH_EXCERPT, SPANISH_EXCERPT, `  ${SPANISH_EXCERPT}  `]} />);
        await waitFor(() => expect(glossApi).toHaveBeenCalledTimes(1));
        expect(glossApi.mock.calls[0][1]).toEqual([SPANISH_EXCERPT]);
    });

    it("never asks about English excerpts", async () => {
        render(<GlossHarness excerpts={["Take 1 tablet twice daily by mouth"]} />);
        await waitFor(() => expect(glossApi).not.toHaveBeenCalled());
    });

    it("leaves the original alone when the gloss fails", async () => {
        glossApi.mockRejectedValue(new Error("unavailable"));
        render(<GlossHarness excerpts={[SPANISH_EXCERPT]} />);
        await waitFor(() => expect(glossApi).toHaveBeenCalled());
        expect(screen.getByText(SPANISH_EXCERPT)).toBeInTheDocument();
        expect(screen.queryByText("In English")).not.toBeInTheDocument();
    });

    it("says the Spanish is the evidence, not the gloss", async () => {
        glossApi.mockResolvedValue({ glosses: [gloss()] });
        render(<GlossHarness excerpts={[SPANISH_EXCERPT]} />);
        await screen.findByText("In English");
        fireEvent.click(screen.getByRole("button", { name: /may contain errors/i }));
        expect(await screen.findByText(/source evidence and is never changed/i)).toBeInTheDocument();
    });
});

/* ── Item 3: the Nora transcript, translated ─────────────────────────────── */

const TRANSCRIPT_TIME = "2026-10-19T10:00:00Z";

describe("Nora transcript translation", () => {
    it("shows an English translation under a Spanish turn, not over it", () => {
        render(
            <ChatTranscript
                messages={[{
                    id: "m1",
                    role: ChatRole.USER,
                    content: "Me duele la cabeza desde ayer",
                    created_at: TRANSCRIPT_TIME,
                    translation: "My head has hurt since yesterday",
                    translation_locale: "en-US",
                    translation_guard_passed: true,
                    translation_model_id: "gemini-test",
                }]}
                patientId="patient-1"
            />,
        );
        expect(screen.getByText("Me duele la cabeza desde ayer")).toBeInTheDocument();
        expect(screen.getByText("My head has hurt since yesterday")).toBeInTheDocument();
        expect(screen.getByText("Translated from Spanish")).toBeInTheDocument();
    });

    it("asks for the turns the read marked pending, and folds in the answer", async () => {
        translateApi.mockResolvedValue({
            message_id: "m1",
            translation: "My head has hurt since yesterday",
            translation_locale: "en-US",
            translation_guard_passed: true,
            translation_pending: false,
            translation_model_id: "gemini-test",
        });
        render(
            <ChatTranscript
                messages={[{
                    id: "m1",
                    role: ChatRole.USER,
                    content: "Me duele la cabeza desde ayer",
                    created_at: TRANSCRIPT_TIME,
                    translation_pending: true,
                }]}
                patientId="patient-1"
            />,
        );
        expect(await screen.findByText("My head has hurt since yesterday")).toBeInTheDocument();
        expect(translateApi).toHaveBeenCalledWith("patient-1", "m1");
    });

    it("asks for each turn once, however often the component re-renders", async () => {
        translateApi.mockResolvedValue({
            message_id: "m1",
            translation: null,
            translation_locale: "en-US",
            translation_guard_passed: null,
            translation_pending: false,
        });
        const messages = [{
            id: "m1",
            role: ChatRole.USER,
            content: "Me duele la cabeza",
            created_at: TRANSCRIPT_TIME,
            translation_pending: true,
        }];
        const { rerender } = render(<ChatTranscript messages={messages} patientId="patient-1" />);
        await waitFor(() => expect(translateApi).toHaveBeenCalledTimes(1));
        rerender(<ChatTranscript messages={messages} patientId="patient-1" />);
        rerender(<ChatTranscript messages={messages} patientId="patient-1" />);
        expect(translateApi).toHaveBeenCalledTimes(1);
    });

    it("never shows a translation whose guard failed", () => {
        render(
            <ChatTranscript
                messages={[{
                    id: "m1",
                    role: ChatRole.USER,
                    content: "Tomo 500 mg",
                    created_at: TRANSCRIPT_TIME,
                    translation: "I take 250 mg",
                    translation_locale: "en-US",
                    translation_guard_passed: false,
                }]}
                patientId="patient-1"
            />,
        );
        expect(screen.queryByText("I take 250 mg")).not.toBeInTheDocument();
        expect(screen.getByText(/translation unavailable for this message/i)).toBeInTheDocument();
    });

    it("does not translate when there is no patient to ask about", async () => {
        render(
            <ChatTranscript
                messages={[{
                    id: "m1",
                    role: ChatRole.USER,
                    content: "Me duele la cabeza",
                    created_at: TRANSCRIPT_TIME,
                    translation_pending: true,
                }]}
            />,
        );
        await waitFor(() => expect(translateApi).not.toHaveBeenCalled());
        expect(screen.getByText("Me duele la cabeza")).toBeInTheDocument();
    });
});

/* ── Item 4: the reply preview gate ──────────────────────────────────────── */

const BODY = "Take 1 tablet of Metformin 500 mg twice daily";

function ready(overrides: Partial<PreviewState & { result: unknown }> = {}): PreviewState {
    return {
        kind: "ready",
        body: BODY,
        result: {
            needed: true,
            target_locale: "es-MX",
            translation: "Toma 1 tableta de Metformin 500 mg dos veces al día",
            back_translation: "Take 1 tablet of Metformin 500 mg twice daily",
            guard_passed: true,
            guard_failure_code: null,
            model_id: "gemini-test",
        },
        ...overrides,
    } as PreviewState;
}

describe("reply preview gate", () => {
    it("never confirms offline stub wording or missing back-translation", () => {
        for (const overrides of [{ model_id: "offline-translation-stub" }, { back_translation: null }]) {
            const state = ready();
            if (state.kind !== "ready") throw new Error("Expected ready fixture");
            const blocked = { ...state, result: { ...state.result, ...overrides } };
            expect(sendBlocker(blocked, BODY, true)).not.toBeNull();
            expect(confirmedTranslationFor(blocked, BODY, true)).toBeNull();
        }
    });
    it("asks for a preview before the first send", () => {
        expect(sendBlocker({ kind: "idle" }, BODY, false)).toMatch(/Preview what the patient will receive/);
    });

    it("waits for the confirmation once the wording is on screen", () => {
        expect(sendBlocker(ready(), BODY, false)).toMatch(/Confirm the wording/);
        expect(sendBlocker(ready(), BODY, true)).toBeNull();
    });

    it("invalidates a preview of text that has since changed", () => {
        expect(sendBlocker(ready(), `${BODY} with water`, true)).toMatch(/changed/);
        expect(confirmedTranslationFor(ready(), `${BODY} with water`, true)).toBeNull();
    });

    it("does not gate a patient who reads the language the clinician wrote in", () => {
        const state = ready({ result: { needed: false, target_locale: "en-US", translation: null, back_translation: null, guard_passed: null, guard_failure_code: null, model_id: null } });
        expect(sendBlocker(state, BODY, false)).toBeNull();
        expect(confirmedTranslationFor(state, BODY, false)).toBeNull();
    });

    it("lets a guard-rejected reply go in English rather than blocking the clinician", () => {
        const state = ready({ result: { needed: true, target_locale: "es-MX", translation: "Toma 250 mg", back_translation: null, guard_passed: false, guard_failure_code: "numbers_changed", model_id: "gemini-test" } });
        expect(sendBlocker(state, BODY, false)).toBeNull();
        // And the rejected wording is never sent as confirmed.
        expect(confirmedTranslationFor(state, BODY, true)).toBeNull();
    });

    it("sends exactly the wording that was confirmed", () => {
        expect(confirmedTranslationFor(ready(), BODY, true)).toEqual({
            text: "Toma 1 tableta de Metformin 500 mg dos veces al día",
            locale: "es-MX",
            model_id: "gemini-test",
        });
    });

    it("sends nothing as confirmed while the box is unticked", () => {
        expect(confirmedTranslationFor(ready(), BODY, false)).toBeNull();
    });

    it("holds the send while a preview is still being prepared", () => {
        expect(sendBlocker({ kind: "loading" }, BODY, false)).toMatch(/Preparing/);
    });

    it("does not lock a clinician out of messaging when the preview fails", () => {
        // Decision 3: an unavailable translation delivers the English, it does not refuse.
        expect(sendBlocker({ kind: "error" }, BODY, false)).toBeNull();
        expect(confirmedTranslationFor({ kind: "error" }, BODY, true)).toBeNull();
    });

    it("does not gate an empty draft", () => {
        expect(sendBlocker({ kind: "idle" }, "   ", false)).toBeNull();
    });
});
