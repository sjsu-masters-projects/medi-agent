/**
 * Copy text to the clipboard, falling back when the asynchronous Clipboard API is missing
 * or refuses (an insecure context, a browser policy, or a lost user gesture).
 *
 * Resolves to whether the text was copied; it never rejects, so callers always show an
 * outcome instead of failing silently.
 */
export async function copyText(text: string): Promise<boolean> {
    if (!text) {
        return false;
    }
    if (typeof navigator !== "undefined" && typeof navigator.clipboard?.writeText === "function") {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch {
            // Try the selection-based copy below.
        }
    }
    return copyWithSelection(text);
}

function copyWithSelection(text: string): boolean {
    if (typeof document === "undefined" || typeof document.execCommand !== "function") {
        return false;
    }
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.setAttribute("aria-hidden", "true");
    area.style.position = "fixed";
    area.style.top = "0";
    area.style.left = "0";
    area.style.opacity = "0";
    area.style.pointerEvents = "none";
    document.body.appendChild(area);
    let copied = false;
    try {
        area.focus();
        area.select();
        area.setSelectionRange(0, text.length);
        copied = document.execCommand("copy");
    } catch {
        copied = false;
    } finally {
        area.remove();
        previousFocus?.focus();
    }
    return copied;
}
