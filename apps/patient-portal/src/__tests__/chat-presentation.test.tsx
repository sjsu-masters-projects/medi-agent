import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatTextarea, chatDisplayTime } from "@/components/features/chat-presentation";

describe("chat presentation", () => {
  const now = new Date(2026, 9, 10, 12);
  it.each(["en-US", "es-MX"])("formats actual message dates in %s without inventing timestamps", (locale) => {
    const today = new Date(2026, 9, 10, 11, 3);
    expect(chatDisplayTime(today, locale, now)).toBe(new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" }).format(today));
    expect(chatDisplayTime(new Date(2026, 9, 9), locale, now)).toBe(new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(-1, "day"));
    const older = new Date(2025, 9, 3);
    expect(chatDisplayTime(older, locale, now)).toBe(new Intl.DateTimeFormat(locale, { month: "short", day: "numeric", year: "numeric" }).format(older));
    expect(chatDisplayTime("invalid", locale, now)).toBe("");
  });

  it("caps textarea growth and retains accessible labeling, disabled state and multiline input", () => {
    const change = vi.fn();
    const view = render(<ChatTextarea aria-label="Message" value="Question" onChange={change} />);
    const field = screen.getByRole("textbox", { name: "Message" });
    Object.defineProperty(field, "scrollHeight", { configurable: true, value: 240 });
    view.rerender(<ChatTextarea aria-label="Message" value={"Question\nSecond line"} onChange={change} />);
    expect(field).toHaveStyle({ height: "104px" });
    expect(field).toHaveValue("Question\nSecond line");
    fireEvent.change(field, { target: { value: "Edited question" } });
    expect(change).toHaveBeenCalledOnce();
    view.rerender(<ChatTextarea aria-label="Message" value="Pending question" onChange={change} disabled />);
    expect(field).toBeDisabled();
    expect(field).toHaveValue("Pending question");
  });
});
