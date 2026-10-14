import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiTransportError } from "../../../../packages/shared/src/utils/api-transport";
import { getADRFollowUpCopy } from "@/content/adr-follow-up-copy";
import { api, ApiClientError } from "@/services/api";
import {
    classifyADRFollowUpError,
    fetchADRFollowUpOverview,
    type ADRFollowUpErrorClass,
} from "@/services/adr-follow-up";

// Keep the real ApiClientError so `instanceof` checks in the classifier hold.
vi.mock("@/services/api", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/services/api")>();
    return { ...actual, api: { get: vi.fn(), post: vi.fn() } };
});

const SECRET = "SERVER SECRET";
const CLASSES: readonly ADRFollowUpErrorClass[] = ["closed", "notFound", "unavailable", "other"];
const LOCALES = ["en-US", "es-MX"] as const;
const CODES: readonly unknown[] = [
    "NOT_FOUND",
    "ADR_REQUEST_CLOSED",
    "ADR_RESPONSE_INVALID",
    "VALIDATION_ERROR",
    "arbitrary text",
    42,
];

interface Case {
    label: string;
    value: unknown;
    expected: ADRFollowUpErrorClass;
}

/** Independent statement of the design mapping, including precedence. */
function expectedForClientError(status: number, details: unknown): ADRFollowUpErrorClass {
    const envelope =
        typeof details === "object" && details !== null
            ? (details as { error?: { code?: unknown } }).error
            : undefined;
    const code = typeof envelope?.code === "string" ? envelope.code : null;
    // A NOT_FOUND code wins over any status (the classifier checks it first).
    if (status === 404 || code === "NOT_FOUND") return "notFound";
    if (status === 422 && code === "ADR_REQUEST_CLOSED") return "closed";
    if ([0, 502, 503, 504].includes(status)) return "unavailable";
    return "other";
}

function buildCases(): Case[] {
    const detailVariants: { label: string; value: unknown }[] = [
        { label: "undefined", value: undefined },
        { label: "null", value: null },
        { label: "string", value: SECRET },
        ...CODES.map((code) => ({
            label: `code=${String(code)}`,
            value: { error: { code, message: SECRET } },
        })),
    ];
    const cases: Case[] = [];
    for (let status = 0; status <= 599; status += 1) {
        for (const details of detailVariants) {
            cases.push({
                label: `ApiClientError ${status} ${details.label}`,
                value: new ApiClientError(SECRET, status, details.value),
                expected: expectedForClientError(status, details.value),
            });
        }
    }

    const timeoutDom = new DOMException(SECRET, "TimeoutError");
    const timeoutError = new Error(SECRET);
    timeoutError.name = "TimeoutError";
    const abortDom = new DOMException(SECRET, "AbortError");
    const abortError = new Error(SECRET);
    abortError.name = "AbortError";
    // Throws on every trap, including the prototype read behind `instanceof`.
    const hostile = new Proxy(
        {},
        {
            get() {
                throw new Error(SECRET);
            },
            getPrototypeOf() {
                throw new Error(SECRET);
            },
        },
    );

    cases.push(
        { label: "ApiTransportError (outcome known)", value: new ApiTransportError(false, 1), expected: "unavailable" },
        { label: "ApiTransportError (outcome unknown)", value: new ApiTransportError(true, 0), expected: "unavailable" },
        { label: "DOMException TimeoutError", value: timeoutDom, expected: "unavailable" },
        { label: "Error named TimeoutError", value: timeoutError, expected: "unavailable" },
        { label: "DOMException AbortError", value: abortDom, expected: "other" },
        { label: "Error named AbortError", value: abortError, expected: "other" },
        { label: "plain Error", value: new Error(SECRET), expected: "other" },
        { label: "null", value: null, expected: "other" },
        { label: "undefined", value: undefined, expected: "other" },
        { label: "string", value: SECRET, expected: "other" },
        { label: "number", value: 503, expected: "other" },
        { label: "object", value: { status: 404, error: { code: "NOT_FOUND", message: SECRET } }, expected: "other" },
        { label: "symbol", value: Symbol(SECRET), expected: "other" },
        { label: "hostile proxy", value: hostile, expected: "other" },
    );
    return cases;
}

