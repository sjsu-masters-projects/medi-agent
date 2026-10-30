import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Form3500PreviewDialog, Form3500PreviewView } from "@/components/features/form-3500-preview";
import type { Form3500Preview, Form3500PreviewItem } from "@/services/clinicians";

const { fetchForm3500PreviewMock } = vi.hoisted(() => ({ fetchForm3500PreviewMock: vi.fn() }));
vi.mock("@/services/clinicians", async (importOriginal) => ({
    ...(await importOriginal<typeof import("@/services/clinicians")>()),
    fetchForm3500Preview: fetchForm3500PreviewMock,
}));

function item(overrides: Partial<Form3500PreviewItem>): Form3500PreviewItem {
    return { item: "A1", label: "Patient identifier", path: "section_a.identifier", value: null, provenance: [], missingForApproval: [], ...overrides };
}

function makePreview(overrides: Partial<Form3500Preview> = {}): Form3500Preview {
    return {
        draftId: "draft-1",
        status: "draft",
        sections: [
            {
                id: "A",
                title: "Patient information",
                notCompletedByMediAgent: false,
                items: [
                    item({ value: "SP-K7QD", provenance: [{ kind: "record", sourceType: "draft", attribution: null, citation: null }] }),
                    item({ item: "A4", label: "Weight", path: "section_a.weight_value" }),
                ],
            },
            {
                id: "B",
                title: "Adverse event, product problem",
                notCompletedByMediAgent: false,
                items: [
                    item({ item: "B3", label: "Date of event", path: "section_b.event_date", value: "02-Oct-2026" }),
                    item({
                        item: "B5",
                        label: "Describe event, problem or product use/medication error",
                        path: "section_b.narrative",
                        value: "Dizziness after starting the inhaler",
                        provenance: [
                            { kind: "ai_extracted", sourceType: "ai", attribution: null, citation: null },
                            { kind: "patient_confirmed", sourceType: "patient_follow_up", attribution: null, citation: null },
                        ],
                    }),
                ],
            },
            { id: "C", title: "Product availability", notCompletedByMediAgent: true, items: [] },
            {
                id: "D",
                title: "Suspect products",
                notCompletedByMediAgent: false,
                items: [
                    item({
                        item: "D1",
                        label: "Product name",
                        path: "section_d.product_1.name",
                        value: "fluticasone/salmeterol inhaler",
                        provenance: [{ kind: "clinician_edited", sourceType: null, attribution: null, citation: null }],
                    }),
                ],
            },
            { id: "E", title: "Suspect medical device", notCompletedByMediAgent: true, items: [] },
            { id: "F", title: "Other (concomitant) medical products", notCompletedByMediAgent: false, items: [] },
            {
                id: "G",
                title: "Reporter",
                notCompletedByMediAgent: false,
                items: [
                    item({ item: "G3", label: "Occupation", path: "section_g.occupation" }),
                    // Marked by the item's own gate codes, not only by the summary list.
                    item({ item: "G2", label: "Health professional", path: "section_g.health_professional", missingForApproval: ["health_professional_missing"] }),
                ],
            },
        ],
        missingForApproval: [
            { path: "section_b.event_date", code: "event_date_unconfirmed" },
            { path: "section_g.occupation", code: "occupation_missing" },
            { path: "mediagent_review.reportability_rationale", code: "reportability_rationale_missing" },
        ],
        mediagentReview: { naranjoScore: 3, causality: "Possible", reportabilityRationale: "" },
        legacy: {},
        template: { revision: "09/2025", expires: "2027-09-30", maySuperseded: false },
        ...overrides,
    };
}

