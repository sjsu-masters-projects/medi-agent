import { vi } from "vitest";

/**
 * Make calls that omit a locale behave like a day-month-year browser region
 * (en-GB), so tests prove clinician dates are formatted explicitly as en-US
 * whatever locale the test process happens to run in.
 */
export function simulateNonUsDefaultLocale(defaultLocale = "en-GB") {
    const toLocaleString = Date.prototype.toLocaleString;
    const toLocaleDateString = Date.prototype.toLocaleDateString;
    const toLocaleTimeString = Date.prototype.toLocaleTimeString;
    vi.spyOn(Date.prototype, "toLocaleString").mockImplementation(function (this: Date, locales, options) {
        return toLocaleString.call(this, locales ?? defaultLocale, options);
    });
    vi.spyOn(Date.prototype, "toLocaleDateString").mockImplementation(function (this: Date, locales, options) {
        return toLocaleDateString.call(this, locales ?? defaultLocale, options);
    });
    vi.spyOn(Date.prototype, "toLocaleTimeString").mockImplementation(function (this: Date, locales, options) {
        return toLocaleTimeString.call(this, locales ?? defaultLocale, options);
    });
}
