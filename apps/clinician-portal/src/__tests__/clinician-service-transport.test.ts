import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchPatientDeepDive, generateSoapNote } from "@/services/clinicians";
import { ApiClientError } from "@/services/api";

vi.mock("@/services/auth-session", () => ({
    readStoredSession: () => ({ accessToken: "synthetic-token" }),
}));

describe("clinician service transport", () => {
    afterEach(() => vi.unstubAllGlobals());

    it("retains the HTTP status needed for the access-denied screen", async () => {
        const fetchMock = vi.fn().mockResolvedValue(new Response(
            JSON.stringify({ error: { message: "You are not assigned to this patient" } }),
            { status: 403, headers: { "Content-Type": "application/json" } },
        ));
        vi.stubGlobal("fetch", fetchMock);
        await expect(fetchPatientDeepDive("synthetic-patient")).rejects.toBeInstanceOf(ApiClientError);
        await expect(fetchPatientDeepDive("synthetic-patient")).rejects.toMatchObject({ status: 403 });
        expect(fetchMock).toHaveBeenCalledTimes(2); // One request per explicit invocation.
    });

    it("recovers a failed deep-dive read once", async () => {
        const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("offline"))
            .mockResolvedValueOnce(new Response("{}", { headers: { "Content-Type": "application/json" } }));
        vi.stubGlobal("fetch", fetchMock);
        await expect(fetchPatientDeepDive("synthetic-patient")).resolves.toBeDefined();
        expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it("never replays a SOAP generation write after a transport failure", async () => {
        const fetchMock = vi.fn().mockRejectedValue(new TypeError("offline"));
        vi.stubGlobal("fetch", fetchMock);
        await expect(generateSoapNote("synthetic-patient", 30)).rejects.toMatchObject({ outcomeUnknown: true });
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });
});
