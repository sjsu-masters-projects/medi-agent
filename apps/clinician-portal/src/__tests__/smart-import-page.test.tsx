import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { get, post, replace, setSearchParams, getSearchParams, assign, replaceState } = vi.hoisted(() => {
    let searchParamsString = "";
    return {
        get: vi.fn(),
        post: vi.fn(),
        replace: vi.fn(),
        setSearchParams: (value: string) => {
            searchParamsString = value;
        },
        getSearchParams: () => new URLSearchParams(searchParamsString),
        assign: vi.fn(),
        replaceState: vi.fn(),
    };
});

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace, push: vi.fn() }),
    useSearchParams: () => getSearchParams(),
}));

vi.mock("react-redux", () => ({
    useSelector: () => "local-clinician-token",
}));

vi.mock("@/services/api", () => ({
    api: { get, post },
}));

import SmartImportPage from "@/app/(dashboard)/smart-import/page";

describe("SMART import page", () => {
    beforeEach(() => {
        get.mockReset();
        post.mockReset();
        replace.mockReset();
        assign.mockReset();
        replaceState.mockReset();
        setSearchParams("");
        Object.defineProperty(window, "location", {
            configurable: true,
            value: { ...window.location, assign },
        });
        Object.defineProperty(window.history, "replaceState", {
            configurable: true,
            value: replaceState,
        });
        get.mockResolvedValue([
            { id: "patient-1", first_name: "Maria", last_name: "Garcia", email: "maria@accounts.mediagent.live" },
        ]);
    });

    it("binds an EHR launch handle to the locally selected patient without displaying it", async () => {
        setSearchParams("iss=https%3A%2F%2Flaunch.smarthealthit.org%2Fv%2Fr4%2Ffhir&launch=opaque-ehr-handle");
        post.mockResolvedValue({ authorization_url: "https://sandbox.example/authorize" });

        render(<SmartImportPage />);

        await screen.findByRole("button", { name: /launch sandbox import/i });
        expect(screen.getByText(/ehr launch context received/i)).toBeInTheDocument();
        expect(screen.queryByText("opaque-ehr-handle")).not.toBeInTheDocument();
        expect(screen.queryByLabelText(/smart issuer/i)).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /launch sandbox import/i }));

        await waitFor(() => {
            expect(post).toHaveBeenCalledWith(
                "/api/v1/smart/launch",
                {
                    patient_id: "patient-1",
                    issuer: "https://launch.smarthealthit.org/v/r4/fhir",
                    launch_context: "opaque-ehr-handle",
                },
                { token: "local-clinician-token" },
            );
        });
        expect(replaceState).toHaveBeenCalledWith({}, "", "/smart-import");
        expect(assign).toHaveBeenCalledWith("https://sandbox.example/authorize");
    });

    it("refuses an incomplete EHR context before posting", async () => {
        setSearchParams("iss=https%3A%2F%2Flaunch.smarthealthit.org%2Fv%2Fr4%2Ffhir");

        render(<SmartImportPage />);

        await screen.findByRole("button", { name: /launch sandbox import/i });
        fireEvent.click(screen.getByRole("button", { name: /launch sandbox import/i }));

        expect(await screen.findByRole("alert")).toHaveTextContent(/launch context is incomplete/i);
        expect(post).not.toHaveBeenCalled();
    });

    it("shows a clear in-progress status while authorization starts", async () => {
        let resolveLaunch: ((value: { authorization_url: string }) => void) | undefined;
        post.mockReturnValue(new Promise((resolve) => { resolveLaunch = resolve; }));

        render(<SmartImportPage />);

        await screen.findByRole("button", { name: /launch sandbox import/i });
        fireEvent.click(screen.getByRole("button", { name: /launch sandbox import/i }));

        expect(await screen.findByRole("status")).toHaveTextContent(/preparing the secure smart authorization session/i);
        expect(screen.getByRole("status")).toHaveTextContent(/keep this tab open/i);
        expect(screen.getByRole("button", { name: /opening smart launch/i })).toBeDisabled();

        resolveLaunch?.({ authorization_url: "https://sandbox.example/authorize" });
        await waitFor(() => expect(assign).toHaveBeenCalledWith("https://sandbox.example/authorize"));
    });

    it("makes an idempotent import outcome explicit", async () => {
        setSearchParams("ticket=single-use-ticket-value-that-is-long-enough");
        post.mockResolvedValue({
            import_record: {
                id: "import-1",
                patient_id: "patient-1",
                status: "completed_with_warnings",
                resource_count: 0,
                candidate_fact_count: 0,
                warnings: ["No new source resources were imported because this sandbox record was already imported."],
            },
            resources: [],
        });

        render(<SmartImportPage />);

        expect(await screen.findByText(/no new smart records to review/i)).toBeInTheDocument();
        expect(screen.getByText(/repeat of a previously imported sandbox record/i)).toBeInTheDocument();
        expect(screen.getByText(/already imported/i)).toBeInTheDocument();
    });
});
