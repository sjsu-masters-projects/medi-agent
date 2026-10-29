import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "@/components/ui/modal";

describe("Modal", () => {
    it("includes help disclosures in the focus loop", () => {
        render(<Modal open title="Language" onClose={vi.fn()}><select aria-label="Language"><option>English</option></select><details><summary>About language</summary><p>Help</p></details></Modal>);
        fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
        expect(screen.getByText("About language")).toHaveFocus();
        fireEvent.keyDown(document, { key: "Tab" });
        expect(screen.getByRole("button", { name: "Close modal" })).toHaveFocus();
    });
    it("labels the dialog, contains keyboard focus, closes on Escape and restores focus", () => {
        const close = vi.fn();
        const { rerender } = render(<><button>Open</button><Modal open={false} title="Review" onClose={close}><button>Last action</button></Modal></>);
        screen.getByRole("button", { name: "Open" }).focus();
        rerender(<><button>Open</button><Modal open title="Review" onClose={close}><button>Last action</button></Modal></>);
        expect(screen.getByRole("dialog", { name: "Review" })).toHaveAttribute("aria-modal", "true");
        expect(screen.getByRole("button", { name: "Close modal" })).toHaveFocus();
        fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
        expect(screen.getByRole("button", { name: "Last action" })).toHaveFocus();
        fireEvent.keyDown(document, { key: "Tab" });
        expect(screen.getByRole("button", { name: "Close modal" })).toHaveFocus();
        fireEvent.keyDown(document, { key: "Escape" });
        expect(close).toHaveBeenCalledOnce();
        rerender(<><button>Open</button><Modal open={false} title="Review" onClose={close}><button>Last action</button></Modal></>);
        expect(screen.getByRole("button", { name: "Open" })).toHaveFocus();
    });
    it("keeps Tab inside the sheet when the last control sits in collapsed details or focus escaped", () => {
        render(<><button>Behind the sheet</button><Modal open title="Medication help" onClose={vi.fn()}><details><summary>Why this matters</summary><button>Hidden follow-up</button></details></Modal></>);
        fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
        expect(screen.getByText("Why this matters")).toHaveFocus();
        fireEvent.keyDown(document, { key: "Tab" });
        expect(screen.getByRole("button", { name: "Close modal" })).toHaveFocus();
        screen.getByRole("button", { name: "Behind the sheet", hidden: true }).focus();
        fireEvent.keyDown(document, { key: "Tab" });
        expect(screen.getByRole("button", { name: "Close modal" })).toHaveFocus();
    });
    it("keeps closing content briefly without a dialog role, returns focus at once, and lets a reopen cancel the exit", () => {
        vi.useFakeTimers();
        try {
            const exited = vi.fn();
            const sheet = (open: boolean) => <><button>Open</button><Modal open={open} animateExit onExited={exited} title="Record" onClose={vi.fn()}><p>Record body</p></Modal></>;
            const { rerender } = render(sheet(false));
            screen.getByRole("button", { name: "Open" }).focus();
            rerender(sheet(true));
            rerender(sheet(false));
            expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
            expect(screen.getByText("Record body", { selector: "p" })).toBeInTheDocument();
            expect(screen.getByRole("button", { name: "Open" })).toHaveFocus();
            act(() => { vi.advanceTimersByTime(100); });
            rerender(sheet(true));
            act(() => { vi.advanceTimersByTime(500); });
            expect(exited).not.toHaveBeenCalled();
            expect(screen.getByRole("dialog", { name: "Record" })).toBeInTheDocument();
            rerender(sheet(false));
            act(() => { vi.advanceTimersByTime(160); });
            expect(exited).toHaveBeenCalledOnce();
            expect(screen.queryByText("Record body")).not.toBeInTheDocument();
        } finally {
            vi.useRealTimers();
        }
    });
    it("closes without delay under reduced motion", () => {
        vi.useFakeTimers();
        vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
        try {
            const exited = vi.fn();
            const { rerender } = render(<Modal open animateExit onExited={exited} title="Record" onClose={vi.fn()}><p>Body</p></Modal>);
            rerender(<Modal open={false} animateExit onExited={exited} title="Record" onClose={vi.fn()}><p>Body</p></Modal>);
            act(() => { vi.advanceTimersByTime(0); });
            expect(exited).toHaveBeenCalledOnce();
        } finally {
            vi.unstubAllGlobals();
            vi.useRealTimers();
        }
    });
    it("renders open content and closes", () => {
        const handleClose = vi.fn();
        render(
            <Modal onClose={handleClose} open title="Document detail">
                <p>Modal content</p>
            </Modal>,
        );

        expect(screen.getByText("Document detail")).toBeInTheDocument();
        fireEvent.click(screen.getByLabelText(/close modal/i));
        expect(handleClose).toHaveBeenCalledOnce();
    });
});
