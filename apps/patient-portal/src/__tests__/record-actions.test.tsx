import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RecordActions } from "@/components/features/record-actions";
import { ApiClientError } from "@/services/api";
import { DocumentParseStatus, DocumentType, type Document } from "@/types";

const { get, remove } = vi.hoisted(() => ({ get: vi.fn(), remove: vi.fn() }));
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/services/api")>()),
  api: { get, delete: remove },
}));
const source = {
  id: "source",
  patientId: "patient",
  uploadedBy: "patient",
  uploadedByRole: "patient",
  reviewStatus: "pending",
  fileName: "synthetic.pdf",
  parseStatus: DocumentParseStatus.COMPLETED,
  documentType: DocumentType.OTHER,
} as Document;
const callbacks = { onRemoved: vi.fn(), onRequest: vi.fn() };
function view(document = source, locale: "en-US" | "es-MX" = "en-US") {
  return (
    <RecordActions
      document={document}
      locale={locale}
      token="synthetic"
      actorId="patient"
      {...callbacks}
    />
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue({ can_remove: true });
  remove.mockResolvedValue(undefined);
});

describe("patient record actions", () => {
  it("requires authoritative eligibility and explicit confirmation", async () => {
    let done!: (value: unknown) => void;
    get.mockReturnValue(
      new Promise((resolve) => {
        done = resolve;
      }),
    );
    render(view());
    expect(
      screen.queryByRole("button", { name: "Remove upload" }),
    ).not.toBeInTheDocument();
    expect(remove).not.toHaveBeenCalled();
    await act(async () => done({ can_remove: true }));
    fireEvent.click(screen.getByRole("button", { name: "Remove upload" }));
    expect(remove).not.toHaveBeenCalled();
    expect(screen.getByText("Remove this upload?")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Remove upload" }));
    await waitFor(() => expect(callbacks.onRemoved).toHaveBeenCalledOnce());
    expect(remove).toHaveBeenCalledWith("/api/v1/documents/source", {
      token: "synthetic",
    });
  });

  it.each([
    { ...source, uploadedByRole: "clinician", uploadedBy: "clinician" },
    { ...source, uploadedBy: "another-patient" },
    { ...source, reviewStatus: "approved" },
    { ...source, reviewStatus: "rejected" },
    { ...source, reviewStatus: undefined },
  ] as Document[])(
    "never exposes direct removal for an ineligible source: %j",
    async (document) => {
      render(view(document));
      await waitFor(() => expect(get).toHaveBeenCalled());
      expect(
        screen.queryByRole("button", { name: "Remove upload" }),
      ).not.toBeInTheDocument();
      fireEvent.click(
        screen.getByRole("button", {
          name:
            document.uploadedByRole === "clinician"
              ? "Report an issue"
              : "Request removal or correction",
        }),
      );
      expect(callbacks.onRequest).toHaveBeenCalledOnce();
      expect(remove).not.toHaveBeenCalled();
    },
  );

  it("fails closed after a permission-read failure and offers recovery", async () => {
    get
      .mockRejectedValueOnce(new Error("unavailable"))
      .mockResolvedValueOnce({ can_remove: true });
    render(view());
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Check removal options again",
      }),
    );
    expect(
      await screen.findByRole("button", { name: "Remove upload" }),
    ).toBeEnabled();
    expect(remove).not.toHaveBeenCalled();
  });

  it("keeps a used or processing source available and routes a review request", async () => {
    get.mockResolvedValue({ can_remove: false, reason: "used_in_record" });
    render(view());
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(
      screen.queryByRole("button", { name: "Remove upload" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Request removal or correction" }),
    ).toBeEnabled();
  });

  it("switches to a care-team request after a concurrent review refusal", async () => {
    remove.mockRejectedValue(
      new ApiClientError("Review required", 409, {
        error: { code: "DOCUMENT_REMOVAL_REQUIRES_REVIEW" },
      }),
    );
    render(view());
    fireEvent.click(
      await screen.findByRole("button", { name: "Remove upload" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "can no longer be removed",
    );
    expect(
      screen.queryByRole("button", { name: "Remove upload" }),
    ).not.toBeInTheDocument();
    expect(callbacks.onRemoved).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Request removal or correction" }),
    ).toBeEnabled();
  });

  it("retries an uncertain removal with the same resource identity", async () => {
    remove
      .mockRejectedValueOnce(new Error("lost response"))
      .mockResolvedValueOnce(undefined);
    render(view());
    fireEvent.click(
      await screen.findByRole("button", { name: "Remove upload" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove upload" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Retry removal" }),
    );
    await waitFor(() => expect(callbacks.onRemoved).toHaveBeenCalledOnce());
    expect(remove.mock.calls[0]).toEqual(remove.mock.calls[1]);
  });

  it("refreshes options after a transient evidence conflict without automatically retrying removal", async () => {
    remove.mockRejectedValueOnce(
      new ApiClientError("Changed", 409, {
        error: { code: "DOCUMENT_REMOVAL_CHANGED" },
      }),
    );
    render(view());
    fireEvent.click(
      await screen.findByRole("button", { name: "Remove upload" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "record changed",
    );
    expect(
      await screen.findByRole("button", { name: "Remove upload" }),
    ).toBeEnabled();
    expect(get).toHaveBeenCalledTimes(2);
    expect(remove).toHaveBeenCalledOnce();
    expect(callbacks.onRemoved).not.toHaveBeenCalled();
  });

  it("does not apply a late successful removal to another mounted context", async () => {
    let done!: () => void;
    remove.mockReturnValue(
      new Promise<void>((resolve) => {
        done = resolve;
      }),
    );
    const { unmount } = render(view());
    fireEvent.click(
      await screen.findByRole("button", { name: "Remove upload" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove upload" }));
    unmount();
    await act(async () => done());
    expect(callbacks.onRemoved).not.toHaveBeenCalled();
  });

  it("offers neither path while eligibility is checked, then moves focus through the confirmation", async () => {
    let done!: (value: unknown) => void;
    get.mockReturnValue(new Promise((resolve) => { done = resolve; }));
    render(view());
    expect(screen.getByRole("status")).toHaveTextContent("Checking removal options…");
    expect(
      screen.queryByRole("button", { name: "Request removal or correction" }),
    ).not.toBeInTheDocument();
    await act(async () => done({ can_remove: true }));
    const start = screen.getByRole("button", { name: "Remove upload" });
    fireEvent.click(start);
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Remove upload" })).toHaveFocus();
    expect(remove).not.toHaveBeenCalled();
  });

  it("localizes the removal confirmation", async () => {
    render(view(source, "es-MX"));
    fireEvent.click(
      await screen.findByRole("button", { name: "Quitar archivo" }),
    );
    expect(screen.getByText("¿Quitar este archivo?")).toBeVisible();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeEnabled();
  });
});
