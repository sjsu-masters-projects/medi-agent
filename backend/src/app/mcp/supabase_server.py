"""Supabase MCP Server — patient data queries for AI agents.

Tools: medications, conditions, allergies, adherence stats, symptoms, full context.
Uses a shared Supabase connection via lazy-loaded admin client.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.clients.supabase import get_admin_client
from app.mcp.base import MCPServer

logger = structlog.get_logger(__name__)


class SupabaseServer(MCPServer):
    """MCP server for Supabase patient data queries."""

    def __init__(self) -> None:
        super().__init__(
            name="supabase",
            description="Query patient data: medications, conditions, allergies, adherence, symptoms",
        )
        self._client: Any = None

    @property
    def client(self) -> Any:  # type: ignore[no-untyped-def]
        """Lazy-load Supabase admin client."""
        if self._client is None:
            self._client = get_admin_client()
        return self._client

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "get_patient_medications",
                "description": "Get all active medications for a patient.",
                "input_schema": {
                    "type": "object",
                    "properties": {"patient_id": {"type": "string", "description": "Patient UUID"}},
                    "required": ["patient_id"],
                },
            },
            {
                "name": "get_patient_conditions",
                "description": "Get all active conditions for a patient.",
                "input_schema": {
                    "type": "object",
                    "properties": {"patient_id": {"type": "string", "description": "Patient UUID"}},
                    "required": ["patient_id"],
                },
            },
            {
                "name": "get_patient_allergies",
                "description": "Get all allergies for a patient.",
                "input_schema": {
                    "type": "object",
                    "properties": {"patient_id": {"type": "string", "description": "Patient UUID"}},
                    "required": ["patient_id"],
                },
            },
            {
                "name": "get_patient_adherence_stats",
                "description": "Get adherence statistics for a patient.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "patient_id": {"type": "string", "description": "Patient UUID"},
                        "days": {
                            "type": "integer",
                            "description": "Days to look back (default 30)",
                            "default": 30,
                        },
                    },
                    "required": ["patient_id"],
                },
            },
            {
                "name": "get_recent_symptoms",
                "description": "Get recent symptom reports for a patient.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "patient_id": {"type": "string", "description": "Patient UUID"},
                        "days": {
                            "type": "integer",
                            "description": "Days to look back (default 7)",
                            "default": 7,
                        },
                    },
                    "required": ["patient_id"],
                },
            },
            {
                "name": "get_patient_context",
                "description": "Get complete patient context (meds, conditions, allergies, symptoms, adherence).",
                "input_schema": {
                    "type": "object",
                    "properties": {"patient_id": {"type": "string", "description": "Patient UUID"}},
                    "required": ["patient_id"],
                },
            },
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        patient_id: str = arguments["patient_id"]

        match tool_name:
            case "get_patient_medications":
                return await self._get_patient_medications(patient_id)
            case "get_patient_conditions":
                return await self._get_patient_conditions(patient_id)
            case "get_patient_allergies":
                return await self._get_patient_allergies(patient_id)
            case "get_patient_adherence_stats":
                return await self._get_patient_adherence_stats(
                    patient_id, arguments.get("days", 30)
                )
            case "get_recent_symptoms":
                return await self._get_recent_symptoms(patient_id, arguments.get("days", 7))
            case "get_patient_context":
                return await self._get_patient_context(patient_id)
        raise ValueError(f"Unknown tool: {tool_name}")

    # ── Tool implementations ────────────────────────────

    async def _get_patient_medications(self, patient_id: str) -> dict[str, Any]:
        try:
            response = (
                self.client.table("medications")
                .select(
                    "id, name, dosage, frequency, instructions, rxcui, start_date, end_date, prescriber_id"
                )
                .eq("patient_id", patient_id)
                .eq("active", True)
                .order("start_date", desc=True)
                .execute()
            )
            return {
                "patient_id": patient_id,
                "medications": response.data,
                "count": len(response.data),
            }
        except Exception as e:
            logger.error("patient_meds_error", patient_id=patient_id, error=str(e))
            return {"patient_id": patient_id, "medications": [], "count": 0, "error": str(e)}

    async def _get_patient_conditions(self, patient_id: str) -> dict[str, Any]:
        try:
            response = (
                self.client.table("conditions")
                .select("id, name, icd10_code, onset_date, status, notes")
                .eq("patient_id", patient_id)
                .eq("active", True)
                .order("onset_date", desc=True)
                .execute()
            )
            return {
                "patient_id": patient_id,
                "conditions": response.data,
                "count": len(response.data),
            }
        except Exception as e:
            logger.error("patient_conditions_error", patient_id=patient_id, error=str(e))
            return {"patient_id": patient_id, "conditions": [], "count": 0, "error": str(e)}

    async def _get_patient_allergies(self, patient_id: str) -> dict[str, Any]:
        try:
            response = (
                self.client.table("allergies")
                .select("id, allergen, reaction, severity, onset_date, notes")
                .eq("patient_id", patient_id)
                .order("severity", desc=True)
                .execute()
            )
            return {
                "patient_id": patient_id,
                "allergies": response.data,
                "count": len(response.data),
            }
        except Exception as e:
            logger.error("patient_allergies_error", patient_id=patient_id, error=str(e))
            return {"patient_id": patient_id, "allergies": [], "count": 0, "error": str(e)}

    async def _get_patient_adherence_stats(self, patient_id: str, days: int = 30) -> dict[str, Any]:
        try:
            response = self.client.rpc(
                "get_adherence_stats",
                {"p_patient_id": patient_id, "p_days": days},
            ).execute()

            if not response.data:
                return {
                    "patient_id": patient_id,
                    "adherence_rate": 0,
                    "streak": 0,
                    "total_doses": 0,
                    "taken_doses": 0,
                    "days": days,
                }

            stats = response.data[0]
            return {
                "patient_id": patient_id,
                "adherence_rate": stats.get("adherence_rate", 0),
                "streak": stats.get("streak", 0),
                "total_doses": stats.get("total_doses", 0),
                "taken_doses": stats.get("taken_doses", 0),
                "days": days,
            }
        except Exception as e:
            logger.error("patient_adherence_error", patient_id=patient_id, error=str(e))
            return {
                "patient_id": patient_id,
                "adherence_rate": 0,
                "streak": 0,
                "total_doses": 0,
                "taken_doses": 0,
                "days": days,
                "error": str(e),
            }

    async def _get_recent_symptoms(self, patient_id: str, days: int = 7) -> dict[str, Any]:
        try:
            cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
            response = (
                self.client.table("symptom_reports")
                .select(
                    "id, symptom, severity, onset_date, related_medication_id, notes, created_at"
                )
                .eq("patient_id", patient_id)
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .execute()
            )
            return {
                "patient_id": patient_id,
                "symptoms": response.data,
                "count": len(response.data),
                "days": days,
            }
        except Exception as e:
            logger.error("patient_symptoms_error", patient_id=patient_id, error=str(e))
            return {
                "patient_id": patient_id,
                "symptoms": [],
                "count": 0,
                "days": days,
                "error": str(e),
            }

    async def _get_patient_context(self, patient_id: str) -> dict[str, Any]:
        """Fetch all patient data in parallel."""
        try:
            meds, conditions, allergies, symptoms, adherence = await asyncio.gather(
                self._get_patient_medications(patient_id),
                self._get_patient_conditions(patient_id),
                self._get_patient_allergies(patient_id),
                self._get_recent_symptoms(patient_id, days=7),
                self._get_patient_adherence_stats(patient_id, days=30),
            )
            return {
                "patient_id": patient_id,
                "medications": meds.get("medications", []),
                "conditions": conditions.get("conditions", []),
                "allergies": allergies.get("allergies", []),
                "recent_symptoms": symptoms.get("symptoms", []),
                "adherence": {
                    "rate": adherence.get("adherence_rate", 0),
                    "streak": adherence.get("streak", 0),
                },
            }
        except Exception as e:
            logger.error("patient_context_error", patient_id=patient_id, error=str(e))
            return {"patient_id": patient_id, "error": str(e)}


supabase_server = SupabaseServer()
