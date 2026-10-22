import { describe, expect, it } from "vitest";
import { reportedProduct } from "@/utils/reported-product";

const report = (product: unknown, confirmation_state = "patient_confirmed") => ({ confirmation_state, confirmed_content: { answers: { product } } });

describe("confirmed product testimony", () => {
    it("keeps an unlisted product without inventing a canonical identity", () => {
        expect(reportedProduct(report({ state: "answered", value: { name: "Synthetic supplement", concern: true } }))).toEqual({ name: "Synthetic supplement", concern: true });
    });
    it.each(["unknown", "declined", "unanswered"])("does not infer a product from %s", (state) => {
        expect(reportedProduct(report({ state, value: { name: "Do not infer", concern: true } }))).toBeUndefined();
    });
    it("does not treat legacy content as patient-confirmed", () => {
        expect(reportedProduct(report({ state: "answered", value: { name: "Legacy" } }, "legacy_unconfirmed"))).toBeUndefined();
    });
    it.each([null, [], "text", { state: "answered", value: [] }, { state: "answered", value: { name: " " } }])("ignores malformed content %j", (value) => {
        expect(reportedProduct(report(value))).toBeUndefined();
    });
    it("does not turn a missing concern into a confirmed concern", () => {
        expect(reportedProduct(report({ state: "answered", value: { name: "Synthetic product", concern: "yes" } }))).toEqual({ name: "Synthetic product", concern: null });
    });
});
