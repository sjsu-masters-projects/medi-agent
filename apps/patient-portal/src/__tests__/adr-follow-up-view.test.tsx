import { configureStore } from "@reduxjs/toolkit";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ADRFollowUpView } from "@/components/features/adr-follow-up-view";
import { ApiClientError } from "@/services/api";
import type { ADRFollowUpOverview, ADRFollowUpRequest } from "@/services/adr-follow-up";
import { authSlice, hydrateSession } from "@/store/slices/auth-slice";
import type { Locale } from "@/types";

const { fetchOverview, respond } = vi.hoisted(() => ({
    fetchOverview: vi.fn(),
    respond: vi.fn(),
}));

// Keep the real classifier: only the two network calls are replaced.
vi.mock("@/services/adr-follow-up", async (importActual) => {
    const actual = await importActual<typeof import("@/services/adr-follow-up")>();
    return {
        ...actual,
        fetchADRFollowUpOverview: fetchOverview,
        respondToADRInformationRequest: respond,
    };
});

type ViewProps = Parameters<typeof ADRFollowUpView>[0];

const STRINGS = {
    "en-US": {
        loading: "Loading your care team’s questions…",
        errorTitle: "Could not load your care team’s questions",
        retry: "Try again",
        notFoundTitle: "Request not found",
        back: "Back to messages",
        emptyTitle: "No questions right now",
        closedTitle: "This request is closed",
        answeredTitle: "Answers sent",
        openNewer: "Open the newer request",
        heading: (symptom: string) => `Reported symptom (original wording): “${symptom}”`,
        review: "Review answers",
        send: "Send to care team",
        notSure: "I’m not sure",
        sent: "Your answers were sent to your care team.",
        closedError: "This request is no longer waiting for answers. Nothing new was sent.",
        answeredLabel: "Answered",
        closedLabel: "Closed",
        recent: (count: number) => `Recent requests (${count})`,
        questionLabel: "A similar past reaction",
        yes: "Yes",
        answersHeading: "Your answers",
    },
    "es-MX": {
        loading: "Cargando las preguntas de tu equipo de atención…",
        errorTitle: "No se pudieron cargar las preguntas de tu equipo de atención",
        retry: "Intentar de nuevo",
        notFoundTitle: "No encontramos esta solicitud",
        back: "Volver a mensajes",
        emptyTitle: "No hay preguntas por ahora",
        closedTitle: "Esta solicitud está cerrada",
        answeredTitle: "Respuestas enviadas",
        openNewer: "Abrir la solicitud más reciente",
        heading: (symptom: string) => `Síntoma reportado (texto original): «${symptom}»`,
        review: "Revisar respuestas",
        send: "Enviar al equipo de atención",
        notSure: "No sé",
        sent: "Tus respuestas se enviaron a tu equipo de atención.",
        closedError: "Esta solicitud ya no espera respuestas. No se envió nada nuevo.",
        answeredLabel: "Respondida",
        closedLabel: "Cerrada",
        recent: (count: number) => `Solicitudes recientes (${count})`,
        questionLabel: "Una reacción similar anterior",
        yes: "Sí",
        answersHeading: "Tus respuestas",
    },
} as const;

const LOCALES: Locale[] = ["en-US", "es-MX"];
const REPLACEMENT_ID = "22222222-2222-4222-8222-222222222222";

function makeRequest(
    id: string,
    overrides: Partial<ADRFollowUpRequest> = {},
): ADRFollowUpRequest {
    return {
        id,
        assessmentId: "assessment-1",
        status: "pending",
        symptom: "dizziness",
        suspectMedicationName: "lisinopril",
        requestedInformation: ["similar_previous_reaction"],
        patientMessage: "",
        createdAt: "2026-10-01T10:00:00Z",
        respondedAt: null,
        closedAt: null,
        responses: [],
        replacementRequestId: null,
        ...overrides,
    };
}

