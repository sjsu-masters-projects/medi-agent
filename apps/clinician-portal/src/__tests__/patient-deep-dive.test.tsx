/**
 * Tests for AdherenceChart, SymptomTimeline, ChatTranscript, and DocumentSummary
 * components — Phase 6 risk radar and patient deep dive UI.
 *
 * Uses @testing-library/react with vitest.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AdherenceChart } from "@/components/features/adherence-chart";
import { SymptomTimeline } from "@/components/features/symptom-timeline";
import { ChatTranscript } from "@/components/features/chat-transcript";
import { DocumentSummary } from "@/components/features/document-summary";
import { AccordionItem } from "@/components/ui/accordion";

// ── Mock recharts ─────────────────────────────────────────────────────────────
// Recharts uses ResizeObserver which is not available in jsdom

vi.mock("recharts", () => ({
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
        <div data-testid="responsive-container">{children}</div>
    ),
    LineChart: ({ children }: { children: React.ReactNode }) => (
        <div data-testid="line-chart">{children}</div>
    ),
    AreaChart: ({ children }: { children: React.ReactNode }) => (
        <div data-testid="area-chart">{children}</div>
    ),
    Line: () => <div data-testid="recharts-line" />,
    Area: () => <div data-testid="recharts-area" />,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
}));

// ── Mock annotateDocument service ─────────────────────────────────────────────

vi.mock("@/services/clinicians", () => ({
    annotateDocument: vi.fn().mockResolvedValue({ status: "saved", document_id: "doc-1" }),
}));

// ── AdherenceChart tests ──────────────────────────────────────────────────────

describe("AdherenceChart", () => {
    const mockData = Array.from({ length: 30 }, (_, i) => ({
        date: `2026-03-${String(i + 1).padStart(2, "0")}`,
        score: 0.7 + i * 0.005,
        completed: 5,
        expected: 7,
    }));

    it("renders the responsive container", () => {
        render(<AdherenceChart data={mockData} />);
        expect(screen.getByTestId("responsive-container")).toBeDefined();
    });

    it("renders a line chart inside", () => {
        render(<AdherenceChart data={mockData} />);
        expect(screen.getByTestId("line-chart")).toBeDefined();
    });

    it("renders with aria label for accessibility", () => {
        const { container } = render(<AdherenceChart data={mockData} />);
        const labelledEl = container.querySelector("[aria-label]");
        expect(labelledEl?.getAttribute("aria-label")).toBe("30-day adherence chart");
    });

    it("handles empty data gracefully", () => {
        expect(() => render(<AdherenceChart data={[]} />)).not.toThrow();
    });
});

// ── SymptomTimeline tests ─────────────────────────────────────────────────────

describe("SymptomTimeline", () => {
    const mockSymptoms = [
        {
            id: "s1",
            symptom: "headache",
            severity: 3,
            created_at: "2026-03-10T09:00:00Z",
            flagged_for_adr: false,
        },
        {
            id: "s2",
            symptom: "nausea",
            severity: 7,
            created_at: "2026-03-15T14:00:00Z",
            flagged_for_adr: true,
        },
    ];

    it("renders an area chart with data", () => {
        render(<SymptomTimeline data={mockSymptoms} />);
        expect(screen.getByTestId("area-chart")).toBeDefined();
    });

    it("shows empty state when no symptoms", () => {
        render(<SymptomTimeline data={[]} />);
        expect(screen.getByText(/No symptom reports recorded/i)).toBeDefined();
    });

    it("renders legend labels", () => {
        render(<SymptomTimeline data={mockSymptoms} />);
        expect(screen.getByText(/Mild/i)).toBeDefined();
        expect(screen.getByText(/Moderate/i)).toBeDefined();
        expect(screen.getByText(/Severe/i)).toBeDefined();
    });
});

// ── ChatTranscript tests ──────────────────────────────────────────────────────

describe("ChatTranscript", () => {
    const mockMessages = [
        { role: "user", content: "I have a headache today", created_at: "2026-03-20T10:00:00Z" },
        {
            role: "assistant",
            content: "I understand. Can you rate the severity 1–10?",
            created_at: "2026-03-20T10:01:00Z",
        },
        { role: "user", content: "About a 5", created_at: "2026-03-20T10:02:00Z" },
    ];

    it("renders all messages", () => {
        render(<ChatTranscript messages={mockMessages} />);
        expect(screen.getByText("I have a headache today")).toBeDefined();
        expect(screen.getByText("About a 5")).toBeDefined();
    });

    it("shows user label for patient messages", () => {
        render(<ChatTranscript messages={[mockMessages[0]!]} />);
        expect(screen.getByText(/Patient/i)).toBeDefined();
    });

    it("shows AI Assistant label for assistant messages", () => {
        render(<ChatTranscript messages={[mockMessages[1]!]} />);
        expect(screen.getByText(/AI Assistant/i)).toBeDefined();
    });

    it("shows empty state when no messages", () => {
        render(<ChatTranscript messages={[]} />);
        expect(screen.getByText(/No chat transcript available/i)).toBeDefined();
    });

    it("renders voice message indicator when audio_url present", () => {
        const voiceMsg = {
            role: "user",
            content: "Voice note",
            created_at: "2026-03-20T10:00:00Z",
            audio_url: "https://example.com/audio.wav",
        };
        render(<ChatTranscript messages={[voiceMsg]} />);
        expect(screen.getByText(/Voice message/i)).toBeDefined();
    });
});

// ── AccordionItem tests ───────────────────────────────────────────────────────

describe("AccordionItem", () => {
    it("renders the title", () => {
        render(
            <AccordionItem title="Medications">
                <p>Metformin 500mg</p>
            </AccordionItem>,
        );
        expect(screen.getByText("Medications")).toBeDefined();
    });

    it("hides content by default when defaultOpen=false", () => {
        render(
            <AccordionItem defaultOpen={false} title="Medications">
                <p>Metformin 500mg</p>
            </AccordionItem>,
        );
        const panel = screen.getByText("Metformin 500mg").closest("div")?.parentElement;
        expect(panel?.style.maxHeight).toBe("0px");
    });

    it("shows content when defaultOpen=true", () => {
        render(
            <AccordionItem defaultOpen title="Medications">
                <p>Metformin 500mg</p>
            </AccordionItem>,
        );
        const panel = screen.getByText("Metformin 500mg").closest("div")?.parentElement;
        expect(panel?.style.maxHeight).not.toBe("0px");
    });

    it("toggles content open and closed when clicked", () => {
        render(
            <AccordionItem defaultOpen={false} title="Medications">
                <p>Metformin 500mg</p>
            </AccordionItem>,
        );
        const button = screen.getByRole("button");

        // Initially closed
        expect(button.getAttribute("aria-expanded")).toBe("false");

        // Click to open
        fireEvent.click(button);
        expect(button.getAttribute("aria-expanded")).toBe("true");

        // Click to close
        fireEvent.click(button);
        expect(button.getAttribute("aria-expanded")).toBe("false");
    });

    it("renders badge when provided", () => {
        render(
            <AccordionItem badge={<span data-testid="badge">3</span>} title="Medications">
                <p>Content</p>
            </AccordionItem>,
        );
        expect(screen.getByTestId("badge")).toBeDefined();
    });
});

// ── DocumentSummary tests ─────────────────────────────────────────────────────

describe("DocumentSummary", () => {
    const props = {
        documentId: "doc-1",
        patientId: "patient-1",
        summaryText:
            "Medications:\n- Metformin 500mg twice daily\n\nWatch For:\n- Low blood sugar\n\nFollow-up:\n- Return in 3 months",
        existingAnnotation: "",
    };

    it("renders accordion sections from parsed summary", () => {
        render(<DocumentSummary {...props} />);
        expect(screen.getByText("Medications")).toBeDefined();
    });

    it("renders clinician annotation section", () => {
        render(<DocumentSummary {...props} />);
        expect(screen.getByText(/Clinician Annotation/i)).toBeDefined();
    });

    it("shows edit button when not editing", () => {
        render(<DocumentSummary {...props} />);
        expect(screen.getByText("Edit")).toBeDefined();
    });

    it("shows textarea when Edit is clicked", () => {
        render(<DocumentSummary {...props} />);
        fireEvent.click(screen.getByText("Edit"));
        expect(screen.getByRole("textbox", { name: /annotation text/i })).toBeDefined();
    });

    it("shows existing annotation text", () => {
        render(
            <DocumentSummary
                {...props}
                existingAnnotation="Patient tolerating medication well"
            />,
        );
        expect(screen.getByText("Patient tolerating medication well")).toBeDefined();
    });

    it("save button is disabled when annotation is empty", () => {
        render(<DocumentSummary {...props} />);
        fireEvent.click(screen.getByText("Edit"));
        const saveBtn = screen.getByRole("button", { name: /save/i });
        expect(saveBtn.hasAttribute("disabled")).toBe(true);
    });

    it("calls annotateDocument when Save is clicked with text", async () => {
        const { annotateDocument } = await import("@/services/clinicians");
        render(<DocumentSummary {...props} />);
        fireEvent.click(screen.getByText("Edit"));

        const textarea = screen.getByRole("textbox", { name: /annotation text/i });
        fireEvent.change(textarea, { target: { value: "Important clinical note" } });

        const saveBtn = screen.getByRole("button", { name: /save/i });
        fireEvent.click(saveBtn);

        await waitFor(() => {
            expect(annotateDocument).toHaveBeenCalledWith(
                "patient-1",
                "doc-1",
                "Important clinical note",
            );
        });
    });
});
