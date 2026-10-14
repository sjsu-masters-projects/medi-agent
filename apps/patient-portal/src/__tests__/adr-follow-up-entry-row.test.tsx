import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ADRFollowUpEntryRow } from "@/components/features/adr-follow-up-entry-row";
const pending = vi.hoisted(() => ({ count: 0, loaded: true }));
vi.mock("@/hooks/use-pending-adr-follow-ups", () => ({
  usePendingADRFollowUps: () => ({ count: pending.count, loaded: pending.loaded }),
}));
describe("ADRFollowUpEntryRow", () => {
  beforeEach(() => { pending.count = 0; pending.loaded = true; });
  it.each([[0, true], [2, false], [0, false]])("renders nothing for count %i, loaded %s", (count, loaded) => {
    pending.count = count;
    pending.loaded = loaded;
    const { container } = render(<ADRFollowUpEntryRow locale="en-US" />);
    expect(container).toBeEmptyDOMElement();
  });
  it.each([
    ["en-US", 1, "Questions from your care team", "1 request is waiting for your answers"],
    ["en-US", 2, "Questions from your care team", "2 requests are waiting for your answers"],
    ["es-MX", 1, "Preguntas de tu equipo de atención", "1 solicitud espera tus respuestas"],
    ["es-MX", 2, "Preguntas de tu equipo de atención", "2 solicitudes esperan tus respuestas"],
  ] as const)("shows a localized, tappable link in %s for %i pending", (locale, count, title, detail) => {
    pending.count = count;
    render(<ADRFollowUpEntryRow locale={locale} />);
    const link = screen.getByRole("link", { name: new RegExp(title) });
    expect(link).toHaveTextContent(title);
    expect(link).toHaveTextContent(detail);
    expect(link).toHaveAttribute("href", "/chat?view=follow-up");
    expect(link).toHaveAttribute("lang", locale);
    expect(link).toHaveClass("min-h-11");
  });
});
