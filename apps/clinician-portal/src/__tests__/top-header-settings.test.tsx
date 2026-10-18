import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TopHeader } from "@/components/layouts/top-header";

vi.mock("next/navigation", () => ({ usePathname: () => "/settings" }));
vi.mock("@/components/features/notification-centre", () => ({ NotificationBell: () => null }));

describe("TopHeader", () => {
    it("labels the settings page Settings", () => {
        render(<TopHeader />);
        expect(screen.getByText("Settings")).toBeInTheDocument();
        expect(screen.queryByText("Clinic settings")).not.toBeInTheDocument();
    });
});
