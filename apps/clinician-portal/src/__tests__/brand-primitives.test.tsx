import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Icon } from "@/components/ui/icons";
import { ApprovalSeal } from "@/components/ui/approval-seal";
import { AiChip } from "@/components/ui/ai-chip";

describe("Brand primitives", () => {
    it("keeps icons decorative while preserving the action label", () => {
        const { container } = render(<button aria-label="Open records"><Icon name="folder" /></button>);
        expect(screen.getByRole("button", { name: "Open records" })).toBeInTheDocument();
        expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    });
    it("keeps approved and AI attribution distinct and uses caller-supplied copy", () => {
        render(<><ApprovalSeal pill>Aprobado por tu equipo</ApprovalSeal><AiChip>Borrador de IA</AiChip></>);
        expect(screen.getByText("Aprobado por tu equipo")).toBeInTheDocument();
        expect(screen.getByText("Borrador de IA")).toBeInTheDocument();
    });
});
