# Document-format and viewer policy

## Purpose

This policy defines the only file formats accepted by the generic clinical-document
upload workflow. It prevents a browser viewer or an extraction model from becoming an
implicit, unsafe parser for arbitrary files.

The original source remains private evidence. Rendering, OCR, and model extraction
are distinct steps, and none creates clinical truth without the existing clinician
review path.

## Generic clinical-document intake

| Source type | Accept | Patient and clinician view | Processing |
| --- | --- | --- | --- |
| PDF | Yes | PDF.js read-only source viewer | Embedded-text extraction, then OCR only where needed |
| JPEG, PNG, WebP | Yes | Read-only native image viewer | OCR |
| TIFF, including multi-frame TIFF | Yes | Generated read-only PDF preview; original retained | OCR across source frames |
| Password-protected or corrupt PDF | Store only when the file is otherwise valid; no automatic extraction | Original-download fallback and clear review state | No model call until an authorized, readable source exists |
| FHIR JSON/NDJSON | No | Dedicated interoperability review surface | Profile-aware FHIR import, not document OCR |
| CDA/C-CDA XML | No | Dedicated structured-document review surface | Schema/profile validation and sanitized narrative rendering, not document OCR |
| DICOM | No | Dedicated DICOMweb imaging surface | Imaging workflow, not document ingestion |
| Office, HTML, SVG, archives, email, executables, HEIC, CSV, and arbitrary text | No | None | Rejected before metadata registration |

`PDF`, `JPEG`, `PNG`, `WebP`, and `TIFF` are the contract. Storage policy, API
validation, both upload clients, worker routing, and viewer coverage must stay in
lockstep. A client-provided MIME type is never sufficient evidence of file type.

## Viewer architecture

- The portals use the Mozilla PDF.js distribution for PDFs. It renders source pages
  locally from a short-lived, role-authorized URL; documents are not sent to a viewer
  SaaS.
- Browser-safe raster images render natively. TIFF gets a server-generated preview
  because browser support is not dependable; the source TIFF is retained separately.
- The clinician viewer is the review surface for page, quote, and bounding-box evidence.
  The patient viewer is read-only and pairs the source with a separately generated,
  plain-language explanation.
- Signed URLs are requested only when a user opens a source. A stale URL must produce a
  safe retry/download state, never an unauthenticated fallback.

## Safety and operations

1. The upload clients and metadata API currently validate the declared type, filename extension,
   and size. The worker verifies the signature/container before any renderer, OCR engine, or
   model reads the bytes and records a safe terminal state on a mismatch. A pre-storage
   malware/signature gateway is still required before broad production rollout; a successful
   browser upload is not a safety verdict.
2. Keep uploaded objects private, scope every read to the owning patient or an assigned
   clinician, and retain immutable source/hash/provenance.
3. Scan uploaded source files before broad production rollout; never treat a successful
   browser upload as a safety verdict.
4. Limit preview generation to the documented resource budget. Failure to generate a
   preview is a reviewable operational state, not permission to serve an arbitrary original
   inline.
5. Exercise the synthetic corpus against valid PDFs, scans, multi-frame TIFF, malformed and
   encrypted PDFs, signed-URL expiry, and authorization denial in both portals.

This policy does not claim support for arbitrary healthcare files. FHIR/CDA/DICOM are
valuable clinical data types, but their validation, provenance, and review models are
different enough to require dedicated work before they are enabled.
