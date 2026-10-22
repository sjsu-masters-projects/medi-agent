import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "@/components/ui/modal";

describe("Clinician review modal", () => {
    it("restores an explicit opener when async work lost its focus before mounting", () => {
        const opener = document.createElement("button");
        document.body.append(opener);
        const returnFocusRef = { current: opener };
        const view = render(<Modal open title="Delayed review" onClose={vi.fn()} returnFocusRef={returnFocusRef}><button>Cancel</button></Modal>);
        view.rerender(<Modal open={false} title="Delayed review" onClose={vi.fn()} returnFocusRef={returnFocusRef}><button>Cancel</button></Modal>);
        expect(opener).toHaveFocus();
        opener.remove();
    });
    it("labels the dialog, traps focus, closes on Escape, and returns focus to the opener", () => {
        const close = vi.fn();
        const opener = document.createElement("button");
        document.body.append(opener); opener.focus();
        const view = render(<Modal open title="Review evidence" onClose={close}><button>Confirm review</button></Modal>);
        expect(screen.getByRole("dialog", { name: "Review evidence" })).toHaveAttribute("aria-modal", "true");
        expect(screen.getByRole("button", { name: "Close modal" })).toHaveFocus();
        fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
        expect(screen.getByRole("button", { name: "Confirm review" })).toHaveFocus();
        fireEvent.keyDown(document, { key: "Tab" });
        expect(screen.getByRole("button", { name: "Close modal" })).toHaveFocus();
        fireEvent.keyDown(document, { key: "Escape" });
        expect(close).toHaveBeenCalledOnce();
        view.rerender(<Modal open={false} title="Review evidence" onClose={close}><button>Confirm review</button></Modal>);
        expect(opener).toHaveFocus();
        expect(document.body.style.overflow).toBe("");
        opener.remove();
    });
    it("excludes controls inside collapsed supporting details from keyboard focus", () => {
        render(<Modal open title="Review evidence" onClose={vi.fn()}><details><summary>Supporting information</summary><button>Hidden source action</button></details></Modal>);
        fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
        expect(screen.getByText("Supporting information")).toHaveFocus();
    });
});