describe("classifyADRFollowUpError", () => {
    // Feature: adr-loop-gap-fixes, Property 4: Error classification is total and never shows server text
    // **Validates: Requirements 3.7, 6.3, 6.4**
    it("returns exactly one known class per the mapping and never surfaces server text", () => {
        const cases = buildCases();
        expect(cases.length).toBeGreaterThan(600 * 9);
        const mismatches: string[] = [];
        for (const { label, value, expected } of cases) {
            let actual: ADRFollowUpErrorClass | undefined;
            expect(() => {
                actual = classifyADRFollowUpError(value);
            }, label).not.toThrow();
            expect(CLASSES, label).toContain(actual);
            if (actual !== expected) mismatches.push(`${label}: expected ${expected}, got ${String(actual)}`);
            for (const locale of LOCALES) {
                const message = getADRFollowUpCopy(locale).errors[actual as ADRFollowUpErrorClass];
                expect(message.trim().length, `${label} ${locale}`).toBeGreaterThan(0);
                expect(message, `${label} ${locale}`).not.toContain(SECRET);
            }
        }
        expect(mismatches).toEqual([]);
    });

    it("maps the design table anchors", () => {
        const envelope = (code: string) => ({ error: { code, message: SECRET } });
        expect(classifyADRFollowUpError(new ApiClientError(SECRET, 404, envelope("NOT_FOUND")))).toBe("notFound");
        expect(classifyADRFollowUpError(new ApiClientError(SECRET, 422, envelope("ADR_REQUEST_CLOSED")))).toBe("closed");
        expect(classifyADRFollowUpError(new ApiClientError(SECRET, 422, envelope("ADR_RESPONSE_INVALID")))).toBe("other");
        expect(classifyADRFollowUpError(new ApiClientError(SECRET, 409, envelope("ADR_REQUEST_CLOSED")))).toBe("other");
        expect(classifyADRFollowUpError(new ApiClientError(SECRET, 503, envelope("NOT_FOUND")))).toBe("notFound");
        expect(classifyADRFollowUpError(new ApiClientError(SECRET, 502, undefined))).toBe("unavailable");
        expect(classifyADRFollowUpError(new ApiClientError(SECRET, 500, undefined))).toBe("other");
    });
});

describe("fetchADRFollowUpOverview", () => {
    const getMock = vi.mocked(api.get);
    const base = "/api/v1/patients/me/adr-information-requests/overview";

    beforeEach(() => {
        getMock.mockReset();
        getMock.mockResolvedValue({ selected: null, pending: [], recent: [] });
    });

    it("builds the selector query, URL-encodes values and omits `?` without a selector", async () => {
        await fetchADRFollowUpOverview("token", { requestId: "req-1" });
        await fetchADRFollowUpOverview("token", { assessmentId: "asm-1" });
        await fetchADRFollowUpOverview("token");
        await fetchADRFollowUpOverview("token", {});
        await fetchADRFollowUpOverview("token", { requestId: "a b&c=d/é?" });

        expect(getMock.mock.calls).toEqual([
            [`${base}?request_id=req-1`, { token: "token" }],
            [`${base}?assessment_id=asm-1`, { token: "token" }],
            [base, { token: "token" }],
            [base, { token: "token" }],
            [`${base}?request_id=a+b%26c%3Dd%2F%C3%A9%3F`, { token: "token" }],
        ]);
    });

    it("maps snake_case to camelCase, drops null evidence and defaults missing arrays", async () => {
        const record = {
            id: "req-1",
            adr_assessment_id: "asm-1",
            status: "answered",
            symptom: "Synthetic dizziness",
            suspect_medication_name: "Synthetic medication",
            requested_information: ["dose_response"],
            patient_message: "Synthetic message",
            created_at: "2026-10-01T10:00:00Z",
            responded_at: "2026-10-02T10:00:00Z",
            closed_at: null,
            responses: [
                { question: "dose_response", answer: "yes", evidence: "Worse at higher dose" },
                { question: "reappeared_on_rechallenge", answer: "no", evidence: null },
                { question: "similar_previous_reaction", answer: "do_not_know" },
            ],
            replacement_request_id: "req-2",
        };
        // Older payloads may omit arrays; the mapper must still return arrays.
        const sparse = {
            id: "req-3",
            adr_assessment_id: "asm-3",
            status: "pending",
            symptom: "Synthetic rash",
            suspect_medication_name: "Synthetic medication",
            patient_message: "Synthetic message",
            created_at: "2026-10-03T10:00:00Z",
        };
        getMock.mockResolvedValueOnce({ selected: record, pending: [sparse] });

        const overview = await fetchADRFollowUpOverview("token", { requestId: "req-1" });

        expect(overview.selected).toEqual({
            id: "req-1",
            assessmentId: "asm-1",
            status: "answered",
            symptom: "Synthetic dizziness",
            suspectMedicationName: "Synthetic medication",
            requestedInformation: ["dose_response"],
            patientMessage: "Synthetic message",
            createdAt: "2026-10-01T10:00:00Z",
            respondedAt: "2026-10-02T10:00:00Z",
            closedAt: null,
            responses: [
                { question: "dose_response", answer: "yes", evidence: "Worse at higher dose" },
                { question: "reappeared_on_rechallenge", answer: "no" },
                { question: "similar_previous_reaction", answer: "do_not_know" },
            ],
            replacementRequestId: "req-2",
        });
        expect(overview.selected?.responses[1]).not.toHaveProperty("evidence");
        expect(overview.selected?.responses[2]).not.toHaveProperty("evidence");
        expect(overview.selected).not.toHaveProperty("adr_assessment_id");
        expect(overview.pending).toEqual([
            {
                id: "req-3",
                assessmentId: "asm-3",
                status: "pending",
                symptom: "Synthetic rash",
                suspectMedicationName: "Synthetic medication",
                requestedInformation: [],
                patientMessage: "Synthetic message",
                createdAt: "2026-10-03T10:00:00Z",
                respondedAt: null,
                closedAt: null,
                responses: [],
                replacementRequestId: null,
            },
        ]);
        expect(overview.recent).toEqual([]);
    });

    it("returns a null selection with empty lists", async () => {
        await expect(fetchADRFollowUpOverview("token")).resolves.toEqual({
            selected: null,
            pending: [],
            recent: [],
        });
    });
});
