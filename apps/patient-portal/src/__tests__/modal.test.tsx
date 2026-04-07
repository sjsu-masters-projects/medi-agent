import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "@/components/ui/modal";

describe("Modal", () => {
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
