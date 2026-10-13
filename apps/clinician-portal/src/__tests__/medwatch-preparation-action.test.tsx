import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MedWatchPreparationAction } from "@/components/features/medwatch-preparation-action";

const PREPARE_ERROR =
    "Unable to prepare the MedWatch draft. Your rationale is retained. Try again.";

function open() {
    fireEvent.click(screen.getByRole("button", { name: "Prepare MedWatch draft" }));
}

function enterRationale(value: string) {
    fireEvent.change(screen.getByLabelText(/clinical rationale/i), {
        target: { value },
    });
}

describe("MedWatchPreparationAction", () => {
    const unhandled = vi.fn();
    beforeEach(() => {
        unhandled.mockReset();
        process.on("unhandledRejection", unhandled);
    });
    afterEach(() => {
        process.off("unhandledRejection", unhandled);
    });

    it("opens the form and requires a rationale before creating", () => {
        const onPrepare = vi.fn().mockResolvedValue(undefined);
        render(<MedWatchPreparationAction disabled={false} onPrepare={onPrepare} />);
        open();
        expect(
            screen.getByRole("form", { name: "Record reportability decision" }),
        ).toBeInTheDocument();
        const create = screen.getByRole("button", { name: "Create editable draft" });
        expect(create).toBeDisabled();
        enterRationale("   ");
        expect(create).toBeDisabled();
        enterRationale("Clinically significant new event.");
        expect(create).not.toBeDisabled();
    });

    it("shows a failure inline, keeps the rationale, and leaves no unhandled rejection", async () => {
        const onPrepare = vi
            .fn()
            .mockRejectedValueOnce(new Error("private provider diagnostic"));
        render(<MedWatchPreparationAction disabled={false} onPrepare={onPrepare} />);
        open();
        enterRationale("  Clinically significant new event.  ");
        fireEvent.click(screen.getByRole("button", { name: "Create editable draft" }));

        expect(await screen.findByRole("alert")).toHaveTextContent(PREPARE_ERROR);
        expect(onPrepare).toHaveBeenCalledWith("Clinically significant new event.");
        expect(screen.queryByText("private provider diagnostic")).not.toBeInTheDocument();
        expect(screen.getByLabelText(/clinical rationale/i)).toHaveValue(
            "  Clinically significant new event.  ",
        );
        expect(screen.getByLabelText(/clinical rationale/i)).toHaveAccessibleDescription(
            expect.stringContaining(PREPARE_ERROR),
        );
        expect(
            screen.getByRole("button", { name: "Create editable draft" }),
        ).not.toBeDisabled();
        // Let any stray rejection surface before asserting none occurred.
        await act(async () => {
            await new Promise((resolve) => setTimeout(resolve, 0));
        });
        expect(unhandled).not.toHaveBeenCalled();
    });

    it("closes and clears the form after a successful preparation", async () => {
        const onPrepare = vi.fn().mockResolvedValue(undefined);
        render(<MedWatchPreparationAction disabled={false} onPrepare={onPrepare} />);
        open();
        enterRationale("Clinically significant new event.");
        fireEvent.click(screen.getByRole("button", { name: "Create editable draft" }));
        await waitFor(() =>
            expect(
                screen.getByRole("button", { name: "Prepare MedWatch draft" }),
            ).toBeInTheDocument(),
        );
        expect(onPrepare).toHaveBeenCalledTimes(1);
        open();
        expect(screen.getByLabelText(/clinical rationale/i)).toHaveValue("");
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("clears the error on Cancel", async () => {
        const onPrepare = vi.fn().mockRejectedValueOnce(new Error("failed"));
        render(<MedWatchPreparationAction disabled={false} onPrepare={onPrepare} />);
        open();
        enterRationale("Clinically significant new event.");
        fireEvent.click(screen.getByRole("button", { name: "Create editable draft" }));
        expect(await screen.findByRole("alert")).toHaveTextContent(PREPARE_ERROR);
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        expect(
            screen.getByRole("button", { name: "Prepare MedWatch draft" }),
        ).toBeInTheDocument();
        open();
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
});
