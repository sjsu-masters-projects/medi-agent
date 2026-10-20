import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");
function token(name: string) {
    const value = css.match(new RegExp(`--color-${name}:\\s*(#[a-f\\d]{6})`, "i"))?.[1];
    if (!value) throw new Error(`Missing color token ${name}`);
    return value;
}
function luminance(hex: string) {
    const channels = hex.slice(1).match(/../g)!.map((part) => {
        const value = Number.parseInt(part, 16) / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}
function contrast(foreground: string, background: string) {
    const [a, b] = [luminance(foreground), luminance(background)];
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

describe("Readable secondary interface text", () => {
    it.each(["background", "surface", "surface-2", "sunken", "track"])("keeps muted text readable on %s", (background) => {
        expect(contrast(token("muted"), token(background))).toBeGreaterThanOrEqual(4.5);
    });
    it.each(["#0A1222", "#1E293B"])("keeps small sidebar counts readable on %s", (background) => {
        expect(contrast(token("rail-faint"), background)).toBeGreaterThanOrEqual(4.5);
    });
});
