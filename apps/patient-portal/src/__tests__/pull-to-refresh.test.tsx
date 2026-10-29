import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PullToRefresh } from "@/components/ui/pull-to-refresh";

function gesture(target: HTMLElement, distance = 180) {
    fireEvent.touchStart(target, { touches: [{ clientX: 10, clientY: 0 }] });
    fireEvent.touchMove(target, { touches: [{ clientX: 10, clientY: distance }] });
    fireEvent.touchEnd(target, { touches: [] });
}

describe("PullToRefresh", () => {
    it("calls the existing refresh only beyond the threshold", () => {
        const refresh = vi.fn();
        render(<PullToRefresh onRefresh={refresh} label="Refresh"><p>List</p></PullToRefresh>);
        gesture(screen.getByText("List"), 100);
        expect(refresh).not.toHaveBeenCalled();
        gesture(screen.getByText("List"));
        expect(refresh).toHaveBeenCalledOnce();
    });
    it("does not steal gestures from controls or horizontal movement", () => {
        const refresh = vi.fn();
        render(<PullToRefresh onRefresh={refresh} label="Refresh"><button>Action</button><p>List</p></PullToRefresh>);
        gesture(screen.getByRole("button", { name: "Action" }));
        const list = screen.getByText("List");
        fireEvent.touchStart(list, { touches: [{ clientX: 0, clientY: 0 }] });
        fireEvent.touchMove(list, { touches: [{ clientX: 200, clientY: 100 }] });
        fireEvent.touchEnd(list);
        expect(refresh).not.toHaveBeenCalled();
    });
    it("cancels without refreshing and respects parent loading", () => {
        const refresh = vi.fn();
        const { rerender } = render(<PullToRefresh onRefresh={refresh} label="Refresh"><p>List</p></PullToRefresh>);
        const list = screen.getByText("List");
        fireEvent.touchStart(list, { touches: [{ clientX: 0, clientY: 0 }] });
        fireEvent.touchMove(list, { touches: [{ clientX: 0, clientY: 200 }] });
        fireEvent.touchCancel(list);
        fireEvent.touchEnd(list);
        rerender(<PullToRefresh busy onRefresh={refresh} label="Refresh"><p>List</p></PullToRefresh>);
        gesture(list);
        expect(refresh).not.toHaveBeenCalled();
        expect(screen.getByRole("img", { name: "Refresh" })).toBeInTheDocument();
    });
    it("can leave parent loading to the page's own indicator while still blocking gestures", async () => {
        let resolve!: () => void;
        const refresh = vi.fn(() => new Promise<void>((done) => { resolve = done; }));
        const { rerender } = render(<PullToRefresh busy indicateBusy={false} onRefresh={refresh} label="Refresh"><p>List</p></PullToRefresh>);
        expect(screen.queryByRole("img", { name: "Refresh" })).not.toBeInTheDocument();
        gesture(screen.getByText("List"));
        expect(refresh).not.toHaveBeenCalled();
        rerender(<PullToRefresh indicateBusy={false} onRefresh={refresh} label="Refresh"><p>List</p></PullToRefresh>);
        gesture(screen.getByText("List"));
        expect(screen.getByRole("img", { name: "Refresh" })).toBeInTheDocument();
        await act(async () => { resolve(); });
        expect(screen.queryByRole("img")).not.toBeInTheDocument();
    });
    it("keeps the pending indication until an actual async refresh resolves", async () => {
        let resolve!: () => void;
        const refresh = vi.fn(() => new Promise<void>((done) => { resolve = done; }));
        render(<PullToRefresh onRefresh={refresh} label="Refreshing"><p>List</p></PullToRefresh>);
        gesture(screen.getByText("List"));
        expect(screen.getByRole("img", { name: "Refreshing" })).toBeInTheDocument();
        gesture(screen.getByText("List"));
        expect(refresh).toHaveBeenCalledOnce();
        await act(async () => { resolve(); });
        expect(screen.queryByRole("img")).not.toBeInTheDocument();
    });
});