describe("Form3500PreviewView", () => {
    it("lays out sections A to G in form order with C and E not completed", () => {
        render(<Form3500PreviewView preview={makePreview()} />);
        const headings = screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent);
        expect(headings.slice(0, 7)).toEqual([
            "A. Patient information",
            "B. Adverse event, product problem",
            "C. Product availability",
            "D. Suspect products",
            "E. Suspect medical device",
            "F. Other (concomitant) medical products",
            "G. Reporter",
        ]);
        expect(within(screen.getByRole("region", { name: "C. Product availability" })).getByText("Not completed by MediAgent")).toBeInTheDocument();
        expect(within(screen.getByRole("region", { name: "E. Suspect medical device" })).getByText("Not completed by MediAgent")).toBeInTheDocument();
    });

    it("shows blank items as Not provided and wraps long values", () => {
        render(<Form3500PreviewView preview={makePreview()} />);
        const sectionA = screen.getByRole("region", { name: "A. Patient information" });
        expect(within(sectionA).getByText("SP-K7QD")).toBeInTheDocument();
        expect(within(sectionA).getByText("Not provided")).toBeInTheDocument();
        expect(within(sectionA).getByText("A4")).toHaveClass("font-mono");
        expect(screen.getByText("Dizziness after starting the inhaler").className).toContain("[overflow-wrap:anywhere]");
    });

    it("labels items missing for approval with text while the draft awaits approval", () => {
        render(<Form3500PreviewView preview={makePreview()} />);
        const sectionB = screen.getByRole("region", { name: "B. Adverse event, product problem" });
        const eventRow = within(sectionB).getByText("Date of event").closest("div")!;
        expect(within(eventRow).getByText("Missing for approval")).toBeInTheDocument();
        expect(within(screen.getByRole("region", { name: "G. Reporter" })).getAllByText("Missing for approval")).toHaveLength(2);
        const summary = screen.getByRole("region", { name: "Missing for approval" });
        expect(within(summary).getByText("B3 Confirm the best-estimate date of event")).toBeInTheDocument();
        // The review rationale is flagged in its own panel.
        const review = screen.getByRole("region", { name: "MediAgent review (not part of Form 3500)" });
        expect(within(review).getByText("Missing for approval")).toBeInTheDocument();
    });

    it("shows no missing labels once the draft is approved", () => {
        render(<Form3500PreviewView preview={makePreview({ status: "reviewed" })} />);
        expect(screen.queryByText("Missing for approval")).not.toBeInTheDocument();
    });

    it("marks provenance truthfully, with the AI chip only on AI-extracted content", () => {
        render(<Form3500PreviewView preview={makePreview()} />);
        const sectionB = screen.getByRole("region", { name: "B. Adverse event, product problem" });
        expect(within(sectionB).getByText("AI-extracted")).toBeInTheDocument();
        expect(within(sectionB).getByText("Patient-confirmed")).toBeInTheDocument();
        expect(screen.getAllByText("AI-extracted")).toHaveLength(1);
        expect(within(screen.getByRole("region", { name: "D. Suspect products" })).getByText("Clinician edited")).toBeInTheDocument();
        expect(within(screen.getByRole("region", { name: "A. Patient information" })).getByText("Record")).toBeInTheDocument();
    });

    it("keeps the Naranjo review in a separate panel outside Form 3500", () => {
        render(<Form3500PreviewView preview={makePreview()} />);
        const review = screen.getByRole("region", { name: "MediAgent review (not part of Form 3500)" });
        expect(within(review).getByText("3")).toBeInTheDocument();
        expect(within(review).getByText("Possible")).toBeInTheDocument();
        for (const id of ["A", "B", "D", "G"]) {
            const section = screen.getAllByRole("region").find((region) => region.getAttribute("aria-labelledby") === `form-3500-section-${id}`)!;
            expect(within(section).queryByText(/Naranjo/)).not.toBeInTheDocument();
        }
    });

    it("contains no input controls", () => {
        const { container } = render(<Form3500PreviewView preview={makePreview()} />);
        expect(container.querySelectorAll("input, select, textarea, button")).toHaveLength(0);
    });

    it("warns when the vendored revision may be superseded and carries the fixed footer", () => {
        render(
            <Form3500PreviewView
                preview={makePreview({ template: { revision: "09/2025", expires: "2027-09-30", maySuperseded: true } })}
            />,
        );
        expect(screen.getByRole("note")).toHaveTextContent(/FDA may have published a newer revision/);
        expect(screen.getByText("Not submitted to FDA by MediAgent")).toBeInTheDocument();
    });

    it("shows earlier draft text that has no Form 3500 item", () => {
        render(<Form3500PreviewView preview={makePreview({ legacy: { "reporter.specialty": "Internal medicine" } })} />);
        const legacy = screen.getByRole("region", { name: "Earlier draft text with no Form 3500 item" });
        expect(within(legacy).getByText("Internal medicine")).toBeInTheDocument();
        // The stored key is labelled for people, including in the printed copy.
        expect(within(legacy).getByText("Reporter · Specialty")).toBeInTheDocument();
        expect(within(legacy).queryByText("reporter.specialty")).not.toBeInTheDocument();
    });
});

describe("Form3500PreviewDialog", () => {
    it("loads the preview in the shared modal and retries a failure", async () => {
        fetchForm3500PreviewMock
            .mockRejectedValueOnce(new Error("This MedWatch draft is no longer available."))
            .mockResolvedValueOnce(makePreview());
        render(<Form3500PreviewDialog draftId="draft-1" onClose={() => undefined} open />);
        const dialog = screen.getByRole("dialog", { name: "Form FDA 3500 preview" });
        expect(await within(dialog).findByText("Unable to load the Form 3500 preview")).toBeInTheDocument();
        fireEvent.click(within(dialog).getByRole("button", { name: "Try again" }));
        await waitFor(() => expect(within(dialog).getByRole("article", { name: "Form FDA 3500 preview" })).toBeInTheDocument());
        expect(fetchForm3500PreviewMock).toHaveBeenCalledWith("draft-1");
        expect(within(dialog).getByRole("button", { name: "Print preview" })).toBeEnabled();
        expect(dialog.querySelector(".ma-print-root")).not.toBeNull();
    });
});
