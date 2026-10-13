import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CopyButton } from "@/components/ui";
import { copyText } from "@/utils/clipboard";

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");

function setClipboard(writeText: ((text: string) => Promise<void>) | undefined) {
    Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: writeText ? { writeText } : undefined,
    });
}

function setExecCommand(result: boolean | Error) {
    const execCommand = vi.fn(() => {
        if (result instanceof Error) throw result;
        return result;
    });
    Object.defineProperty(document, "execCommand", { configurable: true, value: execCommand });
    return execCommand;
}

describe("copyText", () => {
    afterEach(() => {
        if (originalClipboard) Object.defineProperty(navigator, "clipboard", originalClipboard);
        else Reflect.deleteProperty(navigator, "clipboard");
        Reflect.deleteProperty(document, "execCommand");
    });

    it("uses the Clipboard API when it is available", async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        setClipboard(writeText);
        const execCommand = setExecCommand(true);
        await expect(copyText("ABC123")).resolves.toBe(true);
        expect(writeText).toHaveBeenCalledWith("ABC123");
        expect(execCommand).not.toHaveBeenCalled();
    });

    it("falls back to a selected text area when the Clipboard API refuses", async () => {
        setClipboard(vi.fn().mockRejectedValue(new DOMException("Denied", "NotAllowedError")));
        let copiedValue = "";
        const execCommand = setExecCommand(true);
        execCommand.mockImplementation(() => {
            copiedValue = (document.activeElement as HTMLTextAreaElement).value;
            return true;
        });
        await expect(copyText("ABC123")).resolves.toBe(true);
        expect(execCommand).toHaveBeenCalledWith("copy");
        expect(copiedValue).toBe("ABC123");
        expect(document.querySelector("textarea")).toBeNull();
    });

    it("falls back when the Clipboard API is missing", async () => {
        setClipboard(undefined);
        setExecCommand(true);
        await expect(copyText("ABC123")).resolves.toBe(true);
    });

    it("reports failure instead of rejecting when both ways fail", async () => {
        setClipboard(undefined);
        setExecCommand(new Error("unsupported"));
        await expect(copyText("ABC123")).resolves.toBe(false);
        setExecCommand(false);
        await expect(copyText("ABC123")).resolves.toBe(false);
        await expect(copyText("")).resolves.toBe(false);
    });
});

describe("CopyButton", () => {
    beforeEach(() => setClipboard(undefined));
    afterEach(() => {
        cleanup();
        if (originalClipboard) Object.defineProperty(navigator, "clipboard", originalClipboard);
        else Reflect.deleteProperty(navigator, "clipboard");
        Reflect.deleteProperty(document, "execCommand");
    });

    it("says Copied after a successful copy", async () => {
        setClipboard(vi.fn().mockResolvedValue(undefined));
        render(<CopyButton aria-label="Copy clinic code" value="ABC123">Copy</CopyButton>);
        fireEvent.click(screen.getByRole("button", { name: "Copy clinic code" }));
        await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Copied"));
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("says Copied after the fallback copy", async () => {
        setExecCommand(true);
        render(<CopyButton value="ABC123">Copy</CopyButton>);
        fireEvent.click(screen.getByRole("button", { name: "Copy" }));
        await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Copied"));
    });

    it("shows the text selected for a manual copy when copying fails", async () => {
        setExecCommand(false);
        render(<CopyButton value="ABC123">Copy</CopyButton>);
        fireEvent.click(screen.getByRole("button", { name: "Copy" }));
        expect(await screen.findByRole("alert")).toHaveTextContent(/Copy did not work in this browser/);
        const manual = screen.getByRole("textbox", { name: "Text to copy" }) as HTMLInputElement;
        expect(manual).toHaveValue("ABC123");
        expect(manual).toHaveFocus();
        expect([manual.selectionStart, manual.selectionEnd]).toEqual([0, 6]);
        expect(screen.getByRole("status")).toHaveTextContent("");
    });

    it("is disabled while there is nothing to copy", () => {
        render(<CopyButton value={null}>Copy</CopyButton>);
        expect(screen.getByRole("button", { name: "Copy" })).toBeDisabled();
    });
});