function makeOverview(partial: Partial<ADRFollowUpOverview> = {}): ADRFollowUpOverview {
    return { selected: null, pending: [], recent: [], ...partial };
}

function answeredRequest(id: string, overrides: Partial<ADRFollowUpRequest> = {}) {
    return makeRequest(id, {
        status: "answered",
        respondedAt: "2026-10-06T03:30:00Z",
        responses: [{ question: "similar_previous_reaction", answer: "yes", evidence: "Once." }],
        ...overrides,
    });
}

function deferred<T>() {
    let resolve!: (value: T) => void;
    let reject!: (reason: unknown) => void;
    const promise = new Promise<T>((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return { promise, resolve, reject };
}

function closedError() {
    return new ApiClientError("closed", 422, {
        error: { code: "ADR_REQUEST_CLOSED", message: "closed" },
    });
}

function notFoundError() {
    return new ApiClientError("missing", 404, { error: { code: "NOT_FOUND", message: "missing" } });
}

function unavailableError() {
    return new ApiClientError("down", 503, null);
}

function makeStore() {
    const testStore = configureStore({ reducer: { auth: authSlice.reducer } });
    testStore.dispatch(
        hydrateSession({
            accessToken: "access-token",
            expiresAt: 9999999999,
            refreshToken: "refresh-token",
            user: { email: "maya@example.test", id: "patient-1", role: "patient" },
        }),
    );
    return testStore;
}

function renderView(props: Partial<ViewProps> = {}) {
    const testStore = makeStore();
    const tree = (next: Partial<ViewProps>) => (
        <Provider store={testStore}>
            <ADRFollowUpView locale="en-US" timeZone="UTC" {...props} {...next} />
        </Provider>
    );
    const result = render(tree({}));
    return {
        ...result,
        update: (next: Partial<ViewProps>) => result.rerender(tree(next)),
    };
}

async function answerAndSend(text: (typeof STRINGS)[Locale]) {
    fireEvent.click(await screen.findByLabelText(text.notSure));
    fireEvent.click(screen.getByRole("button", { name: text.review }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: text.send }));
}

const SCORE_TEXT = /naranjo|causality|causalidad|score|puntuaci|puntaje|probable|possible|posible/i;

describe("ADR follow-up view", () => {
    beforeEach(() => {
        fetchOverview.mockReset();
        respond.mockReset();
    });

    describe("loading", () => {
        it("announces both locales in a busy status and shows no visible text while the locale is unresolved", async () => {
            fetchOverview.mockResolvedValue(makeOverview({ pending: [makeRequest("r1")] }));

            const { container } = renderView({ locale: undefined });

            const status = screen.getByRole("status");
            expect(status).toHaveAttribute("aria-busy", "true");
            expect(status).not.toHaveAttribute("lang");
            const label = status.querySelector(".sr-only");
            expect(label).not.toBeNull();
            expect(label?.querySelector('[lang="en-US"]')).toHaveTextContent(STRINGS["en-US"].loading);
            expect(label?.querySelector('[lang="es-MX"]')).toHaveTextContent(STRINGS["es-MX"].loading);
            // Everything readable is inside the screen-reader label; the rest is skeleton.
            expect(status.textContent).toBe(label?.textContent);
            expect(screen.queryByRole("heading")).not.toBeInTheDocument();

            // A resolved overview must not reveal default-locale content before the locale resolves.
            await waitFor(() => expect(fetchOverview).toHaveBeenCalledTimes(1));
            await act(async () => {});
            expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
            expect(container).not.toHaveTextContent(STRINGS["en-US"].heading("dizziness"));
            expect(container).not.toHaveTextContent(STRINGS["es-MX"].heading("dizziness"));
        });

        it.each(LOCALES)("announces only the %s label once the locale is known", (locale) => {
            fetchOverview.mockReturnValue(new Promise(() => {}));
            const other: Locale = locale === "en-US" ? "es-MX" : "en-US";

            renderView({ locale });

            const status = screen.getByRole("status");
            expect(status).toHaveAttribute("aria-busy", "true");
            expect(status).toHaveAttribute("lang", locale);
            expect(status).toHaveTextContent(STRINGS[locale].loading);
            expect(status).not.toHaveTextContent(STRINGS[other].loading);
        });

        it("requests the overview with the bearer token and the selector", async () => {
            fetchOverview.mockResolvedValue(makeOverview());

            renderView({ requestId: "request-9", assessmentId: "assessment-9" });

            await waitFor(() =>
                expect(fetchOverview).toHaveBeenCalledWith("access-token", { requestId: "request-9" }),
            );
        });
    });

    describe("load failure", () => {
        it.each(LOCALES)("shows a localized error and retry refetches in %s", async (locale) => {
            const text = STRINGS[locale];
            fetchOverview.mockRejectedValueOnce(unavailableError());
            fetchOverview.mockResolvedValueOnce(makeOverview());

            renderView({ locale });

            expect(await screen.findByText(text.errorTitle)).toBeInTheDocument();
            expect(fetchOverview).toHaveBeenCalledTimes(1);

            fireEvent.click(screen.getByRole("button", { name: text.retry }));

            expect(await screen.findByText(text.emptyTitle)).toBeInTheDocument();
            expect(fetchOverview).toHaveBeenCalledTimes(2);
            expect(screen.queryByText(text.errorTitle)).not.toBeInTheDocument();
        });

        it("shows a loading state while the retry is in flight", async () => {
            const retry = deferred<ADRFollowUpOverview>();
            fetchOverview.mockRejectedValueOnce(new Error("boom"));
            fetchOverview.mockReturnValueOnce(retry.promise);

            renderView();

            fireEvent.click(await screen.findByRole("button", { name: STRINGS["en-US"].retry }));

            expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
            await act(async () => retry.resolve(makeOverview()));
            expect(await screen.findByText(STRINGS["en-US"].emptyTitle)).toBeInTheDocument();
        });
    });

    describe("not found", () => {
        it.each(LOCALES)("shows the not-found state and calls onBack in %s", async (locale) => {
            const text = STRINGS[locale];
            const onBack = vi.fn();
            fetchOverview.mockRejectedValue(notFoundError());

            renderView({ locale, onBack });

            expect(await screen.findByText(text.notFoundTitle)).toBeInTheDocument();
            expect(screen.queryByRole("link")).not.toBeInTheDocument();
            fireEvent.click(screen.getByRole("button", { name: text.back }));
            expect(onBack).toHaveBeenCalledTimes(1);
        });

        it.each(LOCALES)("links back to Care team messages when there is no onBack in %s", async (locale) => {
            const text = STRINGS[locale];
            fetchOverview.mockRejectedValue(notFoundError());

            renderView({ locale });

            expect(await screen.findByText(text.notFoundTitle)).toBeInTheDocument();
            expect(screen.getByRole("link", { name: text.back })).toHaveAttribute("href", "/chat?view=care-team");
            expect(screen.queryByRole("button")).not.toBeInTheDocument();
        });
    });

    describe("pending requests", () => {
        it.each(LOCALES)("renders one form per request, selected first and deduped, in %s", async (locale) => {
            const text = STRINGS[locale];
            const first = makeRequest("r1", { symptom: "dizziness" });
            const second = makeRequest("r2", { symptom: "nausea" });
            const third = makeRequest("r3", { symptom: "rash" });
            fetchOverview.mockResolvedValue(
                makeOverview({ selected: second, pending: [first, second, third] }),
            );

            renderView({ locale, requestId: "r2" });

            await screen.findByText(text.heading("nausea"));
            const headings = screen.getAllByRole("heading", { level: 2 });
            expect(headings.map((heading) => heading.textContent)).toEqual([
                text.heading("nausea"),
                text.heading("dizziness"),
                text.heading("rash"),
            ]);
            expect(screen.getAllByRole("button", { name: text.review })).toHaveLength(3);
        });
    });

    describe("selected answered request", () => {
        it.each([
            ["en-US", "America/Los_Angeles", "October 5, 2026"],
            ["en-US", undefined, "October 6, 2026"],
            ["es-MX", "America/Los_Angeles", "5 de octubre de 2026"],
            ["es-MX", undefined, "6 de octubre de 2026"],
        ] as const)(
            "shows a read-only summary dated in the patient's timezone (%s, %s)",
            async (locale, timeZone, date) => {
                const text = STRINGS[locale];
                const evidence = "It <b>eased</b> & came back\nafter the dose change.";
                const selected = answeredRequest("r1", {
                    responses: [
                        { question: "similar_previous_reaction", answer: "yes", evidence },
                        { question: "dose_response", answer: "do_not_know" },
                    ],
                });
                // Extra fields a stricter API could leak must never be shown.
                const leaky = {
                    ...selected,
                    naranjoScore: 7,
                    currentNaranjoScore: 7,
                    causality: "Probable",
                } as ADRFollowUpRequest;
                fetchOverview.mockResolvedValue(makeOverview({ selected: leaky }));

                const { container } = renderView({ locale, timeZone, requestId: "r1" });

                expect(await screen.findByText(text.answeredTitle)).toBeInTheDocument();
                const answeredOn =
                    locale === "en-US" ? `Answered on ${date}` : `Respondiste el ${date}`;
                const time = screen.getByText(answeredOn);
                expect(time.tagName).toBe("TIME");
                expect(time).toHaveAttribute("datetime", "2026-10-06T03:30:00Z");

                expect(screen.getByText(text.answersHeading)).toBeInTheDocument();
                expect(screen.getByText(text.questionLabel)).toBeInTheDocument();
                expect(screen.getByText(text.yes)).toBeInTheDocument();
                const evidenceNode = screen.getByText(
                    (_, element) => element?.tagName === "DD" && element.textContent === evidence,
                );
                expect(evidenceNode).toBeInTheDocument();
                expect(container.querySelector("b")).toBeNull();

                // No form, and no score or causality anywhere on screen.
                expect(screen.queryByRole("button", { name: text.review })).not.toBeInTheDocument();
                expect(document.body.textContent).not.toMatch(SCORE_TEXT);
                expect(document.body.textContent).not.toMatch(/\b7\b/);
            },
        );

        it("omits the date when the response time is missing", async () => {
            fetchOverview.mockResolvedValue(
                makeOverview({ selected: answeredRequest("r1", { respondedAt: null }) }),
            );

            renderView({ requestId: "r1" });

            expect(await screen.findByText(STRINGS["en-US"].answeredTitle)).toBeInTheDocument();
            expect(screen.queryByText(/Answered on/)).not.toBeInTheDocument();
        });
    });

    describe("selected cancelled request", () => {
        it.each(LOCALES)("shows closed copy and a link to the replacement in %s", async (locale) => {
            const text = STRINGS[locale];
            fetchOverview.mockResolvedValue(
                makeOverview({
                    selected: makeRequest("r1", {
                        status: "cancelled",
                        closedAt: "2026-10-02T10:00:00Z",
                        replacementRequestId: REPLACEMENT_ID,
                    }),
                }),
            );

            renderView({ locale, requestId: "r1" });

            expect(await screen.findByText(text.closedTitle)).toBeInTheDocument();
            expect(screen.queryByRole("button", { name: text.review })).not.toBeInTheDocument();
            expect(screen.getByRole("link", { name: text.openNewer })).toHaveAttribute(
                "href",
                `/chat?view=follow-up&request=${REPLACEMENT_ID}`,
            );
        });

        it.each(LOCALES)("shows no link without a replacement in %s", async (locale) => {
            const text = STRINGS[locale];
            fetchOverview.mockResolvedValue(
                makeOverview({
                    selected: makeRequest("r1", {
                        status: "cancelled",
                        closedAt: "2026-10-02T10:00:00Z",
                    }),
                }),
            );

            renderView({ locale, requestId: "r1" });

            expect(await screen.findByText(text.closedTitle)).toBeInTheDocument();
            expect(screen.queryByRole("link")).not.toBeInTheDocument();
        });
    });

    describe("empty", () => {
        it.each(LOCALES)("shows the empty state when nothing is pending or selected in %s", async (locale) => {
            fetchOverview.mockResolvedValue(makeOverview());

            renderView({ locale });

            expect(await screen.findByText(STRINGS[locale].emptyTitle)).toBeInTheDocument();
            expect(screen.queryByRole("button")).not.toBeInTheDocument();
            expect(screen.queryByRole("link")).not.toBeInTheDocument();
        });
    });

    describe("after the answers are sent", () => {
        it.each(LOCALES)(
            "keeps a focused confirmation and refetches, even if the request now reads as answered, in %s",
            async (locale) => {
                const text = STRINGS[locale];
                const pending = makeRequest("r1");
                fetchOverview.mockResolvedValueOnce(
                    makeOverview({ selected: pending, pending: [pending] }),
                );
                fetchOverview.mockResolvedValueOnce(
                    makeOverview({ selected: answeredRequest("r1") }),
                );
                respond.mockResolvedValue({ status: "answered" });

                renderView({ locale, requestId: "r1" });
                await answerAndSend(text);

                expect(respond).toHaveBeenCalledWith("access-token", "r1", [
                    { question: "similar_previous_reaction", answer: "do_not_know", evidence: undefined },
                ]);
                const confirmation = await screen.findByRole("status");
                expect(confirmation).toHaveTextContent(text.sent);
                await waitFor(() => expect(confirmation).toHaveFocus());

                await waitFor(() => expect(fetchOverview).toHaveBeenCalledTimes(2));
                await act(async () => {});

                // The refetch reads the request as answered, but the confirmation stays.
                const stillThere = screen.getByRole("status");
                expect(stillThere).toBe(confirmation);
                expect(stillThere).toHaveTextContent(text.sent);
                expect(stillThere).toHaveFocus();
                expect(screen.queryByText(text.answeredTitle)).not.toBeInTheDocument();
                expect(screen.queryByRole("button", { name: text.send })).not.toBeInTheDocument();
            },
        );

        it("keeps the confirmation when the background refetch fails", async () => {
            const text = STRINGS["en-US"];
            const pending = makeRequest("r1");
            fetchOverview.mockResolvedValueOnce(makeOverview({ selected: pending, pending: [pending] }));
            fetchOverview.mockRejectedValueOnce(unavailableError());
            respond.mockResolvedValue({ status: "answered" });

            renderView({ requestId: "r1" });
            await answerAndSend(text);

            const confirmation = await screen.findByRole("status");
            await waitFor(() => expect(fetchOverview).toHaveBeenCalledTimes(2));
            await act(async () => {});

            expect(screen.getByRole("status")).toBe(confirmation);
            expect(confirmation).toHaveTextContent(text.sent);
            expect(screen.queryByText(text.errorTitle)).not.toBeInTheDocument();
        });
    });

    describe("request closed while answering", () => {
        it.each([
            [
                "answered elsewhere",
                makeOverview({ selected: answeredRequest("r1") }),
                "answered",
            ],
            [
                "withdrawn",
                makeOverview({
                    selected: makeRequest("r1", {
                        status: "cancelled",
                        closedAt: "2026-10-02T10:00:00Z",
                    }),
                }),
                "closed",
            ],
            [
                "answered elsewhere and no longer selected",
                makeOverview({ recent: [answeredRequest("r1")] }),
                "answered",
            ],
            ["no longer listed at all", makeOverview(), "closed"],
        ] as const)("switches to the outcome without a retry (%s)", async (_label, refreshed, outcome) => {
            const text = STRINGS["en-US"];
            const pending = makeRequest("r1");
            fetchOverview.mockResolvedValueOnce(makeOverview({ selected: pending, pending: [pending] }));
            fetchOverview.mockResolvedValueOnce(refreshed);
            respond.mockRejectedValueOnce(closedError());

            renderView({ requestId: "r1" });
            await answerAndSend(text);

            const title = outcome === "answered" ? text.answeredTitle : text.closedTitle;
            expect(await screen.findByText(title)).toBeInTheDocument();
            expect(respond).toHaveBeenCalledTimes(1);
            expect(fetchOverview).toHaveBeenCalledTimes(2);
            expect(screen.queryByRole("button", { name: text.send })).not.toBeInTheDocument();
            expect(screen.queryByRole("button", { name: text.retry })).not.toBeInTheDocument();
            expect(screen.queryByText(text.errorTitle)).not.toBeInTheDocument();
            expect(screen.queryByText(text.sent)).not.toBeInTheDocument();
        });

        it("keeps the form and its closed message when the follow-up refetch fails", async () => {
            const text = STRINGS["en-US"];
            const pending = makeRequest("r1");
            fetchOverview.mockResolvedValueOnce(makeOverview({ selected: pending, pending: [pending] }));
            fetchOverview.mockRejectedValueOnce(unavailableError());
            respond.mockRejectedValueOnce(closedError());

            renderView({ requestId: "r1" });
            await answerAndSend(text);

            expect(await screen.findByRole("alert")).toHaveTextContent(text.closedError);
            await waitFor(() => expect(fetchOverview).toHaveBeenCalledTimes(2));
            await act(async () => {});

            expect(screen.queryByText(text.errorTitle)).not.toBeInTheDocument();
            expect(screen.getByText(text.heading("dizziness"))).toBeInTheDocument();
            expect(screen.getByRole("alert")).toHaveTextContent(text.closedError);
        });
    });

    describe("recent requests", () => {
        function recentRows() {
            const selected = answeredRequest("recent-1", { symptom: "cough" });
            const rows = [
                selected,
                makeRequest("recent-pending", { symptom: "pending-only" }),
                makeRequest("recent-2", {
                    status: "cancelled",
                    symptom: "rash",
                    closedAt: "2026-09-30T10:00:00Z",
                }),
                answeredRequest("recent-3", { symptom: "itch" }),
                answeredRequest("recent-4", { symptom: "fatigue" }),
                makeRequest("recent-5", { status: "cancelled", symptom: "nausea" }),
                answeredRequest("recent-6", { symptom: "sixth" }),
                answeredRequest("recent-7", { symptom: "seventh" }),
            ];
            return { selected, rows };
        }

        it.each(LOCALES)("is collapsed by default, toggles, and lists at most 5 rows in %s", async (locale) => {
            const text = STRINGS[locale];
            const { selected, rows } = recentRows();
            fetchOverview.mockResolvedValue(makeOverview({ selected, recent: rows }));

            renderView({ locale, requestId: "recent-1" });

            const toggle = await screen.findByRole("button", { name: text.recent(5) });
            expect(toggle).toHaveAttribute("aria-expanded", "false");
            const list = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
            expect(list).not.toBeNull();
            expect(list).toHaveAttribute("hidden");
            expect(screen.queryAllByRole("link")).toHaveLength(0);

            fireEvent.click(toggle);

            expect(toggle).toHaveAttribute("aria-expanded", "true");
            expect(list).not.toHaveAttribute("hidden");
            const links = within(list as HTMLElement).getAllByRole("link");
            expect(links).toHaveLength(5);
            expect(links.map((link) => link.getAttribute("href"))).toEqual([
                "/chat?view=follow-up&request=recent-1",
                "/chat?view=follow-up&request=recent-2",
                "/chat?view=follow-up&request=recent-3",
                "/chat?view=follow-up&request=recent-4",
                "/chat?view=follow-up&request=recent-5",
            ]);
            // Pending requests are answered in a form, never listed as history.
            expect(within(list as HTMLElement).queryByText("pending-only")).not.toBeInTheDocument();
            expect(within(list as HTMLElement).queryByText("sixth")).not.toBeInTheDocument();
            expect(within(list as HTMLElement).queryByText("seventh")).not.toBeInTheDocument();

            // Status badges: answered rows and closed rows.
            expect(within(list as HTMLElement).getAllByText(text.answeredLabel)).toHaveLength(3);
            expect(within(list as HTMLElement).getAllByText(text.closedLabel)).toHaveLength(2);

            // Only the selected request is marked as the current page.
            expect(links.map((link) => link.getAttribute("aria-current"))).toEqual([
                "page",
                null,
                null,
                null,
                null,
            ]);

            fireEvent.click(toggle);
            expect(toggle).toHaveAttribute("aria-expanded", "false");
            expect(list).toHaveAttribute("hidden");
        });

        it("is not rendered when there is no history", async () => {
            fetchOverview.mockResolvedValue(
                makeOverview({ selected: makeRequest("r1"), pending: [makeRequest("r1")] }),
            );

            renderView({ requestId: "r1" });

            await screen.findByText(STRINGS["en-US"].heading("dizziness"));
            expect(screen.queryByRole("button", { name: /Recent requests/ })).not.toBeInTheDocument();
        });
    });

    describe("stale and failed refreshes", () => {
        it("ignores a late response for a superseded request", async () => {
            const text = STRINGS["en-US"];
            const first = deferred<ADRFollowUpOverview>();
            fetchOverview.mockReturnValueOnce(first.promise);
            fetchOverview.mockResolvedValueOnce(
                makeOverview({ selected: makeRequest("b", { symptom: "nausea" }) }),
            );

            const view = renderView({ requestId: "a" });
            await waitFor(() => expect(fetchOverview).toHaveBeenCalledTimes(1));
            view.update({ requestId: "b" });

            expect(await screen.findByText(text.heading("nausea"))).toBeInTheDocument();
            expect(fetchOverview).toHaveBeenLastCalledWith("access-token", { requestId: "b" });

            await act(async () =>
                first.resolve(
                    makeOverview({
                        selected: answeredRequest("a", { symptom: "stale-symptom" }),
                    }),
                ),
            );

            expect(screen.queryByText(text.heading("stale-symptom"))).not.toBeInTheDocument();
            expect(screen.queryByText(text.answeredTitle)).not.toBeInTheDocument();
            expect(screen.getByText(text.heading("nausea"))).toBeInTheDocument();
        });

        it("ignores a late failure for a superseded request", async () => {
            const text = STRINGS["en-US"];
            const first = deferred<ADRFollowUpOverview>();
            fetchOverview.mockReturnValueOnce(first.promise);
            fetchOverview.mockResolvedValueOnce(makeOverview());

            const view = renderView({ requestId: "a" });
            await waitFor(() => expect(fetchOverview).toHaveBeenCalledTimes(1));
            view.update({ requestId: "b" });
            expect(await screen.findByText(text.emptyTitle)).toBeInTheDocument();

            await act(async () => first.reject(notFoundError()));

            expect(screen.queryByText(text.notFoundTitle)).not.toBeInTheDocument();
            expect(screen.getByText(text.emptyTitle)).toBeInTheDocument();
        });

        it("does not show the previous selection when the new one fails to load", async () => {
            const text = STRINGS["en-US"];
            fetchOverview.mockResolvedValueOnce(
                makeOverview({ selected: answeredRequest("a", { symptom: "cough" }) }),
            );
            fetchOverview.mockRejectedValueOnce(unavailableError());

            const view = renderView({ requestId: "a" });
            expect(await screen.findByText(text.answeredTitle)).toBeInTheDocument();

            view.update({ requestId: "b" });

            expect(await screen.findByText(text.errorTitle)).toBeInTheDocument();
            expect(screen.queryByText(text.answeredTitle)).not.toBeInTheDocument();
        });
    });
});
