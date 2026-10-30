import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RecordRequestComposer } from "@/components/features/record-request-composer";
import type { ConversationDraft } from "@/types/care-conversations";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/services/api", () => ({ api: { get } }));
const document = {
  id: "record-a",
  patient_id: "patient",
  file_name: "source.pdf",
  display_title: { "en-US": "Prescription", "es-MX": "Receta" },
};
const onDraft = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue(document);
});
const props = {
  documentId: "record-a",
  patientId: "patient",
  locale: "en-US" as const,
  token: "synthetic-token",
  draft: { body: "" },
  disabled: false,
  onDraft,
};

describe("record review request preparation", () => {
  it("rechecks owned metadata and prepares a draft only after an explicit action", async () => {
    render(<RecordRequestComposer {...props} />);
    const button = await screen.findByRole("button", {
      name: "Prepare request",
    });
    expect(onDraft).not.toHaveBeenCalled();
    fireEvent.click(button);
    expect(onDraft).toHaveBeenCalledWith({
      body: expect.stringContaining(
        "Document: Prescription\nOriginal file: source.pdf\n\nMy request: ",
      ),
    });
    // The patient's message names the record in words, not by its database id.
    expect(onDraft.mock.calls[0][0].body).not.toContain("record-a");
    expect(get).toHaveBeenCalledWith(
      "/api/v1/documents/record-a",
      expect.objectContaining({ token: "synthetic-token" }),
    );
  });

  it.each([
    { body: "Unrelated draft" },
    { body: "", clientMessageId: "uncertain-send" },
    { body: "", carePlanItemId: "activity" },
  ] as ConversationDraft[])(
    "preserves existing or uncertain drafts: %j",
    async (draft) => {
      render(<RecordRequestComposer {...props} draft={draft} />);
      expect(
        await screen.findByRole("button", { name: "Prepare request" }),
      ).toBeDisabled();
      expect(onDraft).not.toHaveBeenCalled();
    },
  );

  it.each([
    null,
    { ...document, patient_id: "foreign" },
    { ...document, id: "foreign" },
  ])("does not prepare missing or foreign content: %j", async (source) => {
    get.mockResolvedValue(source);
    render(<RecordRequestComposer {...props} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No request was prepared",
    );
    expect(
      screen.queryByRole("button", { name: "Prepare request" }),
    ).not.toBeInTheDocument();
    expect(onDraft).not.toHaveBeenCalled();
  });

  it("rejects an old source response after token/context changes", async () => {
    let done!: (value: unknown) => void;
    get
      .mockReturnValueOnce(
        new Promise((resolve) => {
          done = resolve;
        }),
      )
      .mockResolvedValueOnce({ ...document, id: "record-b" });
    const { rerender } = render(<RecordRequestComposer {...props} />);
    rerender(
      <RecordRequestComposer
        {...props}
        documentId="record-b"
        token="replacement"
      />,
    );
    await screen.findByRole("button", { name: "Prepare request" });
    await act(async () =>
      done({ ...document, display_title: { "en-US": "Wrong source" } }),
    );
    expect(screen.queryByText("Wrong source")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Prepare request" }));
    expect(onDraft).toHaveBeenCalledWith({
      body: expect.stringContaining("Document: Prescription"),
    });
    expect(onDraft.mock.calls[0][0].body).not.toContain("Wrong source");
  });

  it("prepares Spanish wording while preserving original source identity", async () => {
    render(<RecordRequestComposer {...props} locale="es-MX" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Preparar solicitud" }),
    );
    expect(onDraft).toHaveBeenCalledWith({
      body: expect.stringContaining(
        "Documento: Receta\nArchivo original: source.pdf",
      ),
    });
  });
});
