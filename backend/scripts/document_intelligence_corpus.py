"""Build the synthetic document corpus used to benchmark and regression-test extraction.

Every page is generated from fictional, clearly labelled synthetic content. Nothing
here is derived from a real record. The corpus covers born-digital PDFs, simulated
scans and faxes, prescription images, tables, two-column pages, Spanish documents,
difficult dosages and dates, blank pages, and deliberately unreadable files, each
with page-level ground truth so accuracy and citations can be measured.

    python backend/scripts/document_intelligence_corpus.py --out-dir /tmp/corpus

Files are written with a manifest; nothing is uploaded or persisted elsewhere.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import random
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0
FONT = "helv"
DEFAULT_SEED = 20260909
SCRIPT_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
    "/System/Library/Fonts/Supplemental/Apple Chancery.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
)

BORN_DIGITAL = "born_digital_text"
SCANNED = "scanned_image"
MIXED = "mixed"
BLANK = "blank"
UNREADABLE = "unreadable"
ENCRYPTED = "encrypted"
UNSUPPORTED = "unsupported"

AUTOMATED = "automated_candidates"
CAUTION = "review_with_caution"
CLINICIAN_ONLY = "clinician_only"
REJECTED = "rejected"


@dataclass(frozen=True)
class GroundTruthField:
    fact_type: str
    field: str
    value: str
    page: int


@dataclass(frozen=True)
class GroundTruthCell:
    page: int
    row: int
    col: int
    text: str


@dataclass(frozen=True)
class CorpusCase:
    case_id: str
    category: str
    language: str
    mime_type: str
    file_name: str
    expected_document_class: str
    acceptable_routes: tuple[str, ...]
    expected_page_classes: tuple[str, ...]
    page_texts: tuple[str, ...]
    fields: tuple[GroundTruthField, ...] = ()
    cells: tuple[GroundTruthCell, ...] = ()
    notes: str = ""
    acceptable_document_classes: tuple[str, ...] = ()

    def accepts_document_class(self, document_class: str) -> bool:
        return document_class in (self.expected_document_class, *self.acceptable_document_classes)


@dataclass(frozen=True)
class BuiltCase:
    case: CorpusCase
    path: Path
    sha256: str
    build_notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": asdict(self.case),
            "path": str(self.path),
            "sha256": self.sha256,
            "build_notes": list(self.build_notes),
        }


# ── Synthetic content ─────────────────────────────────────────────────────────

DISCHARGE_EN_P1 = (
    "SYNTHETIC RECORD - NOT A REAL PATIENT",
    "DISCHARGE SUMMARY",
    "Patient: Rosa Delgado (synthetic)    DOB: 04/12/1957    MRN: SYN-104477",
    "Admission: 08/28/2026    Discharge: 09/02/2026",
    "Attending: Dr. Elena Marsh, MD - Cardiology",
    "Facility: Sierra Vista Community Hospital (fictional)",
    "",
    "DISCHARGE DIAGNOSES",
    "1. Heart failure with reduced ejection fraction, EF 35%",
    "2. Type 2 diabetes mellitus",
    "3. Hypertension",
    "4. Chronic kidney disease stage 3a",
    "",
    "ALLERGIES",
    "Penicillin - hives (severe)",
    "Sulfamethoxazole - rash (moderate)",
)
DISCHARGE_EN_P2 = (
    "DISCHARGE MEDICATIONS",
    "1. Metoprolol succinate 50 mg - take 1 tablet by mouth twice daily",
    "2. Lisinopril 10 mg - take 1 tablet by mouth once daily",
    "3. Furosemide 40 mg - take 1 tablet by mouth every morning",
    "4. Metformin 500 mg - take 1 tablet by mouth twice daily with meals",
    "5. Atorvastatin 40 mg - take 1 tablet by mouth at bedtime",
    "",
    "FOLLOW-UP INSTRUCTIONS",
    "Cardiology clinic visit in 2 weeks",
    "Weigh yourself every morning; call if weight increases more than 3 lb in 2 days",
    "Limit sodium to less than 2,000 mg per day",
    "Electronically signed: Dr. Elena Marsh, MD - 09/02/2026 14:32",
)
DISCHARGE_EN_FIELDS = (
    GroundTruthField("condition", "name", "Heart failure with reduced ejection fraction", 1),
    GroundTruthField("condition", "name", "Type 2 diabetes mellitus", 1),
    GroundTruthField("condition", "name", "Hypertension", 1),
    GroundTruthField("condition", "name", "Chronic kidney disease stage 3a", 1),
    GroundTruthField("allergy", "allergen", "Penicillin", 1),
    GroundTruthField("allergy", "reaction", "hives", 1),
    GroundTruthField("allergy", "allergen", "Sulfamethoxazole", 1),
    GroundTruthField("date", "discharge_date", "09/02/2026", 1),
    GroundTruthField("medication", "name", "Metoprolol succinate", 2),
    GroundTruthField("medication", "dosage", "50 mg", 2),
    GroundTruthField("medication", "frequency", "twice daily", 2),
    GroundTruthField("medication", "name", "Lisinopril", 2),
    GroundTruthField("medication", "dosage", "10 mg", 2),
    GroundTruthField("medication", "name", "Furosemide", 2),
    GroundTruthField("medication", "frequency", "every morning", 2),
    GroundTruthField("medication", "name", "Metformin", 2),
    GroundTruthField("medication", "dosage", "500 mg", 2),
    GroundTruthField("medication", "name", "Atorvastatin", 2),
    GroundTruthField("medication", "frequency", "at bedtime", 2),
    GroundTruthField("obligation", "description", "Cardiology clinic visit in 2 weeks", 2),
    GroundTruthField("obligation", "description", "Limit sodium to less than 2,000 mg per day", 2),
)

RX_EN = (
    "SYNTHETIC - NOT A REAL PATIENT",
    "PRESCRIPTION",
    "Prescriber: Dr. Samuel Okafor, MD - Endocrinology (fictional)",
    "Patient: Denise Whitfield (synthetic)    DOB: 11/03/1985",
    "Date: 09/01/2026",
    "",
    "Rx 1: Semaglutide 0.5 mg/dose - inject 0.5 mg subcutaneously once weekly",
    "Rx 2: Metformin ER 1000 mg - take 1 tablet by mouth once daily with evening meal",
    "Rx 3: Empagliflozin 10 mg - take 1 tablet by mouth once daily in the morning",
    "Rx 4: Insulin glargine 100 units/mL - inject 20 units subcutaneously at bedtime",
    "Refills: 2",
    "Follow-up in 6 weeks to review blood sugar log",
)
RX_EN_FIELDS = (
    GroundTruthField("medication", "name", "Semaglutide", 1),
    GroundTruthField("medication", "dosage", "0.5 mg", 1),
    GroundTruthField("medication", "frequency", "once weekly", 1),
    GroundTruthField("medication", "name", "Metformin ER", 1),
    GroundTruthField("medication", "dosage", "1000 mg", 1),
    GroundTruthField("medication", "name", "Empagliflozin", 1),
    GroundTruthField("medication", "dosage", "10 mg", 1),
    GroundTruthField("medication", "name", "Insulin glargine", 1),
    GroundTruthField("medication", "dosage", "20 units", 1),
    GroundTruthField("medication", "frequency", "at bedtime", 1),
    GroundTruthField("date", "prescription_date", "09/01/2026", 1),
    GroundTruthField(
        "obligation", "description", "Follow-up in 6 weeks to review blood sugar log", 1
    ),
)

RX_ES = (
    "REGISTRO SINTÉTICO - NO ES UN PACIENTE REAL",
    "RECETA MÉDICA",
    "Paciente: Joaquín Ríos Herrera (sintético)    Fecha de nacimiento: 23/07/1961",
    "Fecha: 12 de marzo de 2026    Folio: RX-SYN-2291",
    "Médico: Dra. Lucía Fernández Ortega - Cédula profesional 0000000 (ficticia)",
    "Clínica Familiar del Valle (ficticia), Guadalajara, Jalisco",
    "",
    "1. Metformina 850 mg - tomar 1 tableta vía oral cada 12 horas con alimentos",
    "2. Losartán 50 mg - tomar 1 tableta vía oral cada 24 horas por la mañana",
    "3. Atorvastatina 20 mg - tomar 1 tableta vía oral por la noche",
    "4. Insulina glargina 100 UI/mL - aplicar 18 unidades vía subcutánea a las 22:00 h",
    "5. Levotiroxina 0,1 mg (100 mcg) - 1 tableta VO en ayunas c/24 h",
    "",
    "Alergias: Penicilina (urticaria)",
    "Indicaciones: medir glucosa capilar en ayunas; próxima cita el 26/03/2026",
)
RX_ES_FIELDS = (
    GroundTruthField("medication", "name", "Metformina", 1),
    GroundTruthField("medication", "dosage", "850 mg", 1),
    GroundTruthField("medication", "frequency", "cada 12 horas", 1),
    GroundTruthField("medication", "name", "Losartán", 1),
    GroundTruthField("medication", "dosage", "50 mg", 1),
    GroundTruthField("medication", "frequency", "cada 24 horas", 1),
    GroundTruthField("medication", "name", "Atorvastatina", 1),
    GroundTruthField("medication", "frequency", "por la noche", 1),
    GroundTruthField("medication", "name", "Insulina glargina", 1),
    GroundTruthField("medication", "dosage", "18 unidades", 1),
    GroundTruthField("medication", "name", "Levotiroxina", 1),
    GroundTruthField("medication", "dosage", "0,1 mg", 1),
    GroundTruthField("medication", "frequency", "c/24 h", 1),
    GroundTruthField("allergy", "allergen", "Penicilina", 1),
    GroundTruthField("allergy", "reaction", "urticaria", 1),
    GroundTruthField("date", "prescription_date", "12 de marzo de 2026", 1),
    GroundTruthField("date", "follow_up_date", "26/03/2026", 1),
)

LAB_TABLE_HEADER = (
    "SYNTHETIC - NOT A REAL PATIENT",
    "LABORATORY REPORT",
    "Patient: Rosa Delgado (synthetic)    Collected: 08/29/2026 07:15",
)
LAB_TABLE_COLUMNS = ("Test", "Result", "Units", "Reference", "Flag")
LAB_TABLE_ROWS = (
    ("Glucose", "187", "mg/dL", "70-100", "H"),
    ("HbA1c", "8.2", "%", "<5.7", "H"),
    ("Creatinine", "1.4", "mg/dL", "0.7-1.3", "H"),
    ("eGFR", "55", "mL/min/1.73m2", ">60", "L"),
    ("Potassium", "4.8", "mEq/L", "3.5-5.0", ""),
    ("LDL cholesterol", "158", "mg/dL", "<100", "H"),
)
LAB_TABLE_FOOTER = ("Reported by: Sierra Vista Laboratory (fictional)",)
LAB_TABLE_FIELDS = (
    GroundTruthField("lab", "analyte", "Glucose", 1),
    GroundTruthField("lab", "analyte", "HbA1c", 1),
    GroundTruthField("lab", "analyte", "Creatinine", 1),
    GroundTruthField("lab", "analyte", "LDL cholesterol", 1),
    GroundTruthField("lab", "unit", "mEq/L", 1),
    GroundTruthField("date", "collected", "08/29/2026", 1),
)

LAB_ES = (
    "REGISTRO SINTÉTICO - NO ES UN PACIENTE REAL",
    "REPORTE DE LABORATORIO",
    "Paciente: Joaquín Ríos Herrera (sintético)    Fecha: 05/09/2026",
    "Glucosa en ayunas: 165 mg/dL (referencia 70-100) ALTO",
    "Hemoglobina glucosilada (HbA1c): 7,9 % (referencia <5,7) ALTO",
    "Creatinina: 1,2 mg/dL (referencia 0,7-1,3)",
    "Potasio: 4,6 mEq/L (referencia 3,5-5,0)",
    "Colesterol LDL: 142 mg/dL (referencia <100) ALTO",
    "Laboratorio Clínico del Valle (ficticio)",
)
LAB_ES_FIELDS = (
    GroundTruthField("lab", "analyte", "Glucosa en ayunas", 1),
    GroundTruthField("lab", "value", "165 mg/dL", 1),
    GroundTruthField("lab", "analyte", "HbA1c", 1),
    GroundTruthField("lab", "value", "7,9 %", 1),
    GroundTruthField("lab", "analyte", "Creatinina", 1),
    GroundTruthField("lab", "value", "1,2 mg/dL", 1),
    GroundTruthField("date", "collected", "05/09/2026", 1),
)

MULTICOL_HEADER = ("SYNTHETIC - NOT A REAL PATIENT", "VISIT SUMMARY - 09/04/2026")
MULTICOL_LEFT = (
    "CURRENT MEDICATIONS",
    "Amlodipine 5 mg by mouth once daily",
    "Metformin 500 mg by mouth twice daily",
    "Atorvastatin 20 mg by mouth at bedtime",
    "Aspirin 81 mg by mouth once daily",
)
MULTICOL_RIGHT = (
    "PLAN",
    "Recheck blood pressure in 4 weeks",
    "Repeat HbA1c in 3 months",
    "Continue low-sodium diet",
    "Return sooner for chest pain",
)
MULTICOL_FOOTER = ("Signed: Dr. Elena Marsh, MD (fictional)",)
MULTICOL_FIELDS = (
    GroundTruthField("medication", "name", "Amlodipine", 1),
    GroundTruthField("medication", "dosage", "5 mg", 1),
    GroundTruthField("medication", "name", "Metformin", 1),
    GroundTruthField("medication", "frequency", "twice daily", 1),
    GroundTruthField("medication", "name", "Atorvastatin", 1),
    GroundTruthField("medication", "name", "Aspirin", 1),
    GroundTruthField("medication", "dosage", "81 mg", 1),
    GroundTruthField("obligation", "description", "Recheck blood pressure in 4 weeks", 1),
    GroundTruthField("obligation", "description", "Repeat HbA1c in 3 months", 1),
)

DOSAGES_EN = (
    "SYNTHETIC - NOT A REAL PATIENT",
    "MEDICATION LIST - DIFFICULT FORMATS",
    "Levothyroxine 0.075 mg (75 mcg) by mouth every morning",
    "Insulin glargine 20 units subcutaneously at bedtime",
    "Warfarin 2.5 mg by mouth daily except 5 mg on Monday and Friday",
    "Amoxicillin 875 mg by mouth twice daily for 10 days",
    "Nitroglycerin 0.4 mg sublingual as needed for chest pain",
    "Albuterol 90 mcg/puff, 2 puffs every 4 to 6 hours as needed",
    "Potassium chloride 20 mEq by mouth once daily",
    "Vitamin B12 1,000 mcg by mouth once daily",
    "Started: 2026-09-01    Reviewed: Sep 3, 2026    Next refill due: 01/10/2026",
)
DOSAGES_EN_FIELDS = (
    GroundTruthField("medication", "name", "Levothyroxine", 1),
    GroundTruthField("medication", "dosage", "0.075 mg", 1),
    GroundTruthField("medication", "frequency", "every morning", 1),
    GroundTruthField("medication", "name", "Insulin glargine", 1),
    GroundTruthField("medication", "dosage", "20 units", 1),
    GroundTruthField("medication", "name", "Warfarin", 1),
    GroundTruthField("medication", "dosage", "2.5 mg", 1),
    GroundTruthField("medication", "name", "Amoxicillin", 1),
    GroundTruthField("medication", "dosage", "875 mg", 1),
    GroundTruthField("medication", "frequency", "twice daily for 10 days", 1),
    GroundTruthField("medication", "name", "Nitroglycerin", 1),
    GroundTruthField("medication", "dosage", "0.4 mg", 1),
    GroundTruthField("medication", "name", "Albuterol", 1),
    GroundTruthField("medication", "dosage", "90 mcg/puff", 1),
    GroundTruthField("medication", "name", "Potassium chloride", 1),
    GroundTruthField("medication", "dosage", "20 mEq", 1),
    GroundTruthField("medication", "dosage", "1,000 mcg", 1),
    GroundTruthField("date", "started", "2026-09-01", 1),
    GroundTruthField("date", "reviewed", "Sep 3, 2026", 1),
    GroundTruthField("date", "refill_due", "01/10/2026", 1),
)

ABBREV_ES = (
    "REGISTRO SINTÉTICO - NO ES UN PACIENTE REAL",
    "INDICACIONES MÉDICAS",
    "Omeprazol 20 mg VO c/24 h en ayunas",
    "Paracetamol 500 mg VO c/8 h PRN dolor",
    "Salbutamol 100 mcg/inh, 2 disparos c/6 h PRN",
    "Enalapril 10 mg VO c/12 h",
    "Gotas oftálmicas: 1 gota en cada ojo c/8 h",
    "Fecha: 05/09/2026    Próxima cita: 19 sep 2026",
)
ABBREV_ES_FIELDS = (
    GroundTruthField("medication", "name", "Omeprazol", 1),
    GroundTruthField("medication", "dosage", "20 mg", 1),
    GroundTruthField("medication", "frequency", "c/24 h", 1),
    GroundTruthField("medication", "name", "Paracetamol", 1),
    GroundTruthField("medication", "frequency", "c/8 h PRN", 1),
    GroundTruthField("medication", "name", "Salbutamol", 1),
    GroundTruthField("medication", "dosage", "100 mcg/inh", 1),
    GroundTruthField("medication", "name", "Enalapril", 1),
    GroundTruthField("medication", "frequency", "c/12 h", 1),
    GroundTruthField("date", "visit", "05/09/2026", 1),
    GroundTruthField("date", "next_visit", "19 sep 2026", 1),
)

LABEL_EN = (
    "SYNTHETIC LABEL - NOT A REAL PRESCRIPTION",
    "VALLEY PHARMACY (fictional)   (555) 010-0199",
    "RX# 7731042      Filled: 09/03/2026",
    "WHITFIELD, DENISE (synthetic)",
    "METFORMIN HCL ER 500 MG TABLET",
    "TAKE 2 TABLETS BY MOUTH ONCE DAILY",
    "WITH EVENING MEAL",
    "QTY: 60    REFILLS: 3    Discard after: 09/03/2027",
    "Dr. S. Okafor (fictional)",
)
LABEL_EN_FIELDS = (
    GroundTruthField("medication", "name", "METFORMIN HCL ER", 1),
    GroundTruthField("medication", "dosage", "500 MG", 1),
    GroundTruthField("medication", "frequency", "ONCE DAILY", 1),
    GroundTruthField("medication", "quantity", "QTY: 60", 1),
    GroundTruthField("date", "filled", "09/03/2026", 1),
    GroundTruthField("date", "discard_after", "09/03/2027", 1),
)

LABEL_ES = (
    "ETIQUETA SINTÉTICA - NO ES UNA RECETA REAL",
    "FARMACIA DEL VALLE (ficticia)   Tel. 33 0000 0000",
    "Receta No. 55810      Fecha: 03/09/2026",
    "RÍOS HERRERA, JOAQUÍN (sintético)",
    "LOSARTÁN 50 MG TABLETA",
    "TOMAR 1 TABLETA VÍA ORAL CADA 24 HORAS",
    "POR LA MAÑANA",
    "CANT: 30    RESURTIDOS: 2    Caduca: 03/09/2027",
)
LABEL_ES_FIELDS = (
    GroundTruthField("medication", "name", "LOSARTÁN", 1),
    GroundTruthField("medication", "dosage", "50 MG", 1),
    GroundTruthField("medication", "frequency", "CADA 24 HORAS", 1),
    GroundTruthField("medication", "quantity", "CANT: 30", 1),
    GroundTruthField("date", "filled", "03/09/2026", 1),
)

MEDLIST_SHORT_EN = (
    "SYNTHETIC - NOT A REAL PATIENT",
    "MEDICATION LIST",
    "Amlodipine 5 mg by mouth once daily",
    "Metformin 500 mg by mouth twice daily",
    "Atorvastatin 20 mg by mouth at bedtime",
)
MEDLIST_SHORT_FIELDS = (
    GroundTruthField("medication", "name", "Amlodipine", 1),
    GroundTruthField("medication", "dosage", "5 mg", 1),
    GroundTruthField("medication", "name", "Metformin", 1),
    GroundTruthField("medication", "dosage", "500 mg", 1),
    GroundTruthField("medication", "name", "Atorvastatin", 1),
    GroundTruthField("medication", "frequency", "at bedtime", 1),
)

HANDWRITTEN = ("Metoprolol 25 mg BID", "Lisinopril 10 mg daily", "follow up 2 wks")
HANDWRITTEN_FIELDS = (
    GroundTruthField("medication", "name", "Metoprolol", 1),
    GroundTruthField("medication", "dosage", "25 mg", 1),
    GroundTruthField("medication", "name", "Lisinopril", 1),
)

MIXED_HEADER = (
    "SYNTHETIC - NOT A REAL PATIENT",
    "REFERRAL NOTE",
    "Patient: Rosa Delgado (synthetic)    Date: 09/05/2026",
    "Reason: medication reconciliation after hospital discharge",
)
MIXED_ATTACHMENT = (
    "ATTACHED MEDICATION LIST (SCANNED)",
    "Metoprolol succinate 50 mg twice daily",
    "Lisinopril 10 mg once daily",
    "Furosemide 40 mg every morning",
)
MIXED_FIELDS = (
    GroundTruthField("date", "visit", "09/05/2026", 1),
    GroundTruthField("medication", "name", "Metoprolol succinate", 1),
    GroundTruthField("medication", "dosage", "50 mg", 1),
    GroundTruthField("medication", "name", "Lisinopril", 1),
    GroundTruthField("medication", "name", "Furosemide", 1),
    GroundTruthField("medication", "frequency", "every morning", 1),
)

GARBAGE_TOKENS = "qzxwvk bkrtpl xvzqwn ptkrmz wqzxvb rtplkq zvkxwq mkptrz " * 6


# ── Rendering helpers ─────────────────────────────────────────────────────────


def _text(lines: Sequence[str]) -> str:
    return "\n".join(line for line in lines if line)


def _add_text_page(
    doc: Any,
    lines: Sequence[str],
    *,
    font_size: float = 10.5,
    left: float = 48,
    top: float = 64,
    line_height: float = 15,
) -> Any:
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = top
    for line in lines:
        if line:
            page.insert_text((left, y), line, fontsize=font_size, fontname=FONT)
        y += line_height
    return page


def _add_two_column_page(
    doc: Any,
    header: Sequence[str],
    left_lines: Sequence[str],
    right_lines: Sequence[str],
    footer: Sequence[str],
) -> Any:
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = 64.0
    for line in header:
        page.insert_text((48, y), line, fontsize=11, fontname=FONT)
        y += 16
    column_top = y + 12
    for x, lines in ((48.0, left_lines), (330.0, right_lines)):
        y = column_top
        for line in lines:
            page.insert_text((x, y), line, fontsize=10, fontname=FONT)
            y += 15
    footer_y = column_top + 15 * max(len(left_lines), len(right_lines)) + 30
    for line in footer:
        page.insert_text((48, footer_y), line, fontsize=10, fontname=FONT)
        footer_y += 15
    return page


def _add_table_page(
    doc: Any,
    header: Sequence[str],
    columns: Sequence[str],
    rows: Sequence[Sequence[str]],
    footer: Sequence[str],
) -> Any:
    import fitz

    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = 64.0
    for line in header:
        page.insert_text((48, y), line, fontsize=11, fontname=FONT)
        y += 16
    widths = (150.0, 70.0, 120.0, 100.0, 60.0)
    row_height = 20.0
    top = y + 12
    x0 = 48.0
    all_rows = [tuple(columns), *[tuple(row) for row in rows]]
    for row_index, row in enumerate(all_rows):
        row_top = top + row_index * row_height
        x = x0
        for width, text in zip(widths, row, strict=True):
            rect = fitz.Rect(x, row_top, x + width, row_top + row_height)
            page.draw_rect(rect, color=(0, 0, 0), width=0.7)
            if text:
                page.insert_text((x + 4, row_top + 14), text, fontsize=9.5, fontname=FONT)
            x += width
    footer_y = top + len(all_rows) * row_height + 30
    for line in footer:
        page.insert_text((48, footer_y), line, fontsize=10, fontname=FONT)
        footer_y += 15
    return page


def _pdf_bytes(doc: Any, **save_kwargs: Any) -> bytes:
    data = doc.tobytes(**save_kwargs)
    doc.close()
    return bytes(data)


def _text_pdf(*pages: Sequence[str]) -> bytes:
    import fitz

    doc = fitz.open()
    for lines in pages:
        _add_text_page(doc, lines)
    return _pdf_bytes(doc)


def _render_gray(pdf: bytes, page_index: int, dpi: int) -> Any:
    import fitz
    from PIL import Image

    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        pixmap = doc[page_index].get_pixmap(dpi=dpi)
        return Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("L")
    finally:
        doc.close()


def _png(image: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg(image: Any, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.convert("L").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _image_only_pdf(images: Sequence[Any]) -> bytes:
    """Wrap rasters in a PDF with no text layer, as a scanner or fax gateway would."""
    import fitz

    doc = fitz.open()
    for image in images:
        landscape = image.width > image.height
        width, height = (PAGE_HEIGHT, PAGE_WIDTH) if landscape else (PAGE_WIDTH, PAGE_HEIGHT)
        page = doc.new_page(width=width, height=height)
        page.insert_image(page.rect, stream=_png(image))
    return _pdf_bytes(doc)


def _table_cells(page: int) -> tuple[GroundTruthCell, ...]:
    cells: list[GroundTruthCell] = []
    all_rows = [LAB_TABLE_COLUMNS, *LAB_TABLE_ROWS]
    for row_index, row in enumerate(all_rows):
        for col_index, text in enumerate(row):
            cells.append(GroundTruthCell(page, row_index, col_index, text))
    return tuple(cells)


def _lab_table_text() -> str:
    lines = [*LAB_TABLE_HEADER]
    lines.append(" ".join(LAB_TABLE_COLUMNS))
    lines.extend(" ".join(cell for cell in row if cell) for row in LAB_TABLE_ROWS)
    lines.extend(LAB_TABLE_FOOTER)
    return "\n".join(lines)


# ── Degradations ──────────────────────────────────────────────────────────────


def _fax(image: Any, seed: int) -> Any:
    """Simulate a fax: 150 dpi, slight skew, hard threshold, speckle, and streaks."""
    import numpy as np
    from PIL import Image

    small = image.resize((image.width // 2, image.height // 2), Image.Resampling.BILINEAR)
    skewed = small.rotate(1.5, resample=Image.Resampling.BILINEAR, expand=True, fillcolor=255)
    array = np.asarray(skewed).copy()
    binary = np.where(array > 150, 255, 0).astype(np.uint8)
    rng = np.random.default_rng(seed)
    noise = rng.random(binary.shape)
    binary[noise < 0.004] = 0
    binary[noise > 0.998] = 255
    for row in rng.integers(0, binary.shape[0] - 3, size=3):
        binary[row : row + 2, :] = 0
    return Image.fromarray(binary)


def _low_resolution(image: Any) -> Any:
    """72 dpi with heavy JPEG loss, the way a cropped screenshot often arrives."""
    from PIL import Image

    scale = 72 / 300
    small = image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.Resampling.BILINEAR,
    )
    return Image.open(io.BytesIO(_jpeg(small, 35))).convert("L")


def _phone_photo(image: Any, seed: int) -> Any:
    """Skew, slight blur, and an uneven lighting gradient."""
    import numpy as np
    from PIL import Image, ImageFilter

    rotated = image.rotate(4, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=235)
    blurred = rotated.filter(ImageFilter.GaussianBlur(0.8))
    array = np.asarray(blurred).astype(np.float32)
    gradient = np.linspace(1.0, 0.72, array.shape[1], dtype=np.float32)
    shaded = np.clip(array * gradient[None, :], 0, 255).astype(np.uint8)
    rng = np.random.default_rng(seed)
    shaded = np.clip(shaded + rng.normal(0, 4, shaded.shape), 0, 255).astype(np.uint8)
    return Image.fromarray(shaded)


def _speckled_blank(size: tuple[int, int], seed: int, density: float) -> Any:
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed)
    array = np.full((size[1], size[0]), 255, dtype=np.uint8)
    array[rng.random(array.shape) < density] = 0
    return Image.fromarray(array)


def _handwriting(lines: Sequence[str], seed: int) -> tuple[Any, str]:
    """Render with a script font when one exists, then warp rows to imitate a pen."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.new("L", (1400, 700), 255)
    draw = ImageDraw.Draw(canvas)
    font_path = next((path for path in SCRIPT_FONT_CANDIDATES if Path(path).exists()), None)
    if font_path:
        font = ImageFont.truetype(font_path, 54)
        note = f"handwriting simulated with script font {Path(font_path).name}"
    else:
        font = ImageFont.load_default(size=48)
        note = "handwriting simulated with warp only; no script font installed"
    y = 90
    for line in lines:
        draw.text((110, y), line, fill=0, font=font)
        y += 150
    array = np.asarray(canvas).copy()
    rng = np.random.default_rng(seed)
    phase = rng.uniform(0, math.pi)
    for row in range(array.shape[0]):
        shift = int(9 * math.sin(row / 28 + phase))
        array[row] = np.roll(array[row], shift)
    return Image.fromarray(array).rotate(-2, expand=True, fillcolor=255), note


