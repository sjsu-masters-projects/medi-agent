import "@testing-library/jest-dom/vitest";

function installStorageFallback(name: "localStorage" | "sessionStorage") {
    const current = window[name];
    if (current && typeof current.clear === "function") {
        return;
    }

    const values = new Map<string, string>();
    Object.defineProperty(window, name, {
        configurable: true,
        value: {
            clear: () => values.clear(),
            getItem: (key: string) => values.get(key) ?? null,
            key: (index: number) => Array.from(values.keys())[index] ?? null,
            removeItem: (key: string) => values.delete(key),
            setItem: (key: string, value: string) => values.set(key, String(value)),
            get length() {
                return values.size;
            },
        },
    });
}

installStorageFallback("localStorage");
installStorageFallback("sessionStorage");
