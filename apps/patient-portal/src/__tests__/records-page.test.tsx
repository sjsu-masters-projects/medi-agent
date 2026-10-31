import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RecordsPage from "@/app/(app)/records/page";
import { DocumentParseStatus, DocumentType } from "@/types";
const destination = vi.hoisted(() => ({ params: new URLSearchParams() }));

const {
  authState,
  deleteRequest,
  dispatch,
  get,
  hashDocumentFile,
  playAssistantVoiceResponse,
  post,
  push,
  redirectToLogin,
  refreshPatientSession,
  uploadDocumentToStorage,
  writeStoredSession,
} = vi.hoisted(() => ({
  authState: {
    value: {
      accessToken: "access-token",
      expiresAt: Math.floor(Date.now() / 1000) + 3600,
      refreshToken: "refresh-token",
      user: { id: "patient-1" },
    },
  },
  deleteRequest: vi.fn(),
  dispatch: vi.fn(() => ({ unwrap: vi.fn().mockResolvedValue(undefined) })),
  get: vi.fn(),
  hashDocumentFile: vi.fn(),
  playAssistantVoiceResponse: vi.fn<typeof import("@/services/browser-voice").playAssistantVoiceResponse>(() => null),
  post: vi.fn(),
  push: vi.fn(),
  redirectToLogin: vi.fn(),
  refreshPatientSession: vi.fn(),
  uploadDocumentToStorage: vi.fn(),
  writeStoredSession: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => destination.params,
}));

vi.mock("react-redux", () => ({
  useDispatch: () => dispatch,
  useSelector: (selector: (state: unknown) => unknown) =>
    selector({
      auth: authState.value,
    }),
}));

vi.mock("@/services/api", () => ({
  api: { delete: deleteRequest, get, post },
}));

vi.mock("@/services/storage", () => ({
  hashDocumentFile,
  uploadDocumentToStorage,
}));

vi.mock("@/services/auth-redirect", () => ({
  redirectToLogin,
}));

vi.mock("@/services/auth-refresh", () => ({
  refreshPatientSession,
}));

vi.mock("@/services/auth-session", () => ({
    refreshSingleFlight: async ({ current, refreshSession }: { current: { refreshToken: string }; refreshSession: (token: string) => Promise<unknown> }) => {
        try {
            const session = await refreshSession(current.refreshToken);
            writeStoredSession(session);
            return { adopted: false, session, status: "ok" };
        } catch {
            return { status: "invalid" };
        }
    },
  writeStoredSession,
}));

vi.mock("@/services/browser-voice", () => ({
  playAssistantVoiceResponse,
}));

const profileSettings = vi.hoisted(() => ({
  locale: "en-US" as "en-US" | "es-MX",
}));
vi.mock("@/hooks/use-patient-profile", () => ({
  usePatientProfile: () => ({
    preferredLanguage: profileSettings.locale,
    timezone: "America/Los_Angeles",
  }),
  useSharedPatientProfile: () => null,
}));

