import type { Locale } from "@/types";

// Only interface copy is localized; source documents and clinical wording are preserved.
const spanish: Record<string, string> = {
  "My Records": "Mis documentos",
  "View clinical records and plain-language explanations.":
    "Consulta tus documentos y explicaciones en lenguaje sencillo.",
  Upload: "Subir documento",
  Stored: "Guardados",
  "Secure records": "Documentos guardados",
  Parsing: "En proceso",
  "AI Ready": "Explicaciones",
  "Documents in progress": "Documentos en proceso",
  "Summaries available": "Explicaciones disponibles",
  "Could not load records": "No se pudieron cargar los documentos",
  "Action failed": "No se pudo completar la acción",
  "Document processing failed": "No se pudo procesar el documento",
  "Loading documents...": "Cargando documentos...",
  "Upload PDFs or images from your clinic visits.":
    "Sube archivos PDF o imágenes de tus consultas.",
  "No records yet": "Aún no hay documentos",
  "Record details": "Detalles del documento",
  Document: "Documento",
  Source: "Origen",
  "Explain this to me": "Explicación en lenguaje sencillo",
  "Read summary aloud": "Escuchar explicación",
  "Explanation language": "Idioma de la explicación",
  "Translating...": "Preparando explicación...",
  "A plain-language explanation will appear here once it is ready.":
    "La explicación aparecerá aquí cuando esté lista.",
  "Ask about this document": "Preguntar sobre este documento",
  Close: "Cerrar",
  "Upload another": "Subir otro documento",
  "Could not delete document": "No se pudo eliminar el documento",
  "Delete this document?": "¿Eliminar este documento?",
  "This removes the record from your documents. Existing care-plan items created from prior parsing are not removed.":
    "Esto elimina el archivo de tus documentos. Las instrucciones del plan de atención que ya se crearon a partir de este archivo se conservan.",
  Cancel: "Cancelar",
  Deleting: "Eliminando",
  "Delete permanently": "Eliminar permanentemente",
  "Delete document": "Eliminar documento",
  "Duplicate upload": "Archivo duplicado",
  "Processing...": "En proceso...",
  "Needs care-team review": "Necesita revisión del equipo de atención",
  "Parse failed": "No se pudo procesar",
  "AI Summary": "Explicación con IA",
  "Explanation unavailable": "Explicación no disponible",
  "Translation is currently unavailable. Please try again later.":
    "La explicación en este idioma no está disponible por ahora. Inténtalo más tarde.",
  "We are preparing this document. Its explanation will appear when ready.":
    "Estamos procesando este documento. La explicación aparecerá cuando esté lista.",
  "This document could not be processed.":
    "No se pudo procesar este documento.",
  "We tried several times and could not process this document. Someone on your care team can review it.":
    "No pudimos procesar este documento después de varios intentos. Tu equipo de atención puede revisarlo.",
  "We could not match what we found back to the document, so nothing was saved. Someone on your care team can review it.":
    "No pudimos verificar la información con el documento, por lo que no se guardaron datos nuevos. Tu equipo de atención puede revisarlo.",
  "We could not read the details from this document. Someone on your care team can review it.":
    "No pudimos leer los detalles de este documento. Tu equipo de atención puede revisarlo.",
  "We could not read this scan reliably, so nothing was saved. Someone on your care team can review it.":
    "No pudimos leer esta imagen con suficiente claridad, por lo que no se guardaron datos nuevos. Tu equipo de atención puede revisarla.",
  "The document service was briefly unavailable. Please try again in a moment.":
    "El servicio de documentos no estaba disponible. Inténtalo de nuevo en un momento.",
  "This file could not be opened. It may be damaged, or password protected.":
    "No se pudo abrir este archivo. Puede estar dañado o protegido con contraseña.",
  "A plain-language explanation is not available for this document right now. Your document and your records are unchanged, and your care team can request it again.":
    "La explicación de este documento no está disponible por ahora. Tu documento y tus registros se conservan. Tu equipo de atención puede solicitarla de nuevo.",
  "There is no extracted information in this document to explain. You can still open the original document above or ask your care team about it.":
    "No hay información extraída de este documento para explicar. Puedes abrir el original o consultar a tu equipo de atención.",
  "The plain-language explanation is still being prepared. You can read the original document above and check back shortly.":
    "La explicación aún se está preparando. Puedes leer el documento original y volver más tarde.",
  "Choose a PDF, JPG, PNG, WebP, or TIFF file up to 20 MB.":
    "Elige un archivo PDF, JPG, PNG, WebP o TIFF de hasta 20 MB.",
  "Each file must be 20 MB or smaller.":
    "Cada archivo debe ser de 20 MB o menos.",
  "Please sign in again before uploading a document.":
    "Inicia sesión de nuevo antes de subir un documento.",
  "Your session expired. Please sign in again before uploading.":
    "Tu sesión venció. Inicia sesión de nuevo antes de subir un documento.",
  "Please sign in again before deleting this document.":
    "Inicia sesión de nuevo antes de eliminar este documento.",
  "We could not load your documents. Please try again.":
    "No pudimos cargar tus documentos. Inténtalo de nuevo.",
  "Upload failed. Please refresh your records before trying again.":
    "No pudimos confirmar que se subió el documento. Actualiza tus documentos antes de intentarlo de nuevo.",
  "Delete failed. Please refresh your records before trying again.":
    "No pudimos confirmar que se eliminó el documento. Actualiza tus documentos antes de intentarlo de nuevo.",
  "Try again": "Intentar de nuevo",
  "Refresh records": "Actualizar documentos",
  "Refreshing...": "Actualizando...",
  "Care team": "Equipo de atención",
  "Patient uploaded document": "Documento que subiste",
  "Lab report": "Resultados de laboratorio",
  Prescription: "Receta",
  "Discharge summary": "Resumen de alta",
  "Diagnostic report": "Informe de diagnóstico",
  "Other document": "Otro documento",
  "Source document": "Documento original",
  "Original uploaded file": "Archivo original",
  "Preview generated from the original TIFF":
    "Vista previa del archivo TIFF original",
  "Download original": "Descargar original",
  "Loading source document…": "Cargando documento original…",
  Previous: "Anterior",
  Next: "Siguiente",
  "This PDF could not be displayed in the browser. You can still download the original.":
    "No se pudo mostrar este PDF. Puedes descargar el original.",
  "This page could not be rendered. You can still download the original.":
    "No se pudo mostrar esta página. Puedes descargar el original.",
  "A browser preview is being prepared for this TIFF. The original is available to download now.":
    "Se está preparando una vista previa de este TIFF. Ya puedes descargar el original.",
  "A browser preview could not be prepared. Download the original or ask your care team for help reviewing it.":
    "No se pudo preparar una vista previa. Descarga el original o pide ayuda a tu equipo de atención para revisarlo.",
  "This source is temporarily unavailable. Please refresh and try again.":
    "Este documento no está disponible por ahora. Actualiza e inténtalo de nuevo.",
  // Test results read from one document. Values, names and ranges stay as printed.
  "Test results": "Resultados",
  Measurements: "Mediciones",
  "Other results": "Otros resultados",
  Range: "Rango",
  Page: "Página",
  "Result status": "Estado del resultado",
  High: "Alto",
  Low: "Bajo",
  "Outside range": "Fuera de rango",
  Critical: "Crítico",
  "Flag as printed": "Indicador impreso",
  "Contact your care team today.": "Comunícate hoy con tu equipo de atención.",
  "Not yet reviewed by your care team": "Aún no revisado por tu equipo de atención",
  "Loading test results…": "Cargando resultados…",
  "Could not load test results": "No se pudieron cargar los resultados",
  "We could not load the results from this document. Please try again.":
    "No pudimos cargar los resultados de este documento. Intenta de nuevo.",
  "These results were read automatically from this document. Any not yet reviewed by your care team are marked.":
    "Estos resultados se leyeron automáticamente de este documento. Los que tu equipo de atención aún no revisa están marcados.",
  "Your care team will review your results with you.":
    "Tu equipo de atención revisará tus resultados contigo.",
};

export function recordsCopy(locale: Locale, text: string): string {
  return locale === "es-MX" ? (spanish[text] ?? text) : text;
}
