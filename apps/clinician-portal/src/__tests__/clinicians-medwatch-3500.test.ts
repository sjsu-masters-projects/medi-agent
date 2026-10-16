import { afterEach, describe, expect, it, vi } from "vitest";
import {
    amendMedWatchSubmission,
    approveMedWatchDraft,
    discardMedWatchDraft,
    downloadForm3500Pdf,
    fetchForm3500Preview,
    fetchForm3500PreviewPdf,
    fetchMedWatchDraft,
    fetchMedWatchDrafts,
    form3500PdfFilename,
    form3500TemplateInfo,
    MedWatchRequestError,
    recordMedWatchSubmission,
    updateMedWatchDraft,
} from "@/services/clinicians";
import { makeForm } from "./fixtures/medwatch";

vi.mock("@/services/auth-session", () => ({
    readStoredSession: () => ({ accessToken: "synthetic-token" }),
}));

const BASE = "http://localhost:8000/api/v1/clinicians/me/medwatch-drafts";
const DRAFT_ID = "abcdef12-3456-4789-8abc-def012345678";

function json(body: unknown, status = 200): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
    });
}

function draftResponse(overrides: Record<string, unknown> = {}) {
    return {
        id: DRAFT_ID,
        adr_assessment_id: "adr-1",
        patient_id: "patient-1",
        form_data: makeForm(),
        source_evidence: [],
        clinician_edited_fields: [],
        status: "submitted",
        revision: 4,
        export_version: "fda-3500-2025-09",
        created_at: "2026-10-09T10:00:00Z",
        updated_at: "2026-10-10T10:00:00Z",
        approved_at: "2026-10-09T18:00:00Z",
        missing_for_approval: [{ path: "section_g.occupation", code: "occupation_missing" }],
        name_warnings: [{ path: "section_b.narrative", kind: "patient_name" }],
        current_submission: {
            id: "submission-2",
            submitted_on: "2026-10-10",
            method: "fax",
            method_detail: null,
            fda_reference: null,
            recorded_by: "clinician-1",
            recorded_by_name: "Dr. Synthetic Clinician",
            created_at: "2026-10-11T10:00:00Z",
            amends_id: "submission-1",
            amend_reason: "Wrong method",
        },
        attestation: { version: "medwatch-3500-approval-v1", text: "Attestation." },
        template: { revision: "09/2025", expires: "2027-09-30", may_be_superseded: true },
        pdf_available: false,
        discarded_at: null,
        discard_reason: null,
        ...overrides,
    };
}

