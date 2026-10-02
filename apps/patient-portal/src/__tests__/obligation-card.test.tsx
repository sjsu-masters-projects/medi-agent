import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ObligationCard } from "@/components/features/obligation-card";

describe("ObligationCard patient labels", () => {
    it.each(["hydration", "monitoring", "follow_up", "custom"] as const)("uses meaningful %s labels without classifying provenance as custom", (type) => {
        render(<ObligationCard id="care-1" description="Approved activity" instructions="Follow this reviewed instruction" type={type} time="" status="active" onMarkComplete={vi.fn()} />);
        expect(screen.getByText("Follow this reviewed instruction")).toBeInTheDocument();
        expect(screen.queryByText("Custom task")).not.toBeInTheDocument();
        expect(screen.getByText(type === "hydration" ? "Hydration" : type === "monitoring" ? "Check" : type === "follow_up" ? "Follow-up" : "Care")).toBeInTheDocument();
    });
});