# ── Case builders ─────────────────────────────────────────────────────────────

Builder = Callable[[int], tuple[CorpusCase, bytes, tuple[str, ...]]]


def _discharge_pdf() -> bytes:
    return _text_pdf(DISCHARGE_EN_P1, DISCHARGE_EN_P2)


def build_born_digital_discharge_en(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    case = CorpusCase(
        case_id="born_digital_discharge_en",
        category="born_digital",
        language="en-US",
        mime_type="application/pdf",
        file_name="discharge-summary.pdf",
        expected_document_class=BORN_DIGITAL,
        acceptable_routes=(AUTOMATED,),
        expected_page_classes=(BORN_DIGITAL, BORN_DIGITAL),
        page_texts=(_text(DISCHARGE_EN_P1), _text(DISCHARGE_EN_P2)),
        fields=DISCHARGE_EN_FIELDS,
        notes="Two-page born-digital discharge summary with diagnoses, allergies, and medications.",
    )
    return case, _discharge_pdf(), ()


def build_born_digital_lab_table_en(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    import fitz

    doc = fitz.open()
    _add_table_page(doc, LAB_TABLE_HEADER, LAB_TABLE_COLUMNS, LAB_TABLE_ROWS, LAB_TABLE_FOOTER)
    case = CorpusCase(
        case_id="born_digital_lab_table_en",
        category="born_digital",
        language="en-US",
        mime_type="application/pdf",
        file_name="lab-report.pdf",
        expected_document_class=BORN_DIGITAL,
        acceptable_routes=(AUTOMATED,),
        expected_page_classes=(BORN_DIGITAL,),
        page_texts=(_lab_table_text(),),
        fields=LAB_TABLE_FIELDS,
        cells=_table_cells(1),
        notes="Ruled laboratory table; cell recovery is measured.",
    )
    return case, _pdf_bytes(doc), ()


def build_born_digital_two_column_en(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    import fitz

    doc = fitz.open()
    _add_two_column_page(doc, MULTICOL_HEADER, MULTICOL_LEFT, MULTICOL_RIGHT, MULTICOL_FOOTER)
    case = CorpusCase(
        case_id="born_digital_two_column_en",
        category="born_digital",
        language="en-US",
        mime_type="application/pdf",
        file_name="visit-summary.pdf",
        expected_document_class=BORN_DIGITAL,
        acceptable_routes=(AUTOMATED,),
        expected_page_classes=(BORN_DIGITAL,),
        page_texts=(_text([*MULTICOL_HEADER, *MULTICOL_LEFT, *MULTICOL_RIGHT, *MULTICOL_FOOTER]),),
        fields=MULTICOL_FIELDS,
        notes="Two-column layout; ground-truth text is left column then right column.",
    )
    return case, _pdf_bytes(doc), ()


def build_born_digital_prescription_es(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    case = CorpusCase(
        case_id="born_digital_prescription_es",
        category="born_digital",
        language="es-MX",
        mime_type="application/pdf",
        file_name="receta.pdf",
        expected_document_class=BORN_DIGITAL,
        acceptable_routes=(AUTOMATED,),
        expected_page_classes=(BORN_DIGITAL,),
        page_texts=(_text(RX_ES),),
        fields=RX_ES_FIELDS,
        notes="Spanish prescription with decimal commas, accents, and c/24 h abbreviations.",
    )
    return case, _text_pdf(RX_ES), ()


def build_born_digital_dosages_en(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    case = CorpusCase(
        case_id="born_digital_difficult_dosages_en",
        category="born_digital",
        language="en-US",
        mime_type="application/pdf",
        file_name="medication-list.pdf",
        expected_document_class=BORN_DIGITAL,
        acceptable_routes=(AUTOMATED,),
        expected_page_classes=(BORN_DIGITAL,),
        page_texts=(_text(DOSAGES_EN),),
        fields=DOSAGES_EN_FIELDS,
        notes="Fractional doses, units, PRN schedules, and three date formats.",
    )
    return case, _text_pdf(DOSAGES_EN), ()


def build_scanned_discharge_en(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    pdf = _discharge_pdf()
    images = [_render_gray(pdf, index, 300) for index in range(2)]
    case = CorpusCase(
        case_id="scanned_discharge_en_300dpi",
        category="scanned",
        language="en-US",
        mime_type="application/pdf",
        file_name="discharge-summary-scan.pdf",
        expected_document_class=SCANNED,
        acceptable_routes=(AUTOMATED, CAUTION),
        expected_page_classes=(SCANNED, SCANNED),
        page_texts=(_text(DISCHARGE_EN_P1), _text(DISCHARGE_EN_P2)),
        fields=DISCHARGE_EN_FIELDS,
        notes="Clean 300 dpi scan of the born-digital discharge summary.",
    )
    return case, _image_only_pdf(images), ()


def build_scanned_fax_prescription_en(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    image = _fax(_render_gray(_text_pdf(RX_EN), 0, 300), seed)
    case = CorpusCase(
        case_id="scanned_fax_prescription_en",
        category="scanned",
        language="en-US",
        mime_type="application/pdf",
        file_name="prescription-fax.pdf",
        expected_document_class=SCANNED,
        acceptable_routes=(AUTOMATED, CAUTION, CLINICIAN_ONLY),
        expected_page_classes=(SCANNED,),
        page_texts=(_text(RX_EN),),
        fields=RX_EN_FIELDS,
        notes="Fax simulation: 150 dpi, 1.5 degree skew, hard threshold, speckle, streaks.",
    )
    return case, _image_only_pdf([image]), ()


def build_scanned_rotated_lab_es(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    image = _render_gray(_text_pdf(LAB_ES), 0, 300).rotate(90, expand=True)
    case = CorpusCase(
        case_id="scanned_rotated_lab_es_90",
        category="scanned",
        language="es-MX",
        mime_type="application/pdf",
        file_name="laboratorio-rotado.pdf",
        expected_document_class=SCANNED,
        acceptable_routes=(AUTOMATED, CAUTION),
        expected_page_classes=(SCANNED,),
        page_texts=(_text(LAB_ES),),
        fields=LAB_ES_FIELDS,
        notes="Spanish laboratory page scanned sideways (rotated 90 degrees).",
    )
    return case, _image_only_pdf([image]), ()


def build_scanned_low_res_medlist_en(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    image = _low_resolution(_render_gray(_text_pdf(MEDLIST_SHORT_EN), 0, 300))
    case = CorpusCase(
        case_id="scanned_low_res_medlist_en_72dpi",
        category="scanned",
        language="en-US",
        mime_type="application/pdf",
        file_name="medication-list-lowres.pdf",
        expected_document_class=SCANNED,
        acceptable_routes=(AUTOMATED, CAUTION, CLINICIAN_ONLY),
        expected_page_classes=(SCANNED,),
        page_texts=(_text(MEDLIST_SHORT_EN),),
        fields=MEDLIST_SHORT_FIELDS,
        notes="72 dpi JPEG-degraded scan; upscaling and confidence routing are measured.",
    )
    return case, _image_only_pdf([image]), ()


def build_scanned_abbreviations_es(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    image = _render_gray(_text_pdf(ABBREV_ES), 0, 300)
    case = CorpusCase(
        case_id="scanned_abbreviations_es_300dpi",
        category="scanned",
        language="es-MX",
        mime_type="application/pdf",
        file_name="indicaciones-scan.pdf",
        expected_document_class=SCANNED,
        acceptable_routes=(AUTOMATED, CAUTION),
        expected_page_classes=(SCANNED,),
        page_texts=(_text(ABBREV_ES),),
        fields=ABBREV_ES_FIELDS,
        notes="Spanish medical abbreviations (VO, c/8 h, PRN, mcg/inh) at clean 300 dpi.",
    )
    return case, _image_only_pdf([image]), ()


def build_scanned_dosages_en_200dpi(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    image = _render_gray(_text_pdf(DOSAGES_EN), 0, 200)
    case = CorpusCase(
        case_id="scanned_difficult_dosages_en_200dpi",
        category="scanned",
        language="en-US",
        mime_type="application/pdf",
        file_name="medication-list-scan.pdf",
        expected_document_class=SCANNED,
        acceptable_routes=(AUTOMATED, CAUTION),
        expected_page_classes=(SCANNED,),
        page_texts=(_text(DOSAGES_EN),),
        fields=DOSAGES_EN_FIELDS,
        notes="Difficult dosages and dates at 200 dpi.",
    )
    return case, _image_only_pdf([image]), ()


def build_prescription_label_png_en(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    import fitz

    doc = fitz.open()
    _add_text_page(doc, LABEL_EN, font_size=13, left=40, top=70, line_height=22)
    image = _render_gray(_pdf_bytes(doc), 0, 200).crop((60, 100, 1150, 760))
    case = CorpusCase(
        case_id="prescription_label_png_en",
        category="prescription_image",
        language="en-US",
        mime_type="image/png",
        file_name="pharmacy-label.png",
        expected_document_class=SCANNED,
        acceptable_routes=(AUTOMATED, CAUTION),
        expected_page_classes=(SCANNED,),
        page_texts=(_text(LABEL_EN),),
        fields=LABEL_EN_FIELDS,
        notes="Pharmacy label photo in PNG; uppercase sig line and refill counts.",
    )
    return case, _png(image), ()


def build_prescription_label_jpeg_es(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    import fitz

    doc = fitz.open()
    _add_text_page(doc, LABEL_ES, font_size=13, left=40, top=70, line_height=22)
    image = _render_gray(_pdf_bytes(doc), 0, 200).crop((60, 100, 1150, 700))
    case = CorpusCase(
        case_id="prescription_label_jpeg_es",
        category="prescription_image",
        language="es-MX",
        mime_type="image/jpeg",
        file_name="etiqueta-farmacia.jpg",
        expected_document_class=SCANNED,
        acceptable_routes=(AUTOMATED, CAUTION),
        expected_page_classes=(SCANNED,),
        page_texts=(_text(LABEL_ES),),
        fields=LABEL_ES_FIELDS,
        notes="Spanish pharmacy label as JPEG with accents in uppercase.",
    )
    return case, _jpeg(image, 80), ()


def build_prescription_photo_skewed_en(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    image = _phone_photo(_render_gray(_text_pdf(RX_EN), 0, 200), seed)
    case = CorpusCase(
        case_id="prescription_photo_skewed_en",
        category="prescription_image",
        language="en-US",
        mime_type="image/jpeg",
        file_name="prescription-photo.jpg",
        expected_document_class=SCANNED,
        acceptable_routes=(AUTOMATED, CAUTION, CLINICIAN_ONLY),
        expected_page_classes=(SCANNED,),
        page_texts=(_text(RX_EN),),
        fields=RX_EN_FIELDS,
        notes="Phone photo simulation: 4 degree skew, blur, lighting gradient, JPEG q60.",
    )
    return case, _jpeg(image, 60), ()


def build_handwritten_note_png(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    image, note = _handwriting(HANDWRITTEN, seed)
    case = CorpusCase(
        case_id="handwritten_note_png",
        category="prescription_image",
        language="en-US",
        mime_type="image/png",
        file_name="handwritten-note.png",
        expected_document_class=SCANNED,
        acceptable_routes=(CAUTION, CLINICIAN_ONLY),
        expected_page_classes=(SCANNED,),
        page_texts=(_text(HANDWRITTEN),),
        fields=HANDWRITTEN_FIELDS,
        notes="Handwriting simulation; must not reach automated candidates.",
    )
    return case, _png(image), (note,)


def build_mixed_page_pdf(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    import fitz

    attachment = _render_gray(_text_pdf(MIXED_ATTACHMENT), 0, 200).crop((80, 120, 1300, 460))
    doc = fitz.open()
    page = _add_text_page(doc, MIXED_HEADER)
    page.insert_image(fitz.Rect(48, 200, 564, 620), stream=_png(attachment))
    case = CorpusCase(
        case_id="mixed_text_and_scanned_attachment_pdf",
        category="born_digital",
        language="en-US",
        mime_type="application/pdf",
        file_name="referral-with-attachment.pdf",
        expected_document_class=MIXED,
        acceptable_routes=(AUTOMATED, CAUTION),
        expected_page_classes=(MIXED,),
        page_texts=(_text([*MIXED_HEADER, *MIXED_ATTACHMENT]),),
        fields=MIXED_FIELDS,
        notes="Born-digital header plus an embedded scanned medication list image.",
    )
    return case, _pdf_bytes(doc), ()


def build_blank_pages_pdf(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    import fitz

    doc = fitz.open()
    _add_text_page(doc, MEDLIST_SHORT_EN)
    doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    noise = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    noise.insert_image(noise.rect, stream=_png(_speckled_blank((1275, 1650), seed, 0.0006)))
    case = CorpusCase(
        case_id="blank_and_noise_pages_pdf",
        category="adversarial",
        language="en-US",
        mime_type="application/pdf",
        file_name="medication-list-with-blank-pages.pdf",
        expected_document_class=BORN_DIGITAL,
        acceptable_routes=(AUTOMATED,),
        expected_page_classes=(BORN_DIGITAL, BLANK, BLANK),
        page_texts=(_text(MEDLIST_SHORT_EN), "", ""),
        fields=MEDLIST_SHORT_FIELDS,
        notes="Content page followed by an empty page and a faint scanner-noise page.",
    )
    return case, _pdf_bytes(doc), ()


def build_garbage_text_layer_pdf(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    import fitz

    image = _render_gray(_text_pdf(RX_EN), 0, 300)
    doc = fitz.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.insert_image(page.rect, stream=_png(image))
    y = 80.0
    words = GARBAGE_TOKENS.split()
    for start in range(0, len(words), 8):
        page.insert_text(
            (48, y), " ".join(words[start : start + 8]), fontsize=10, fontname=FONT, render_mode=3
        )
        y += 15
    case = CorpusCase(
        case_id="garbage_text_layer_over_scan_pdf",
        category="adversarial",
        language="en-US",
        mime_type="application/pdf",
        file_name="prescription-bad-ocr-layer.pdf",
        expected_document_class=SCANNED,
        acceptable_routes=(AUTOMATED, CAUTION),
        expected_page_classes=(SCANNED,),
        page_texts=(_text(RX_EN),),
        fields=RX_EN_FIELDS,
        notes="Scan carrying an invisible garbage text layer from a prior bad OCR pass.",
    )
    return case, _pdf_bytes(doc), ()


def build_encrypted_pdf(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    import fitz

    doc = fitz.open()
    _add_text_page(doc, MEDLIST_SHORT_EN)
    data = _pdf_bytes(
        doc,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="synthetic-user",
        owner_pw="synthetic-owner",
    )
    case = CorpusCase(
        case_id="encrypted_pdf",
        category="adversarial",
        language="en-US",
        mime_type="application/pdf",
        file_name="medication-list-encrypted.pdf",
        expected_document_class=ENCRYPTED,
        acceptable_routes=(REJECTED,),
        expected_page_classes=(),
        page_texts=(),
        notes="AES-256 user password; must be rejected without retry.",
    )
    return case, data, ()


def build_unreadable_bytes_pdf(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    rng = random.Random(seed)
    data = bytes(rng.getrandbits(8) for _ in range(4096))
    case = CorpusCase(
        case_id="unreadable_random_bytes_pdf",
        category="adversarial",
        language="en-US",
        mime_type="application/pdf",
        file_name="corrupt.pdf",
        expected_document_class=UNREADABLE,
        acceptable_routes=(REJECTED,),
        expected_page_classes=(),
        page_texts=(),
        notes="Random bytes with a PDF extension and MIME type.",
    )
    return case, data, ()


def build_truncated_pdf(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    pdf = _discharge_pdf()
    data = pdf[: int(len(pdf) * 0.55)]
    case = CorpusCase(
        case_id="truncated_pdf",
        category="adversarial",
        language="en-US",
        mime_type="application/pdf",
        file_name="discharge-summary-truncated.pdf",
        expected_document_class=UNREADABLE,
        acceptable_routes=(REJECTED, CAUTION),
        expected_page_classes=(),
        page_texts=(),
        notes="PDF cut at 55%; rejected, or repaired and flagged, never treated as complete.",
        acceptable_document_classes=(BORN_DIGITAL,),
    )
    return case, data, ()


def build_unsupported_docx(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    data = b"PK\x03\x04" + b"\x00" * 64
    case = CorpusCase(
        case_id="unsupported_docx",
        category="adversarial",
        language="en-US",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_name="notes.docx",
        expected_document_class=UNSUPPORTED,
        acceptable_routes=(REJECTED,),
        expected_page_classes=(),
        page_texts=(),
        notes="Word document bytes; unsupported container.",
    )
    return case, data, ()


def build_multi_page_tiff(seed: int) -> tuple[CorpusCase, bytes, tuple[str, ...]]:
    first = _render_gray(_text_pdf(RX_EN), 0, 200)
    second = _render_gray(_text_pdf(ABBREV_ES), 0, 200)
    buffer = io.BytesIO()
    try:
        first.save(
            buffer, format="TIFF", save_all=True, append_images=[second], compression="tiff_lzw"
        )
    except Exception:  # noqa: BLE001 - libtiff without LZW
        buffer = io.BytesIO()
        first.save(buffer, format="TIFF", save_all=True, append_images=[second])
    case = CorpusCase(
        case_id="multi_page_tiff_scans",
        category="scanned",
        language="en-US",
        mime_type="image/tiff",
        file_name="scans.tiff",
        expected_document_class=SCANNED,
        acceptable_routes=(AUTOMATED, CAUTION),
        expected_page_classes=(SCANNED, SCANNED),
        page_texts=(_text(RX_EN), _text(ABBREV_ES)),
        fields=tuple(
            [*RX_EN_FIELDS]
            + [GroundTruthField(f.fact_type, f.field, f.value, 2) for f in ABBREV_ES_FIELDS]
        ),
        notes="Two-frame TIFF with an English page and a Spanish page.",
    )
    return case, buffer.getvalue(), ()


BUILDERS: tuple[Builder, ...] = (
    build_born_digital_discharge_en,
    build_born_digital_lab_table_en,
    build_born_digital_two_column_en,
    build_born_digital_prescription_es,
    build_born_digital_dosages_en,
    build_scanned_discharge_en,
    build_scanned_fax_prescription_en,
    build_scanned_rotated_lab_es,
    build_scanned_low_res_medlist_en,
    build_scanned_abbreviations_es,
    build_scanned_dosages_en_200dpi,
    build_prescription_label_png_en,
    build_prescription_label_jpeg_es,
    build_prescription_photo_skewed_en,
    build_handwritten_note_png,
    build_mixed_page_pdf,
    build_blank_pages_pdf,
    build_garbage_text_layer_pdf,
    build_encrypted_pdf,
    build_unreadable_bytes_pdf,
    build_truncated_pdf,
    build_unsupported_docx,
    build_multi_page_tiff,
)


def build_corpus(out_dir: Path, *, seed: int = DEFAULT_SEED) -> list[BuiltCase]:
    """Write every case to ``out_dir`` and return the built cases with checksums."""
    out_dir.mkdir(parents=True, exist_ok=True)
    built: list[BuiltCase] = []
    for index, builder in enumerate(BUILDERS):
        case, data, notes = builder(seed + index)
        path = out_dir / f"{case.case_id}{Path(case.file_name).suffix}"
        path.write_bytes(data)
        built.append(BuiltCase(case, path, hashlib.sha256(data).hexdigest(), notes))
    manifest = {
        "seed": seed,
        "synthetic_only": True,
        "cases": [item.to_dict() for item in built],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return built


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for the corpus")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    built = build_corpus(args.out_dir, seed=args.seed)
    for item in built:
        print(f"{item.case.case_id:45s} {item.path.name:45s} {item.sha256[:12]}")
    print(f"{len(built)} synthetic cases written to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
