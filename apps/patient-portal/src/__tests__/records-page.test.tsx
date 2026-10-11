import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RecordsPage from "@/app/(app)/records/page";
import { DocumentParseStatus, DocumentType } from "@/types";

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
  playAssistantVoiceResponse: vi.fn(() => null),
  post: vi.fn(),
  push: vi.fn(),
  redirectToLogin: vi.fn(),
  refreshPatientSession: vi.fn(),
  uploadDocumentToStorage: vi.fn(),
  writeStoredSession: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
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
  beforeEach(() => {
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

    expect(await screen.findAllByText(/City Health/i)).toHaveLength(3);
    expect(screen.getByText(/Your lab values are stable/i)).toBeInTheDocument();
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

  it("shows a duplicate explanation in both languages without asking the model to reprocess it", async () => {
    get.mockResolvedValue([
      {
        id: "duplicate-doc",
        patient_id: "patient-1",
        uploaded_by: "patient-1",
        uploaded_by_role: "patient",
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
    render(<RecordsPage />);
    await screen.findByText("duplicate.pdf");
    expect(screen.getByText("Duplicate upload")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /duplicate.pdf/ }));
    expect(
      screen.getByText(/These exact file contents were already processed/),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "es-MX" },
    });
    expect(
      screen.getByText(/Este mismo archivo ya se procesó/),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "en-US" },
    });
    expect(
      screen.getByText(/These exact file contents were already processed/),
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

  it("deletes a selected document after confirmation", async () => {
    get.mockResolvedValue([
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
        visibility: "shared",
      },
    ]);
    deleteRequest.mockResolvedValue(undefined);

    render(<RecordsPage />);

    expect(
      await screen.findByText(/Discharge Summary\.txt/i),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /Discharge Summary\.txt/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: /delete document/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /delete permanently/i }),
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
    fireEvent.click(
      screen.getByRole("button", { name: /read summary aloud/i }),
    );

    expect(playAssistantVoiceResponse).toHaveBeenCalledWith(
      expect.objectContaining({
        language: "en-US",
        text: "Your lab values are stable and no urgent action is needed.",
      }),
    );
  });

  it("uses the saved Spanish locale for records chrome and preserves cached clinical wording without translation", async () => {
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
    render(<RecordsPage />);
    expect(await screen.findByText("Mis documentos")).toBeInTheDocument();
    expect(await screen.findByText("receta médica")).toBeInTheDocument();
    const file = screen.getByRole("button", {
      name: /Morgan-Ellis-Hidratacion-Reviewed.pdf/,
    });
    expect(file.querySelector("h3")).toHaveClass("break-words");
    expect(file.querySelector("h3")).not.toHaveClass("truncate");
    fireEvent.click(file);
    expect(
      screen.getByText("Exact reviewed source wording."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Idioma de la explicación")).toHaveValue(
      "en-US",
    );
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
    expect(post).not.toHaveBeenCalled();
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
        "No pudimos cargar sus documentos. Inténtelo de nuevo.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Intentar de nuevo" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/internal_schema/)).not.toBeInTheDocument();
  });
});
