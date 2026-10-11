import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TodayTaskContent } from "@/components/features/today-presentation";
import { getTodayCopy } from "@/content/today-copy";
import type { FeedTask } from "@/types";

const task = (contentLocale?: FeedTask["contentLocale"]): FeedTask => ({
    id: "obligation:1:unscheduled", type: "obligation", targetId: "1", status: "pending",
    name: "Revise su glucosa en ayunas", frequency: "Daily", contentLocale,
});

function renderTask(locale: "en-US" | "es-MX", contentLocale?: FeedTask["contentLocale"]) {
    render(<TodayTaskContent task={task(contentLocale)} copy={getTodayCopy(locale)} status="active" timeLabel="Any time" disabled={false} onComplete={() => undefined} onBarrier={() => undefined} />);
}

describe("Today wording language", () => {
    it("labels an older single-language item written in the other language", () => {
        renderTask("en-US", "es-MX");
        expect(screen.getByText("Written in Spanish by your care team")).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "Revise su glucosa en ayunas" })).toHaveAttribute("lang", "es-MX");
    });

    it.each([["es-MX", "es-MX"], ["en-US", undefined]] as const)("shows no label when %s wording matches or is unknown", (locale, contentLocale) => {
        renderTask(locale, contentLocale);
        expect(screen.queryByText(/by your care team|por tu equipo de atención/)).not.toBeInTheDocument();
    });
});
