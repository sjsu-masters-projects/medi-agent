import { describe, expect, it } from "vitest";
import { readableError } from "@/services/error-text";
import { ApiClientError } from "@/services/api";
import { MedWatchRequestError } from "@/services/clinicians";
import { ApiTransportError } from "../../../../packages/shared/src/utils/api-transport";

describe("readableError", () => {
    it("shows messages written for clinicians", () => {
        expect(readableError(new ApiClientError("Only clinic admins can manage staff", 403, null), "Fallback")).toBe("Only clinic admins can manage staff");
        expect(readableError(new ApiTransportError(false, 1), "Fallback")).toMatch(/Could not connect/);
        expect(readableError(new MedWatchRequestError("UNKNOWN", 404), "Fallback")).toBe("This MedWatch draft is no longer available.");
    });

    it("replaces code errors and non-errors with the screen's fallback", () => {
        expect(readableError(new TypeError("Cannot read properties of undefined (reading 'id')"), "Unable to load imported records.")).toBe("Unable to load imported records.");
        expect(readableError(new SyntaxError("Unexpected token < in JSON"), "Fallback")).toBe("Fallback");
        expect(readableError("boom", "Fallback")).toBe("Fallback");
        expect(readableError(new ApiClientError("  ", 500, null), "Fallback")).toBe("Fallback");
    });
});
