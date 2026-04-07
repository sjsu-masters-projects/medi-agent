import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge } from "@/components/ui/badge";

describe("Badge", () => {
    it("renders each status variant", () => {
        render(
            <div>
                <Badge variant="success">Done</Badge>
                <Badge variant="warning">Review</Badge>
                <Badge variant="danger">Critical</Badge>
            </div>,
        );

        expect(screen.getByText("Done").className).toContain("bg-green-100");
        expect(screen.getByText("Review").className).toContain("bg-yellow-100");
        expect(screen.getByText("Critical").className).toContain("bg-red-100");
    });
});
