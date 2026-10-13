import { fireEvent, render, screen } from "@testing-library/react";
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
