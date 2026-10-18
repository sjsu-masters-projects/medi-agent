import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
    BackTranslationPanel,
    BilingualWording,
    spanishKey,
    verificationBlocker,
    type BackCheck,
} from "@/components/features/care-plan-wording";
import { factFields, isFactTranslatedFromSpanish } from "@/components/features/extracted-fact-candidates";
import { fetchBackTranslation, type BackTranslationResult, type CarePlanItem, type ExtractedDocumentFact } from "@/services/clinicians";

vi.mock("@/services/clinicians", () => ({ fetchBackTranslation: vi.fn() }));

const ok = (title = "Walk"): BackTranslationResult => ({
    back_translation: { title, instructions: "Walk 20 minutes", frequency: "daily" },
    guards: { numbers_match: true, medication_names_match: true },
});
const es = (title: string) => ({ title, instructions: "Camina 20 minutos", frequency: "a diario" });

function panel(wording: ReturnType<typeof es>, unsaved = false, onCheck?: (id: string, check: BackCheck) => void) {
    return <BackTranslationPanel itemId="item-1" onCheck={onCheck} patientId="p" planId="plan" spanishWording={wording} unsaved={unsaved} />;
}

const mocked = vi.mocked(fetchBackTranslation);
beforeEach(() => mocked.mockReset());
afterEach(cleanup);

describe("BackTranslationPanel", () => {
    it("fetches the saved wording once, not on every keystroke, and says so while edits are unsaved", async () => {
        mocked.mockResolvedValue(ok());
        const { rerender } = render(panel(es("Caminar")));
        expect(await screen.findByText(/Title:/)).toBeInTheDocument();
        expect(mocked).toHaveBeenCalledTimes(1);

        rerender(panel(es("Caminar r"), true));
        rerender(panel(es("Caminar rá"), true));
        rerender(panel(es("Caminar rápido"), true));
        expect(mocked).toHaveBeenCalledTimes(1);
        // The saved version's result stays visible, labelled as such.
        expect(screen.getByText("Translation shown is for the saved version. Save your changes to check the new Spanish.", { exact: false })).toBeInTheDocument();

        // After a successful save the new saved wording is fetched.
        rerender(panel(es("Caminar rápido"), false));
        await waitFor(() => expect(mocked).toHaveBeenCalledTimes(2));
    });

    it("clears the old result while a new one loads and ignores an out-of-order response", async () => {
        let resolveFirst: (value: BackTranslationResult) => void = () => undefined;
        mocked.mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }));
        mocked.mockResolvedValueOnce(ok("Second"));
        const { rerender } = render(panel(es("Caminar")));
        expect(screen.getByText("Loading back-translation…")).toBeInTheDocument();

        // A save changes the saved wording while the first request is still in flight.
        rerender(panel(es("Caminar rápido")));
        expect(await screen.findByText(/Second/)).toBeInTheDocument();

        await act(async () => { resolveFirst(ok("First (stale)")); });
        expect(screen.queryByText(/First \(stale\)/)).not.toBeInTheDocument();
        expect(screen.getByText(/Second/)).toBeInTheDocument();
    });

    it("offers a retry after an error and reports the state to the attestation", async () => {
        mocked.mockRejectedValueOnce(new Error("down"));
        mocked.mockResolvedValueOnce(ok());
        const onCheck = vi.fn();
        render(panel(es("Caminar"), false, onCheck));
        fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
        await screen.findByText(/Title:/);
        const states = onCheck.mock.calls.map(([, check]) => check.state);
        expect(states).toContain("error");
        expect(onCheck).toHaveBeenLastCalledWith("item-1", { state: "ready", guardsOk: true, key: spanishKey(es("Caminar")) });
    });

    it("announces loading and results in a polite live region", async () => {
        mocked.mockResolvedValue(ok());
        render(panel(es("Caminar")));
        expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
        await screen.findByText(/Numbers match/);
    });

    it("reports failed guards", async () => {
        mocked.mockResolvedValue({ ...ok(), guards: { numbers_match: false, medication_names_match: true } });
        const onCheck = vi.fn();
        render(panel(es("Caminar"), false, onCheck));
        await screen.findByText(/Numbers differ/);
        expect(onCheck).toHaveBeenLastCalledWith("item-1", expect.objectContaining({ state: "ready", guardsOk: false }));
    });
});

