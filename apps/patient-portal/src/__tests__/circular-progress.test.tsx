import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CircularProgress } from "@/components/features/circular-progress";

describe("CircularProgress", () => {
    it("renders the percentage label", () => {
        render(<CircularProgress percent={72} />);
        expect(screen.getByText("72%")).toBeInTheDocument();
    });
});