describe("RecordsPage", () => {
  const sourceRecord = (review_status?: string) => ({
    id: "synthetic-source",
    file_name: "Metformin.pdf",
    patient_id: "patient-1",
    uploaded_by: "patient-1",
    uploaded_by_role: "patient",
    review_status,
    document_type: DocumentType.PRESCRIPTION,
    mime_type: "application/pdf",
    file_url: "https://example.test/metformin.pdf",
    file_size_bytes: 100,
    parsed: true,
    parse_status: DocumentParseStatus.COMPLETED,
    ai_summary: "El documento dice Metformina 500 mg con la cena.",
    visibility: "shared",
    created_at: "2026-10-28T12:00:00Z",
  });

  it("refreshes directly, shows recorded source approval, and keeps one close control with Escape/focus return", async () => {
    get.mockResolvedValue([sourceRecord("approved")]);
    render(<RecordsPage />);
    const row = await screen.findByRole("button", { name: /Metformin.pdf/ });
    expect(
      within(row).getByText("Source approved by your care team"),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "More options" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh records" }));
    await waitFor(() =>
      expect(
        get.mock.calls.filter(([url]) => url === "/api/v1/documents/"),
      ).toHaveLength(2),
    );
    row.focus();
    fireEvent.click(row);
    const dialog = screen.getByRole("dialog");
    expect(
      within(dialog).getByText("Source approved by your care team"),
    ).toBeVisible();
    expect(
      within(dialog).getByText(
        /Source approval does not approve this explanation/,
      ),
    ).toBeVisible();
    expect(
      within(dialog).getAllByRole("button", { name: /close/i }),
    ).toHaveLength(1);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(row).toHaveFocus();
  });

  it("renders short semantic sections and keeps their text visible while reading aloud", async () => {
    get.mockResolvedValue([sourceRecord("pending")]);
    const sections = [
      { kind: "overview", items: ["This document describes a prescription."] },
      {
        kind: "medicines",
        items: ["The document says Metformina 500 mg with dinner."],
      },
      {
        kind: "instructions",
        items: ["The document mentions walking if the care team confirms it."],
      },
    ];
    post.mockResolvedValue({
      available: true,
      language: "en-US",
      sections,
      summary: sections.flatMap((section) => section.items).join("\n\n"),
    });
    const stop = vi.fn();
    playAssistantVoiceResponse.mockImplementationOnce((options) => {
      options.onStart?.();
      return stop;
    });
    render(<RecordsPage />);
    fireEvent.click(await screen.findByRole("button", { name: /Metformin.pdf/ }));
    expect(
      await screen.findByRole("region", { name: "Document summary" }),
    ).toHaveTextContent("500 mg");
    expect(
      screen.getByRole("region", { name: "Document summary" }),
    ).toHaveTextContent("if the care team confirms");
    expect(
      screen.queryByRole("region", { name: "Questions for your care team" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Read summary aloud" }));
    expect(
      screen.getByRole("region", { name: "Document summary" }),
    ).toHaveTextContent("500 mg");
    expect(screen.getByRole("button", { name: "Stop reading" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Close modal" }));
    expect(stop).toHaveBeenCalledOnce();
  });

  it.each(["pending", "failed"])(
    "does not forward cached Spanish text to speech or chat when presentation is %s",
    async (state) => {
      get.mockResolvedValue([sourceRecord()]);
      let resolve!: (value: unknown) => void;
      post.mockReturnValue(
        new Promise((done) => {
          resolve = done;
        }),
      );
      render(<RecordsPage />);
      fireEvent.click(
        await screen.findByRole("button", { name: /Metformin.pdf/ }),
      );
      expect(screen.queryByText(/El documento dice/)).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Read summary aloud" }),
      ).toBeDisabled();
      if (state === "failed") {
        await act(async () => resolve({ available: false, summary: null }));
        expect(screen.getByText(/unavailable in your language/)).toBeVisible();
        expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
      }
      fireEvent.click(
        screen.getByRole("button", { name: "Ask about this document" }),
      );
      const stored = window.sessionStorage.getItem(
        "patient-portal.chat.document-context.synthetic-source",
      );
      expect(JSON.parse(stored!).summary).toBeUndefined();
      expect(playAssistantVoiceResponse).not.toHaveBeenCalled();
    },
  );

  it("does not announce an invented zero while records are loading", async () => {
    let resolve!: (rows: unknown[]) => void;
    get.mockReturnValue(new Promise((done) => { resolve = done; }));
    render(<RecordsPage />);
    expect(screen.queryByText("0 records")).not.toBeInTheDocument();
    resolve([]);
    expect(await screen.findByText("0 records")).toBeInTheDocument();
  });

  it("does not describe a failed records request as zero records", async () => {
    get.mockRejectedValue(new Error("synthetic read failure"));
    render(<RecordsPage />);
    await screen.findByText("We could not load your documents. Please try again.");
    expect(screen.queryByText("0 records")).not.toBeInTheDocument();
  });
  it("names the uploader once, with no placeholder clinic, and keeps the original filename with the source", async () => {
    get.mockResolvedValue([sourceRecord("pending")]);
    render(<RecordsPage />);
    const row = await screen.findByRole("button", { name: /Metformin.pdf/ });
    expect(within(row).getByText("Uploaded by you")).toBeVisible();
    expect(within(row).queryByText(/Your upload|Care team/)).not.toBeInTheDocument();
    fireEvent.click(row);
    const dialog = screen.getByRole("dialog");
    const original = within(dialog).getByText("Original file: Metformin.pdf");
    expect(original.closest("details")).not.toHaveAttribute("open");
    expect(within(dialog).getAllByText("Uploaded by you")).toHaveLength(1);
  });
  it("opens only the requested authorized document, retaining the original filename", async () => {
    destination.params = new URLSearchParams("document=exact-record");
    get.mockResolvedValue([
      { id: "other", file_name: "Other record.pdf", document_type: DocumentType.LAB_REPORT, created_at: "2026-10-10T12:00:00Z", parse_status: DocumentParseStatus.PENDING },
      { id: "exact-record", file_name: "Exact record.pdf", document_type: DocumentType.LAB_REPORT, created_at: "2026-10-10T12:00:00Z", parse_status: DocumentParseStatus.PENDING },
    ]);
    render(<RecordsPage />);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Exact record.pdf");
    expect(dialog).not.toHaveTextContent("Other record.pdf");
  });
  it("clears an old account's record and ignores its late list response", async () => {
    let finishOld!: (rows: unknown[]) => void;
    get.mockReturnValueOnce(new Promise((resolve) => { finishOld = resolve; }));
    const { rerender } = render(<RecordsPage />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    authState.value = { ...authState.value, accessToken: "new-account-token", user: { id: "patient-2" } };
    get.mockResolvedValueOnce([]);
    rerender(<RecordsPage />);
    await screen.findByText("0 records");
    await act(async () => finishOld([sourceRecord("approved")]));
    expect(screen.queryByRole("button", { name: /Metformin.pdf/ })).not.toBeInTheDocument();
    expect(screen.getByText("0 records")).toBeInTheDocument();
  });

  it("ignores an older refresh result after a token refresh starts a newer read", async () => {
    let finishOld!: (rows: unknown[]) => void;
    get.mockReturnValueOnce(new Promise((resolve) => { finishOld = resolve; }));
    const { rerender } = render(<RecordsPage />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    authState.value = { ...authState.value, accessToken: "refreshed-token" };
    get.mockResolvedValueOnce([]);
    rerender(<RecordsPage />);
    await screen.findByText("0 records");
    await act(async () => finishOld([sourceRecord("approved")]));
    expect(screen.queryByRole("button", { name: /Metformin.pdf/ })).not.toBeInTheDocument();
    expect(screen.getByText("0 records")).toBeInTheDocument();
  });

  it("does not open another document for an unavailable requested record", async () => {
    destination.params = new URLSearchParams("document=revoked-record");
    get.mockResolvedValue([]);
    render(<RecordsPage />);
    await screen.findByText("This document is unavailable. Refresh your records.");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  beforeEach(() => {
    destination.params = new URLSearchParams();
    profileSettings.locale = "en-US";
    authState.value = {
      accessToken: "access-token",
      expiresAt: Math.floor(Date.now() / 1000) + 3600,
      refreshToken: "refresh-token",
      user: { id: "patient-1" },
    };
    deleteRequest.mockReset();
    dispatch.mockReset();
    dispatch.mockReturnValue({ unwrap: vi.fn().mockResolvedValue(undefined) });
    get.mockReset();
    hashDocumentFile.mockReset();
    hashDocumentFile.mockResolvedValue("a".repeat(64));
    playAssistantVoiceResponse.mockReset();
    playAssistantVoiceResponse.mockReturnValue(null);
    post.mockReset();
    post.mockResolvedValue({
      available: true, language: "en-US",
      summary: "Your lab values are stable and no urgent action is needed.",
      sections: [{ kind: "overview", items: ["Your lab values are stable and no urgent action is needed."] }],
    });
    push.mockReset();
    redirectToLogin.mockReset();
    refreshPatientSession.mockReset();
    uploadDocumentToStorage.mockReset();
    writeStoredSession.mockReset();
    window.sessionStorage.clear();
  });

  it("shows document summary details and keeps the ask-about-document path available", async () => {
    get.mockResolvedValue([
      {
        ai_summary:
          "Your lab values are stable and no urgent action is needed.",
        created_at: "2026-04-20T12:00:00Z",
        document_type: DocumentType.LAB_REPORT,
        file_name: "April Lab Report.txt",
        file_size_bytes: 1200,
        file_url: "https://example.test/lab.txt",
        id: "doc-1",
        mime_type: "text/plain",
        parse_status: DocumentParseStatus.COMPLETED,
        parsed: true,
        patient_id: "patient-1",
        source_clinic: "City Health",
        uploaded_by: "patient-1",
        uploaded_by_role: "patient",
        visibility: "shared",
      },
    ]);

    render(<RecordsPage />);

    expect(
      await screen.findByText(/April Lab Report\.txt/i),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /April Lab Report\.txt/i }),
    );

    expect(await screen.findAllByText(/City Health/i)).toHaveLength(2);
    expect(await screen.findByText(/Your lab values are stable/i)).toBeInTheDocument();
    expect(
      screen.getByText(/not a newly approved care plan/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /ask about this document/i }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /ask about this document/i }),
    );

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/chat?document=doc-1");
    });
  });

  it.each(["patient", "clinician"])("shows a duplicate explanation in both languages without assuming its uploader (%s)", async (uploader) => {
    get.mockResolvedValue([
      {
        id: "duplicate-doc",
        patient_id: "patient-1",
        uploaded_by: uploader === "patient" ? "patient-1" : "clinician-1",
        uploaded_by_role: uploader,
        document_type: DocumentType.OTHER,
        file_name: "duplicate.pdf",
        file_url: "https://example.test/duplicate.pdf",
        file_size_bytes: 1024,
        mime_type: "application/pdf",
        parsed: true,
        parse_status: DocumentParseStatus.DUPLICATE,
        summary_status: "not_required",
        ai_summary: "Stale duplicate summary must not be shown",
        visibility: "shared",
        created_at: "2026-10-10T18:00:00Z",
      },
    ]);
    const { rerender } = render(<RecordsPage />);
    await screen.findByText("duplicate.pdf");
    expect(screen.getByText("Duplicate upload")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /duplicate.pdf/ }));
    expect(
      screen.getByText(/This file is already in your records/),
    ).toBeInTheDocument();
    profileSettings.locale = "es-MX";
    rerender(<RecordsPage />);
    expect(
      screen.getByText(/Este mismo archivo ya está en tus documentos/),
    ).toBeInTheDocument();
    // The explanation and disclaimer follow the saved patient language.
    expect(screen.getByText(/Esta explicación describe el documento subido/)).toHaveAttribute("lang", "es-MX");
    profileSettings.locale = "en-US";
    rerender(<RecordsPage />);
    expect(
      screen.getByText(/This file is already in your records/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Stale duplicate summary/),
    ).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
    expect(
      screen.queryByText(/There is no extracted information/),
    ).not.toBeInTheDocument();
  });

  it("says why a parsed document has no explanation instead of showing nothing", async () => {
    get.mockResolvedValue([
      {
        ai_summary: null,
        created_at: "2026-04-20T12:00:00Z",
        document_type: DocumentType.LAB_REPORT,
        file_name: "April Lab Report.txt",
        file_size_bytes: 1200,
        file_url: "https://example.test/lab.txt",
        id: "doc-1",
        mime_type: "text/plain",
        parse_status: DocumentParseStatus.COMPLETED,
        parsed: true,
        patient_id: "patient-1",
        source_clinic: "City Health",
        summary_failure_code: "provider_unavailable",
        summary_status: "failed",
        uploaded_by: "patient-1",
        uploaded_by_role: "patient",
        visibility: "shared",
      },
    ]);

    render(<RecordsPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: /April Lab Report\.txt/i }),
    );

    // The document parsed fine, so the old "after parsing completes" placeholder
    // would have promised something that was never coming.
    expect(
      await screen.findByText(
        /explanation is not available for this document/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/after parsing completes/i),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /ask about this document/i }),
    );

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/chat?document=doc-1");
    });
    // The reason an explanation is missing is not itself a document summary, and must
    // never be carried into the chat as one.
    const stored = window.sessionStorage.getItem(
      "patient-portal.chat.document-context.doc-1",
    );
    expect(stored).not.toBeNull();
    expect(JSON.parse(stored as string).summary).toBeUndefined();
  });

  it("tells a patient an owed explanation is still being prepared", async () => {
    get.mockResolvedValue([
      {
        ai_summary: null,
        created_at: "2026-04-20T12:00:00Z",
        document_type: DocumentType.LAB_REPORT,
        file_name: "April Lab Report.txt",
        file_size_bytes: 1200,
        file_url: "https://example.test/lab.txt",
        id: "doc-1",
        mime_type: "text/plain",
        parse_status: DocumentParseStatus.COMPLETED,
        parsed: true,
        patient_id: "patient-1",
        summary_status: "pending",
        uploaded_by: "patient-1",
        uploaded_by_role: "patient",
        visibility: "shared",
      },
    ]);

    render(<RecordsPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: /April Lab Report\.txt/i }),
    );

    expect(
      await screen.findByText(/still being prepared/i),
    ).toBeInTheDocument();
  });

  it("removes only a patient-owned pending upload after confirmation", async () => {
    const rows = [
      {
        ai_summary: "Discharge instructions are ready.",
        created_at: "2026-04-20T12:00:00Z",
        document_type: DocumentType.DISCHARGE_SUMMARY,
        file_name: "Discharge Summary.txt",
        file_size_bytes: 1200,
        file_url: "https://example.test/discharge.txt",
        id: "doc-delete",
        mime_type: "text/plain",
        parse_status: DocumentParseStatus.COMPLETED,
        parsed: true,
        patient_id: "patient-1",
        source_clinic: "City Health",
        uploaded_by: "patient-1",
        uploaded_by_role: "patient",
        review_status: "pending",
        visibility: "shared",
      },
    ];
    get.mockImplementation(async (url: string) => url.endsWith("/removal") ? { can_remove: true } : url.endsWith("/results") ? [] : rows);
    deleteRequest.mockResolvedValue(undefined);

    render(<RecordsPage />);

    expect(
      await screen.findByText(/Discharge Summary\.txt/i),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /Discharge Summary\.txt/i }),
    );
    fireEvent.click(await screen.findByRole("button", { name: /^remove upload$/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /^remove upload$/i }),
    );

    await waitFor(() => {
      expect(deleteRequest).toHaveBeenCalledWith(
        "/api/v1/documents/doc-delete",
        {
          token: "access-token",
        },
      );
    });
    await waitFor(() => {
      expect(
        screen.queryByText(/Discharge Summary\.txt/i),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByText(/No records yet/i)).toBeInTheDocument();
    expect(screen.getByText("Your upload was removed.")).toBeInTheDocument();
  });

  it("does not infer a clinical type from an uploaded PDF filename", async () => {
    get.mockResolvedValue([]);
    uploadDocumentToStorage.mockResolvedValue(
      "patient-1/vatsal-discharge-summary.pdf",
    );
    post.mockResolvedValue({
      ai_summary: null,
      created_at: "2026-04-20T12:00:00Z",
      document_type: DocumentType.DISCHARGE_SUMMARY,
      file_name: "vatsal-discharge-summary.pdf",
      file_size_bytes: 1400,
      file_url: "https://example.test/discharge.pdf",
      id: "doc-upload",
      mime_type: "application/pdf",
      parse_status: DocumentParseStatus.PENDING,
      parsed: false,
      patient_id: "patient-1",
      source_clinic: null,
      uploaded_by: "patient-1",
      uploaded_by_role: "patient",
      visibility: "shared",
    });

    const { container } = render(<RecordsPage />);
    const input =
      container.querySelector<HTMLInputElement>('input[type="file"]');
    const file = new File(["test"], "vatsal-discharge-summary.pdf", {
      type: "application/pdf",
    });

    fireEvent.change(input!, { target: { files: [file] } });

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        "/api/v1/documents/",
        expect.objectContaining({
          document_type: DocumentType.OTHER,
          file_name: "vatsal-discharge-summary.pdf",
        }),
        { token: "access-token" },
      );
    });
  });

  it("rejects unsupported files before storage or document registration", async () => {
    get.mockResolvedValue([]);

    const { container } = render(<RecordsPage />);
    const input =
      container.querySelector<HTMLInputElement>('input[type="file"]');
    const textFile = new File(["synthetic QA"], "prescription.txt", {
      type: "text/plain",
    });

    await screen.findByText(/No records yet/i);
    fireEvent.change(input!, { target: { files: [textFile] } });

    expect(
      await screen.findByText(
        "Choose a PDF, JPG, PNG, WebP, or TIFF file up to 20 MB.",
      ),
    ).toBeInTheDocument();
    expect(input).toHaveAttribute(
      "accept",
      ".pdf,.jpg,.jpeg,.png,.webp,.tif,.tiff",
    );
    expect(uploadDocumentToStorage).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
    // An upload problem is not a records-loading failure, and its action reopens the picker.
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Could not upload this file");
    expect(screen.queryByText("Could not load records")).not.toBeInTheDocument();
    expect(screen.getByText(/No records yet/i)).toBeInTheDocument();
    const pick = vi.spyOn(input!, "click");
    fireEvent.click(within(alert).getByRole("button", { name: "Choose another file" }));
    expect(pick).toHaveBeenCalledOnce();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("starts candidate-only ingestion after uploading the file", async () => {
    get.mockResolvedValue([]);
    uploadDocumentToStorage.mockResolvedValue("patient-1/lab-results.pdf");
    let resolveCreate:
      | ((document: Record<string, unknown>) => void)
      | undefined;
    const createdDocument = {
      ai_summary: null,
      created_at: "2026-04-20T12:00:00Z",
      document_type: DocumentType.LAB_REPORT,
      file_name: "lab-results.pdf",
      file_size_bytes: 1400,
      file_url: "https://example.test/lab-results.pdf",
      id: "doc-upload-order",
      mime_type: "application/pdf",
      parse_status: DocumentParseStatus.PENDING,
      parsed: false,
      patient_id: "patient-1",
      source_clinic: null,
      uploaded_by: "patient-1",
      uploaded_by_role: "patient",
      visibility: "shared",
    };
    post.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveCreate = resolve;
        }),
    );

    const { container } = render(<RecordsPage />);
    const input =
      container.querySelector<HTMLInputElement>('input[type="file"]');
    fireEvent.change(input!, {
      target: {
        files: [
          new File(["test"], "lab-results.pdf", { type: "application/pdf" }),
        ],
      },
    });

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenLastCalledWith(
      "/api/v1/documents/",
      expect.objectContaining({
        file_path: "patient-1/lab-results.pdf",
        content_hash: "a".repeat(64),
        start_ingestion: true,
      }),
      { token: "access-token" },
    );

    resolveCreate!(createdDocument);

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  });

  it("fails visibly and safely when an upload session cannot be refreshed", async () => {
    authState.value = {
      accessToken: "expired-access-token",
      expiresAt: Math.floor(Date.now() / 1000) - 60,
      refreshToken: "refresh-token",
      user: { id: "patient-1" },
    };
    get.mockResolvedValue([]);
    refreshPatientSession.mockRejectedValue(new Error("Refresh failed"));

    const { container } = render(<RecordsPage />);
    const input =
      container.querySelector<HTMLInputElement>('input[type="file"]');
    fireEvent.change(input!, {
      target: {
        files: [
          new File(["test"], "lab-results.pdf", { type: "application/pdf" }),
        ],
      },
    });

    expect(
      await screen.findByText(
        /your session expired. please sign in again before uploading/i,
      ),
    ).toBeInTheDocument();
    expect(refreshPatientSession).toHaveBeenCalledWith("refresh-token");
    expect(redirectToLogin).toHaveBeenCalledWith({ reason: "session_expired" });
    expect(uploadDocumentToStorage).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
  });

  it("reads the visible document summary aloud", async () => {
    get.mockResolvedValue([
      {
        ai_summary:
          "Your lab values are stable and no urgent action is needed.",
        created_at: "2026-04-20T12:00:00Z",
        document_type: DocumentType.LAB_REPORT,
        file_name: "April Lab Report.txt",
        file_size_bytes: 1200,
        file_url: "https://example.test/lab.txt",
        id: "doc-1",
        mime_type: "text/plain",
        parse_status: DocumentParseStatus.COMPLETED,
        parsed: true,
        patient_id: "patient-1",
        source_clinic: "City Health",
        uploaded_by: "patient-1",
        uploaded_by_role: "patient",
        visibility: "shared",
      },
    ]);

    render(<RecordsPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: /April Lab Report\.txt/i }),
    );
    await waitFor(() => expect(screen.getByRole("button", { name: /read summary aloud/i })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /read summary aloud/i }));

    expect(playAssistantVoiceResponse).toHaveBeenCalledWith(
      expect.objectContaining({
        language: "en-US",
        text: "Your lab values are stable and no urgent action is needed.",
      }),
    );
  });

  it("uses the saved Spanish locale for both the interface and structured explanation", async () => {
    profileSettings.locale = "es-MX";
    get.mockResolvedValue([
      {
        id: "source-record",
        patient_id: "patient-1",
        uploaded_by: "patient-1",
        uploaded_by_role: "patient",
        document_type: DocumentType.PRESCRIPTION,
        file_name: "Morgan-Ellis-Hidratacion-Reviewed.pdf",
        mime_type: "image/png",
        file_url: "https://example.test/source.png",
        parsed: true,
        parse_status: DocumentParseStatus.COMPLETED,
        summary_status: "completed",
        ai_summary: "Exact reviewed source wording.",
        visibility: "shared",
        created_at: "2026-10-10T18:00:00Z",
      },
    ]);
    post.mockResolvedValue({ available: true, language: "es-MX", summary: "El documento describe tu receta.", sections: [{ kind: "overview", items: ["El documento describe tu receta."] }] });
    render(<RecordsPage />);
    expect(await screen.findByText("Mis documentos")).toBeInTheDocument();
    expect(await screen.findByText("receta médica")).toBeInTheDocument();
    const file = screen.getByRole("button", {
      name: /Morgan-Ellis-Hidratacion-Reviewed.pdf/,
    });
    expect(file.querySelector("h3")).toHaveClass("break-words");
    expect(file.querySelector("h3")).not.toHaveClass("truncate");
    fireEvent.click(file);
    expect(await screen.findByText("El documento describe tu receta.")).toBeInTheDocument();
    expect(screen.queryByText("Exact reviewed source wording.")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Preguntar sobre este documento" }),
    ).toBeInTheDocument();
    expect(
      screen
        .getByText("Documento original", { selector: "summary span" })
        .closest("details"),
    ).not.toHaveAttribute("open");
    expect(
      screen.getByRole("button", { name: "Cerrar ventana" }),
    ).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith("/api/v1/documents/source-record/explain", { language: "es-MX", structured: true }, expect.objectContaining({ token: "access-token" }));
    expect(screen.queryByText("Secure records")).not.toBeInTheDocument();
  });

  it("localizes a missing explanation and processing status without exposing failure codes", async () => {
    profileSettings.locale = "es-MX";
    get.mockResolvedValue([
      {
        id: "failed-record",
        document_type: DocumentType.OTHER,
        file_name: "source-unreadable.pdf",
        created_at: "2026-10-10T18:00:00Z",
        parsed: false,
        parse_status: DocumentParseStatus.NEEDS_OCR,
        parse_failure_code: "needs_ocr",
        ai_summary: null,
        summary_status: "failed",
      },
    ]);
    render(<RecordsPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: /source-unreadable.pdf/ }),
    );
    expect(screen.getByText(/No pudimos leer esta imagen/)).toBeInTheDocument();
    expect(screen.queryByText("needs_ocr")).not.toBeInTheDocument();
    expect(
      screen.getByText("Necesita revisión del equipo de atención"),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("shows a neutral Spanish recovery state instead of a raw request error", async () => {
    profileSettings.locale = "es-MX";
    get.mockRejectedValue(new Error("internal_schema private.patient_id"));
    render(<RecordsPage />);
    expect(
      await screen.findByText(
        "No pudimos cargar tus documentos. Inténtalo de nuevo.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Intentar de nuevo" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/internal_schema/)).not.toBeInTheDocument();
  });

  it("loads test results only for the document a patient opens", async () => {
    const record = (id: string, fileName: string, parseStatus: string = DocumentParseStatus.COMPLETED) => ({
      id,
      patient_id: "patient-1",
      uploaded_by: "patient-1",
      uploaded_by_role: "patient",
      document_type: DocumentType.LAB_REPORT,
      file_name: fileName,
      file_url: `https://example.test/${id}.pdf`,
      file_size_bytes: 1024,
      mime_type: "application/pdf",
      parsed: parseStatus === DocumentParseStatus.COMPLETED,
      parse_status: parseStatus,
      ai_summary: "Summary",
      source_clinic: "City Health",
      visibility: "shared",
      created_at: "2026-10-10T12:00:00Z",
    });
    get.mockImplementation(async (url: string) => {
      if (url === "/api/v1/documents/") {
        return [
          record("lab-a", "Lab A.pdf"),
          record("lab-b", "Lab B.pdf"),
          record("lab-c", "Lab C.pdf", DocumentParseStatus.PROCESSING),
        ];
      }
      if (url === "/api/v1/documents/lab-b/results") {
        return [
          { kind: "lab_result", name: "Potassium", value: "6.9", unit: "mmol/L", reference_range: "3.5-5.1", flag: "HH", flag_meaning: "critical", range_status: "above", panel: null, observed_at: null, page: 1, reviewed: false },
        ];
      }
      throw new Error(`unexpected ${url}`);
    });
    const resultCalls = () => get.mock.calls.filter(([url]) => String(url).endsWith("/results"));

    render(<RecordsPage />);
    await screen.findByRole("button", { name: /Lab A\.pdf/ });
    expect(resultCalls()).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: /Lab C\.pdf/ }));
    await screen.findByRole("dialog");
    // A document still being read has no results yet, so nothing is requested.
    expect(resultCalls()).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Close modal" }));

    fireEvent.click(screen.getByRole("button", { name: /Lab B\.pdf/ }));
    const section = await screen.findByRole("region", { name: "Test results" });
    expect(resultCalls()).toEqual([
      ["/api/v1/documents/lab-b/results", expect.objectContaining({ token: "access-token" })],
    ]);
    expect(section).toHaveTextContent("Potassium");
    expect(section).toHaveTextContent("Contact your care team today.");
    expect(section).toHaveTextContent("Not yet reviewed by your care team");
  });

  describe("state feedback (REC-001-MO)", () => {
    const processing = {
      ...sourceRecord("pending"),
      id: "loaded-processing",
      file_name: "Loaded scan.pdf",
      parsed: false,
      parse_status: DocumentParseStatus.PROCESSING,
      ai_summary: null,
    };
    const itemCalls = () =>
      get.mock.calls.filter(([url]) => url === "/api/v1/documents/loaded-processing");
    const listCalls = () =>
      get.mock.calls.filter(([url]) => url === "/api/v1/documents/");
    const advance = (ms: number) =>
      act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
      });

    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
    });
    afterEach(() => {
      Reflect.deleteProperty(document, "visibilityState");
      vi.useRealTimers();
    });

    it("watches a document that was already processing on load and announces when it is ready", async () => {
      get.mockImplementation(async (url: string) =>
        url === "/api/v1/documents/"
          ? [processing]
          : url.endsWith("/results")
            ? []
            : { ...processing, parsed: true, parse_status: DocumentParseStatus.COMPLETED, ai_summary: "Ready summary" },
      );
      render(<RecordsPage />);
      const row = await screen.findByRole("button", { name: /Loaded scan\.pdf/ });
      expect(within(row).getByText("Reading")).toBeInTheDocument();
      await advance(3_000);
      expect(itemCalls()[0]).toEqual([
        "/api/v1/documents/loaded-processing",
        expect.objectContaining({ token: "access-token" }),
      ]);
      expect(await screen.findByText("Loaded scan is ready to view.")).toBeInTheDocument();
      expect(within(row).queryByText("Reading")).not.toBeInTheDocument();
    });

    it("keeps watching after extraction until the stored summary is available", async () => {
      const waiting = { ...processing, parsed: true, parse_status: DocumentParseStatus.COMPLETED, summary_status: "pending" };
      let reads = 0;
      get.mockImplementation(async (url: string) => {
        if (url === "/api/v1/documents/") return [waiting];
        if (url !== "/api/v1/documents/loaded-processing") return [];
        reads++;
        const update = { ...waiting, file_url: `https://example.test/renewed-${reads}.pdf` };
        return reads === 1 ? update : { ...update, ai_summary: "The document says Metformina 500 mg.", summary_status: "ready" };
      });
      post.mockResolvedValue({ available: true, language: "en-US", summary: "The document says Metformina 500 mg.", sections: [{ kind: "medicines", items: ["The document says Metformina 500 mg."] }] });
      render(<RecordsPage />);
      fireEvent.click(await screen.findByRole("button", { name: /Loaded scan\.pdf/ }));
      await advance(3_000);
      expect(reads).toBe(1);
      expect(post).not.toHaveBeenCalled();
      expect(screen.queryByText("Loaded scan is ready to view.")).not.toBeInTheDocument();
      expect(screen.getByText(/still being prepared/i)).toBeInTheDocument();
      expect(screen.getByText("Download original").closest("a")).toHaveAttribute("href", waiting.file_url);
      await advance(6_000);
      expect(reads).toBe(2);
      expect(await screen.findByText("Loaded scan is ready to view.")).toBeInTheDocument();
      expect(await screen.findByText("The document says Metformina 500 mg.")).toBeInTheDocument();
      expect(screen.getByText("Download original").closest("a")).toHaveAttribute("href", waiting.file_url);
      await advance(30_000);
      expect(reads).toBe(2);
    });

    it("labels a failed document's action as a new upload, not a retry", async () => {
      get.mockImplementation(async (url: string) =>
        url === "/api/v1/documents/"
          ? [processing]
          : { ...processing, parse_status: DocumentParseStatus.FAILED, parse_failure_code: "source_unreadable" },
      );
      render(<RecordsPage />);
      await screen.findByRole("button", { name: /Loaded scan\.pdf/ });
      await advance(3_000);
      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("Document processing failed");
      expect(within(alert).getByRole("button", { name: "Upload another" })).toBeEnabled();
      expect(within(alert).queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
      expect(screen.getByText("We could not process Loaded scan.")).toBeInTheDocument();
    });

    it("pauses while hidden, stops after ten minutes without moving dots, and resumes on Refresh", async () => {
      get.mockImplementation(async (url: string) =>
        url === "/api/v1/documents/" ? [processing] : processing,
      );
      render(<RecordsPage />);
      const row = await screen.findByRole("button", { name: /Loaded scan\.pdf/ });
      Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
      await advance(60_000);
      expect(itemCalls()).toHaveLength(0);
      Reflect.deleteProperty(document, "visibilityState");
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"));
      });
      await advance(0);
      expect(itemCalls()).toHaveLength(1);

      await advance(11 * 60_000);
      expect(within(row).getByText("Still processing")).toBeVisible();
      expect(within(row).queryByText("Reading")).not.toBeInTheDocument();
      const stoppedAt = itemCalls().length;
      await advance(5 * 60_000);
      expect(itemCalls()).toHaveLength(stoppedAt);

      fireEvent.click(row);
      const dialog = screen.getByRole("dialog");
      expect(within(dialog).getByText(/We stopped checking automatically/)).toBeVisible();
      fireEvent.click(within(dialog).getByRole("button", { name: "Refresh records" }));
      await waitFor(() => expect(listCalls()).toHaveLength(2));
      await waitFor(() =>
        expect(within(dialog).queryByText(/We stopped checking automatically/)).not.toBeInTheDocument(),
      );
      await advance(3_000);
      expect(itemCalls()).toHaveLength(stoppedAt + 1);
    });

    it("shows moving progress and a slow note while the explanation is prepared", async () => {
      get.mockResolvedValue([sourceRecord("pending")]);
      post.mockReturnValue(new Promise(() => {}));
      render(<RecordsPage />);
      fireEvent.click(await screen.findByRole("button", { name: /Metformin.pdf/ }));
      expect(screen.getByText("Preparing your explanation…")).toBeVisible();
      expect(screen.queryByText(/taking longer than usual/)).not.toBeInTheDocument();
      await advance(15_000);
      expect(screen.getByText(/taking longer than usual/)).toBeVisible();
      expect(screen.getByRole("button", { name: "Read summary aloud" })).toBeDisabled();
    });

    it("keeps the last count and says a refresh failed when records are already shown", async () => {
      get.mockResolvedValueOnce([sourceRecord("approved")]);
      render(<RecordsPage />);
      expect(await screen.findByText("1 record")).toBeInTheDocument();
      let fail!: (error: Error) => void;
      get.mockReturnValueOnce(new Promise((_, reject) => { fail = reject; }));
      fireEvent.click(screen.getByRole("button", { name: "Refresh records" }));
      expect(screen.getByText("1 record")).toBeInTheDocument();
      await act(async () => fail(new Error("synthetic refresh failure")));
      expect(await screen.findByText("Could not refresh records")).toBeInTheDocument();
      expect(screen.queryByText("Action failed")).not.toBeInTheDocument();
      expect(screen.getByText("1 record")).toBeInTheDocument();
    });
  });
});