function stubFetch(response: Response) {
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

function sentBody(fetchMock: ReturnType<typeof vi.fn>) {
    return JSON.parse(String(fetchMock.mock.calls[0][1].body));
}

describe("MedWatch Form 3500 client", () => {
    afterEach(() => vi.unstubAllGlobals());

    it.each(["active", "submitted", "discarded"] as const)(
        "lists %s drafts with the gate, warnings, submission and attestation",
        async (state) => {
            const fetchMock = stubFetch(json({ items: [draftResponse()], total: 1 }));
            const [draft] = await fetchMedWatchDrafts(state);
            expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}?state=${state}`);
            expect(draft.missingForApproval).toEqual([
                { path: "section_g.occupation", code: "occupation_missing" },
            ]);
            expect(draft.nameWarnings).toEqual([{ path: "section_b.narrative", kind: "patient_name" }]);
            expect(draft.currentSubmission).toMatchObject({
                id: "submission-2",
                method: "fax",
                recordedByName: "Dr. Synthetic Clinician",
                amendsId: "submission-1",
            });
            expect(draft.submissionHistory).toHaveLength(1);
            expect(draft.attestation).toEqual({
                version: "medwatch-3500-approval-v1",
                text: "Attestation.",
            });
            expect(draft.template).toEqual({
                revision: "09/2025",
                expires: "2027-09-30",
                maySuperseded: true,
            });
            expect(draft.pdfAvailable).toBe(false);
        },
    );

    it("defaults the list to active and the template to the pinned record", async () => {
        const fetchMock = stubFetch(
            json({
                items: [
                    draftResponse({ template: undefined, current_submission: null, pdf_available: undefined }),
                ],
                total: 1,
            }),
        );
        const [draft] = await fetchMedWatchDrafts();
        // A response without `pdf_available` keeps the download control available.
        expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}?state=active`);
        expect(draft.currentSubmission).toBeNull();
        expect(draft.submissionHistory).toEqual([]);
        expect(draft.template).toMatchObject({ revision: "09/2025", expires: "2027-09-30" });
        expect(draft.pdfAvailable).toBe(true);
        expect(form3500TemplateInfo(null, new Date("2027-10-02T12:00:00Z")).maySuperseded).toBe(true);
        expect(form3500TemplateInfo(null, new Date("2027-09-30T12:00:00Z")).maySuperseded).toBe(false);
    });

    it("approves with the attestation version, D12 attestation and acknowledged warnings", async () => {
        const fetchMock = stubFetch(json(draftResponse({ status: "reviewed" })));
        await approveMedWatchDraft(DRAFT_ID, {
            approvalNote: "Reviewed.",
            expectedRevision: 4,
            attestationVersion: "medwatch-3500-approval-v1",
            nonSeriousAttested: true,
            acknowledgedWarnings: [{ path: "section_b.narrative", kind: "patient_name" }],
        });
        expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/${DRAFT_ID}/approve`);
        expect(fetchMock.mock.calls[0][1].method).toBe("POST");
        expect(sentBody(fetchMock)).toEqual({
            approval_note: "Reviewed.",
            expected_revision: 4,
            attested: true,
            attestation_version: "medwatch-3500-approval-v1",
            non_serious_attested: true,
            acknowledged_warnings: [{ path: "section_b.narrative", kind: "patient_name" }],
        });
    });

    it("maps the preview sections, provenance and template", async () => {
        stubFetch(
            json({
                draft_id: DRAFT_ID,
                status: "draft",
                sections: [
                    {
                        section: "B",
                        title: "Adverse event, product problem",
                        completion: "mediagent",
                        items: [
                            {
                                item: "B5",
                                label: "Describe event",
                                path: "section_b.narrative",
                                value: "Dizziness",
                                provenance: [
                                    { source_type: "ai_extracted_adr_evidence", attribution: "Chat" },
                                    { source_type: "patient_follow_up" },
                                    { source_type: "patient_symptom_report" },
                                    { kind: "clinician_edited" },
                                ],
                                missing_for_approval: ["narrative_missing"],
                            },
                        ],
                    },
                    { section: "C", title: "Product availability", completion: "not_completed_by_mediagent", items: [] },
                ],
                missing_for_approval: [],
                mediagent_review: { naranjo_score: 3, causality: "Possible", reportability_rationale: "R" },
                template: { revision: "09/2025", expires: "2027-09-30", may_be_superseded: false },
            }),
        );
        const preview = await fetchForm3500Preview(DRAFT_ID);
        expect(preview.sections[0].items[0].provenance.map((entry) => entry.kind)).toEqual([
            "ai_extracted",
            "patient_confirmed",
            "record",
            "clinician_edited",
        ]);
        expect(preview.sections[0].id).toBe("B");
        expect(preview.sections[0].notCompletedByMediAgent).toBe(false);
        expect(preview.sections[0].items[0].missingForApproval).toEqual(["narrative_missing"]);
        expect(preview.sections[1].notCompletedByMediAgent).toBe(true);
        expect(preview.mediagentReview.naranjoScore).toBe(3);
        expect(preview.template.maySuperseded).toBe(false);
    });

    it("downloads the PDF once as a blob under the server filename", async () => {
        const fetchMock = stubFetch(
            new Response("%PDF-1.7", {
                status: 200,
                headers: {
                    "Content-Type": "application/pdf",
                    "Content-Disposition": 'attachment; filename="fda-3500-abcdef12-not-submitted.pdf"',
                },
            }),
        );
        const file = await downloadForm3500Pdf(DRAFT_ID);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/${DRAFT_ID}/export.pdf`);
        expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer synthetic-token");
        expect(file.filename).toBe("fda-3500-abcdef12-not-submitted.pdf");
        expect(await file.blob.text()).toBe("%PDF-1.7");
    });

    it("fetches the watermarked preview with the bearer token and never as an export", async () => {
        const fetchMock = vi.fn().mockResolvedValue(
            new Response("%PDF-1.7", { status: 200, headers: { "Content-Type": "application/pdf" } }),
        );
        vi.stubGlobal("fetch", fetchMock);
        const blob = await fetchForm3500PreviewPdf(DRAFT_ID);
        expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/${DRAFT_ID}/preview.pdf`);
        expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer synthetic-token");
        expect(await blob.text()).toBe("%PDF-1.7");
    });

    it("reports a preview failure by code without server text", async () => {
        stubFetch(json({ error: { code: "FORM_3500_RENDER_FAILED", message: "private server detail" } }, 502));
        const failure = await fetchForm3500PreviewPdf(DRAFT_ID).catch((error: unknown) => error);
        expect(failure).toMatchObject({ code: "FORM_3500_RENDER_FAILED", status: 502 });
        expect((failure as Error).message).not.toContain("private server detail");
    });

    it("reads one draft by id and maps a 404 to the unavailable message", async () => {
        stubFetch(json(draftResponse()));
        expect((await fetchMedWatchDraft(DRAFT_ID)).id).toBe(DRAFT_ID);
        stubFetch(json({ error: { code: "NOT_FOUND" } }, 404));
        await expect(fetchMedWatchDraft(DRAFT_ID)).rejects.toMatchObject({ status: 404 });
    });

    it("falls back to the server's filename pattern without a readable header", () => {
        expect(form3500PdfFilename(DRAFT_ID, null)).toBe("fda-3500-abcdef12-not-submitted.pdf");
        expect(form3500PdfFilename(DRAFT_ID, 'attachment; filename="../etc/passwd"')).toBe(
            "fda-3500-abcdef12-not-submitted.pdf",
        );
    });

    it("never replays a PDF download after a transport failure", async () => {
        const fetchMock = vi.fn().mockRejectedValue(new TypeError("offline"));
        vi.stubGlobal("fetch", fetchMock);
        await expect(downloadForm3500Pdf(DRAFT_ID)).rejects.toMatchObject({ code: "NETWORK" });
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it.each([
        [503, "FORM_3500_TEMPLATE_MISMATCH", /integrity check/],
        [502, "FORM_3500_RENDER_FAILED", /could not be produced/],
        [422, "MEDWATCH_LEGACY_DRAFT_INCOMPLETE", /Discard it and prepare a new draft/],
        [403, "AUTHORIZATION_ERROR", /no longer assigned/],
        [404, "NOT_FOUND", /no longer available/],
    ])("surfaces a %s %s PDF error by code without server text", async (status, code, message) => {
        stubFetch(json({ error: { code, message: "private server detail" } }, status));
        const failure = await downloadForm3500Pdf(DRAFT_ID).catch((error: unknown) => error);
        expect(failure).toBeInstanceOf(MedWatchRequestError);
        expect(failure).toMatchObject({ code, status });
        expect((failure as Error).message).toMatch(message);
        expect((failure as Error).message).not.toContain("private server detail");
    });

    it("surfaces an incomplete approval and a stale revision without server text", async () => {
        stubFetch(json({ error: { code: "MEDWATCH_APPROVAL_INCOMPLETE", message: "secret" } }, 422));
        const incomplete = await approveMedWatchDraft(DRAFT_ID, {
            approvalNote: "n",
            expectedRevision: 1,
            attestationVersion: "medwatch-3500-approval-v1",
            nonSeriousAttested: false,
            acknowledgedWarnings: [],
        }).then(
            () => {
                throw new Error("expected a rejection");
            },
            (error: unknown) => error as MedWatchRequestError,
        );
        expect(incomplete.code).toBe("MEDWATCH_APPROVAL_INCOMPLETE");
        expect(incomplete.message).toMatch(/missing items/);

        stubFetch(json({ error: { code: "VALIDATION_ERROR", message: "secret" } }, 409));
        const stale = await updateMedWatchDraft(DRAFT_ID, makeForm(), 1).then(
            () => {
                throw new Error("expected a rejection");
            },
            (error: unknown) => error as MedWatchRequestError,
        );
        expect(stale.status).toBe(409);
        expect(stale.message).toMatch(/changed since you opened it/);
        expect(stale.message).not.toContain("secret");
    });

    it("discards with a reason and the expected revision", async () => {
        const fetchMock = stubFetch(json(draftResponse()));
        await discardMedWatchDraft(DRAFT_ID, { reason: "Wrong suspect product", expectedRevision: 2 });
        expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/${DRAFT_ID}/discard`);
        expect(sentBody(fetchMock)).toEqual({ reason: "Wrong suspect product", expected_revision: 2 });
    });

    it("records a submission with the attestation and the expected revision", async () => {
        const fetchMock = stubFetch(json(draftResponse()));
        await recordMedWatchSubmission(DRAFT_ID, {
            submittedOn: "2026-10-10",
            method: "medwatch_online",
            methodDetail: "ignored unless other",
            fdaReference: "  MW-0000001 ",
            expectedRevision: 3,
        });
        expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/${DRAFT_ID}/submission`);
        expect(sentBody(fetchMock)).toEqual({
            submitted_on: "2026-10-10",
            method: "medwatch_online",
            method_detail: null,
            fda_reference: "MW-0000001",
            attested: true,
            expected_revision: 3,
        });
    });

    it("amends the current record with a reason", async () => {
        const fetchMock = stubFetch(json(draftResponse()));
        await amendMedWatchSubmission(DRAFT_ID, {
            amendsId: "submission-1",
            submittedOn: "2026-10-09",
            method: "other",
            methodDetail: " Courier ",
            fdaReference: "",
            reason: " Wrong date ",
        });
        expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/${DRAFT_ID}/submission/amend`);
        expect(sentBody(fetchMock)).toEqual({
            amends_id: "submission-1",
            submitted_on: "2026-10-09",
            method: "other",
            method_detail: "Courier",
            fda_reference: null,
            reason: "Wrong date",
        });
    });
});
