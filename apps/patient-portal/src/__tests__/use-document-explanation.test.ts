import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useDocumentExplanation } from "@/hooks/use-document-explanation";
import { readDocumentExplanation } from "@/services/documents";
import type { Locale } from "@/types";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("@/services/api", () => ({ api: { post } }));

const props: Parameters<typeof useDocumentExplanation>[0] = {
  documentId: "source-a",
  source: "Legacy Spanish summary.",
  locale: "en-US",
  token: "synthetic-token",
  actorId: "synthetic-patient",
};
function response(locale: Locale, text: string) {
  return {
    available: true,
    language: locale,
    summary: text,
    sections: [{ kind: "medicines", items: [text] }],
  };
}
function deferred() {
  let resolve!: (value: unknown) => void;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("document explanation ownership", () => {
  beforeEach(() => {
    post.mockReset();
  });

  it("requests English for a legacy source without displaying it as English", async () => {
    const pending = deferred();
    post.mockReturnValue(pending.promise);
    const { result } = renderHook(() => useDocumentExplanation(props));
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(post).toHaveBeenCalledWith(
      "/api/v1/documents/source-a/explain",
      { language: "en-US", structured: true },
      expect.objectContaining({
        token: props.token,
        signal: expect.any(AbortSignal),
      }),
    );
    await act(async () =>
      pending.resolve(response("en-US", "The document says 500 mg.")),
    );
    expect(result.current.data?.summary).toBe("The document says 500 mg.");
  });

  it.each(["locale", "document", "account", "token", "close"])(
    "rejects a delayed response after a %s change",
    async (change) => {
      const old = deferred();
      const current = deferred();
      post
        .mockReturnValueOnce(old.promise)
        .mockReturnValueOnce(current.promise);
      const { result, rerender } = renderHook(
        (value) => useDocumentExplanation(value),
        { initialProps: props },
      );
      const oldSignal = post.mock.calls[0][2].signal as AbortSignal;
      const next = {
        ...props,
        ...(change === "locale" ? { locale: "es-MX" as Locale } : {}),
        ...(change === "document" ? { documentId: "source-b" } : {}),
        ...(change === "account" ? { actorId: "another-patient" } : {}),
        ...(change === "token" ? { token: "replacement-token" } : {}),
        ...(change === "close" ? { documentId: null } : {}),
      };
      rerender(next);
      expect(result.current.data).toBeNull();
      expect(oldSignal.aborted).toBe(true);
      await act(async () => old.resolve(response("en-US", "Old content")));
      expect(result.current.data).toBeNull();
      if (change !== "close") {
        await act(async () =>
          current.resolve(response(next.locale, "Current content")),
        );
        expect(result.current.data?.summary).toBe("Current content");
      }
    },
  );

  it("hides a previously ready explanation immediately when locale changes", async () => {
    post
      .mockResolvedValueOnce(response("en-US", "English content"))
      .mockReturnValue(new Promise(() => {}));
    const { result, rerender } = renderHook(
      (value) => useDocumentExplanation(value),
      { initialProps: props },
    );
    await waitFor(() =>
      expect(result.current.data?.summary).toBe("English content"),
    );
    rerender({ ...props, locale: "es-MX" });
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(true);
  });

  it("refuses wrong-locale output and supports an explicit retry", async () => {
    post
      .mockResolvedValueOnce(
        response("es-MX", "Texto incorrecto para esta selección"),
      )
      .mockResolvedValueOnce(response("en-US", "Correct content"));
    const { result } = renderHook(() => useDocumentExplanation(props));
    await waitFor(() => expect(result.current.failed).toBe(true));
    expect(result.current.data).toBeNull();
    act(() => result.current.retry());
    expect(result.current.data).toBeNull();
    await waitFor(() =>
      expect(result.current.data?.summary).toBe("Correct content"),
    );
  });

  it("reports a network failure without making source content available", async () => {
    post.mockRejectedValue(new Error("internal detail"));
    const { result } = renderHook(() => useDocumentExplanation(props));
    await waitFor(() => expect(result.current.failed).toBe(true));
    expect(result.current.data).toBeNull();
  });

  it.each([
    { token: null },
    { actorId: undefined },
    { documentId: null },
    { source: undefined },
  ])(
    "does not request unavailable or unauthenticated content: %j",
    (override) => {
      const { result } = renderHook(() =>
        useDocumentExplanation({ ...props, ...override }),
      );
      expect(result.current.loading).toBe(false);
      expect(result.current.data).toBeNull();
      expect(post).not.toHaveBeenCalled();
    },
  );
});

describe("explanation response validation", () => {
  it.each([
    null,
    { summary: "Old unstructured response" },
    { ...response("en-US", "Visible"), summary: "Different speech" },
    {
      ...response("en-US", "Visible"),
      sections: [{ kind: "approved", items: ["Visible"] }],
    },
    {
      ...response("en-US", "Visible"),
      sections: [{ kind: "medicines", items: [""] }],
    },
    {
      ...response("en-US", "Visible"),
      sections: response("en-US", "Visible").sections.concat(
        response("en-US", "Visible").sections,
      ),
    },
  ])("refuses malformed or inconsistent content: %j", (value) => {
    expect(readDocumentExplanation(value, "en-US")).toBeNull();
  });
});
