import { Icon } from "@/components/ui/icons";

function fileKind(name?: string | null) {
    const extension = name?.split(".").pop()?.toLowerCase() ?? "";
    if (extension === "pdf") return { label: "PDF", tone: "bg-risk-tint text-risk-ink" };
    if (["png", "jpg", "jpeg", "webp", "tif", "tiff", "heic"].includes(extension)) return { label: "IMG", tone: "bg-ok-tint text-ok-ink" };
    if (["txt", "doc", "docx", "rtf"].includes(extension)) return { label: "DOC", tone: "bg-primary-tint text-primary" };
    return null;
}

/** Small file-type tile that marks a reference as a source document. */
export function SourceFileIcon({ name, className = "" }: { name?: string | null; className?: string }) {
    const kind = fileKind(name);
    if (!kind) return <Icon name="file" className={`h-3.5 w-3.5 shrink-0 text-muted ${className}`} />;
    return <span aria-hidden="true" className={`inline-flex h-[18px] shrink-0 items-center rounded-[5px] px-1 font-mono text-[9px] font-semibold leading-none tracking-[0.04em] ${kind.tone} ${className}`}>{kind.label}</span>;
}