describe("verificationBlocker", () => {
    const item = {
        id: "i", category: "movement", title: "Walk", instructions: "Walk 20 minutes", frequency: "daily",
        schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false, source_locale: "en-US",
        wording: {
            "en-US": { title: "Walk", instructions: "Walk 20 minutes", frequency: "daily" },
            "es-MX": es("Caminar"),
        },
    } as unknown as CarePlanItem;
    const key = spanishKey(item.wording?.["es-MX"]);

    it.each([
        ["no check yet", undefined, false, "Back-translation is loading"],
        ["loading", { state: "loading", guardsOk: false, key }, false, "Back-translation is loading"],
        ["a check of other wording", { state: "ready", guardsOk: true, key: "other" }, false, "Back-translation is loading"],
        ["error", { state: "error", guardsOk: false, key }, false, "Back-translation unavailable — retry"],
        ["failed guards", { state: "ready", guardsOk: false, key }, false, "Numbers or medication names differ — fix the Spanish"],
        ["unsaved edits", { state: "ready", guardsOk: true, key }, true, "Save your changes first"],
        ["all clear", { state: "ready", guardsOk: true, key }, false, null],
    ] as const)("%s", (_name, check, unsaved, expected) => {
        expect(verificationBlocker(item, check as BackCheck | undefined, unsaved)).toBe(expected);
    });
});

describe("BilingualWording", () => {
    it("shows the back-translation card under the Spanish wording and passes edits through", async () => {
        mocked.mockResolvedValue(ok());
        const onChange = vi.fn();
        const item = {
            id: "item-1", category: "movement", title: "Walk", instructions: "Walk 20 minutes", frequency: "daily",
            schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false, source_locale: "en-US",
            wording: { "en-US": { title: "Walk", instructions: "Walk 20 minutes", frequency: "daily" }, "es-MX": es("Caminar") },
            wording_origin: { "en-US": "source", "es-MX": "ai_draft" },
        } as unknown as CarePlanItem;
        render(<BilingualWording busy={false} fieldClass="" item={item} onChange={onChange} onTranslate={() => undefined}
            onWriteManually={() => undefined} patientId="p" patientLocale="es-MX" planId="plan" unsaved={false} />);
        expect(await screen.findByText("English back-translation")).toBeInTheDocument();
        expect(screen.getByText("AI translation · check it")).toBeInTheDocument();
        fireEvent.change(screen.getAllByRole("textbox", { name: "Title" })[1], { target: { value: "Caminar mas" } });
        expect(onChange).toHaveBeenCalledWith("es-MX", "title", "Caminar mas");
    });
});

describe("fact display helpers", () => {
    const fact = (over: Partial<ExtractedDocumentFact>): ExtractedDocumentFact => ({
        id: "f", fact_type: "medication", value: { name: "Losartán", instructions: "tomar con agua", dosage: "50 mg" },
        review_state: "pending", ...over,
    });
    it("prefers the English display text field by field and keeps printed values", () => {
        const fields = factFields(fact({ display_value: { instructions: "take with water" }, display_locale: "es-MX" }));
        const byKey = Object.fromEntries(fields.map((f) => [f.key, f.value]));
        expect(byKey.instructions).toBe("take with water");
        expect(byKey.name).toBe("Losartán");
        expect(byKey.dosage).toBe("50 mg");
    });
    it("ignores a blank override", () => {
        const fields = factFields(fact({ display_value: { instructions: "  " }, display_locale: "es-MX" }));
        expect(fields.find((f) => f.key === "instructions")?.value).toBe("tomar con agua");
    });
    it("recognises a fact translated from Spanish only with a locale and display fields", () => {
        expect(isFactTranslatedFromSpanish(fact({ display_value: { instructions: "x" }, display_locale: "es-MX" }))).toBe(true);
        expect(isFactTranslatedFromSpanish(fact({ display_value: {}, display_locale: "es-MX" }))).toBe(false);
        expect(isFactTranslatedFromSpanish(fact({ display_value: { instructions: "x" }, display_locale: "en-US" }))).toBe(false);
        expect(isFactTranslatedFromSpanish(fact({ display_value: null, display_locale: "es-MX" }))).toBe(false);
    });
});
