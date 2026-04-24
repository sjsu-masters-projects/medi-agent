const DEFAULT_TIMEZONE = "UTC";

export function getSupportedTimezones(): string[] {
    if (typeof Intl !== "undefined" && "supportedValuesOf" in Intl) {
        try {
            const intlWithSupportedValuesOf = Intl as typeof Intl & {
                supportedValuesOf?: (key: string) => string[];
            };
            return intlWithSupportedValuesOf.supportedValuesOf?.("timeZone") ?? [DEFAULT_TIMEZONE];
        } catch {
            return [DEFAULT_TIMEZONE];
        }
    }
    return [DEFAULT_TIMEZONE];
}

export function getBrowserTimezone(): string {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || DEFAULT_TIMEZONE;
    } catch {
        return DEFAULT_TIMEZONE;
    }
}
