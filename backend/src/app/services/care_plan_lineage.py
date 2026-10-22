"""Which care plan a clinician is working in (PLAN-002).

A plan belongs to one care-team link. A clinician acts on a plan only through an active link
of their own to that plan's patient (with active membership at the link's clinic). Another
team's plan is answered exactly like a missing one, so nothing confirms it exists. When a
clinician holds several links to the patient (two clinics) and more than one has a plan, the
caller must name the care team; nothing is guessed.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core import authorization_reasons as reasons
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.services.care_team_plan_scope import CareTeamPlanScope, CareTeamPlanScopeService

OWNER_FIELDS = ("specialty", "clinician_name", "clinic_id", "clinic_name")


def _denied(clinician_id: UUID, patient_id: UUID) -> AuthorizationError:
    return AuthorizationError(
        "You are not assigned to this patient",
        reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
        actor_id=str(clinician_id),
        actor_role="clinician",
        target_type="patient",
        target_id=str(patient_id),
    )


def owner_from_snapshot(plan: dict[str, Any]) -> dict[str, Any]:
    """The last known owner display of a plan (names only, no contact details)."""
    snapshot = cast(dict[str, Any], plan.get("owner_snapshot") or {})
    return {field: snapshot.get(field) for field in OWNER_FIELDS}


class CarePlanLineageService:
    def __init__(self, db: Client) -> None:
        self.db = db
        self.scopes = CareTeamPlanScopeService(db)

    # ── reads of the plan rows ────────────────────────────────────────────────────────────
    def plans_for_patient(self, patient_id: UUID) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self.db.table("care_plans")
            .select("*")
            .eq("patient_id", str(patient_id))
            .order("created_at")
            .execute()
            .data
            or [],
        )

    def plan(self, care_plan_id: UUID | str) -> dict[str, Any] | None:
        rows = cast(
            list[dict[str, Any]],
            self.db.table("care_plans").select("*").eq("id", str(care_plan_id)).execute().data
            or [],
        )
        return rows[0] if rows else None

    def team_displays(self, team_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Specialty, clinician and clinic of live links, keyed by care-team id."""
        if not team_ids:
            return {}
        rows = cast(
            list[dict[str, Any]],
            self.db.table("care_teams")
            .select(
                "id, role, specialty_context, clinic_id, "
                "clinics(display_name), clinicians(first_name, last_name, specialty)"
            )
            .in_("id", sorted(set(team_ids)))
            .execute()
            .data
            or [],
        )
        displays: dict[str, dict[str, Any]] = {}
        for row in rows:
            clinician = cast(dict[str, Any], row.get("clinicians") or {})
            clinic = cast(dict[str, Any], row.get("clinics") or {})
            name = " ".join(
                part for part in (clinician.get("first_name"), clinician.get("last_name")) if part
            )
            displays[str(row["id"])] = {
                "specialty": row.get("specialty_context")
                or clinician.get("specialty")
                or row.get("role"),
                "clinician_name": name or None,
                "clinic_id": row.get("clinic_id"),
                "clinic_name": clinic.get("display_name"),
            }
        return displays

    def owner_view(
        self, plan: dict[str, Any], displays: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Live owner for an owned plan, last known owner for an unowned one."""
        if plan.get("ownership_state") == "owned" and plan.get("care_team_id"):
            live = displays.get(str(plan["care_team_id"]))
            if live:
                return {field: live.get(field) for field in OWNER_FIELDS}
        return owner_from_snapshot(plan)

    # ── selecting the plan a clinician works in ───────────────────────────────────────────
    def clinician_scopes(self, clinician_id: UUID, patient_id: UUID) -> list[CareTeamPlanScope]:
        scopes = self.scopes.list_for_clinician(clinician_id, patient_id)
        if not scopes:
            raise _denied(clinician_id, patient_id)
        return scopes

    def select_owned_plan(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        *,
        care_team_id: UUID | None = None,
        care_plan_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        """The clinician's own plan. None when the chosen team has no plan yet."""
        scopes = self.clinician_scopes(clinician_id, patient_id)
        mine = {str(scope.care_team_id) for scope in scopes}
        if care_team_id is not None and str(care_team_id) not in mine:
            raise NotFoundError("Care team", str(care_team_id))
        plans = [
            plan
            for plan in self.plans_for_patient(patient_id)
            if plan.get("ownership_state") == "owned" and str(plan.get("care_team_id")) in mine
        ]
        if care_plan_id is not None:
            plans = [plan for plan in plans if str(plan["id"]) == str(care_plan_id)]
            if not plans:
                raise NotFoundError("Care plan", str(care_plan_id))
        if care_team_id is not None:
            plans = [plan for plan in plans if str(plan["care_team_id"]) == str(care_team_id)]
        if len(plans) > 1:
            # An adopted plan sits beside the team's own plan: the native one is the default.
            native = [plan for plan in plans if plan.get("origin") == "native"]
            same_team = len({str(plan["care_team_id"]) for plan in plans}) == 1
            if same_team and len(native) == 1 and care_plan_id is None:
                return native[0]
            raise ValidationError(
                "Choose the care team for this plan",
                code="CARE_TEAM_REQUIRED",
                details={
                    "options": [
                        {"care_team_id": plan["care_team_id"], "care_plan_id": plan["id"]}
                        for plan in plans
                    ]
                },
            )
        return plans[0] if plans else None

    def scope_for_team(
        self, clinician_id: UUID, patient_id: UUID, care_team_id: UUID | None
    ) -> CareTeamPlanScope:
        """Exact link for an action that creates something (a plan, a clinician entry)."""
        scopes = self.clinician_scopes(clinician_id, patient_id)
        if care_team_id is not None:
            scopes = [scope for scope in scopes if scope.care_team_id == care_team_id]
            if not scopes:
                raise NotFoundError("Care team", str(care_team_id))
        if len(scopes) != 1:
            raise ValidationError(
                "Choose the care team for this plan",
                code="CARE_TEAM_REQUIRED",
                details={"options": [{"care_team_id": str(s.care_team_id)} for s in scopes]},
            )
        return scopes[0]

    def ensure_plan_id(self, clinician_id: UUID, scope: CareTeamPlanScope) -> UUID:
        result = self.db.rpc(
            "ensure_care_plan_for_clinician",
            {"p_care_team_id": str(scope.care_team_id), "p_actor_id": str(clinician_id)},
        ).execute()
        return UUID(str(result.data))

    def require_owned_version(
        self, clinician_id: UUID, patient_id: UUID, version_id: UUID
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """(version, plan) when the clinician owns the version's plan; otherwise not found.

        A version of another team's plan, of an unowned plan or of another patient is
        indistinguishable from a version that does not exist.
        """
        scopes = self.clinician_scopes(clinician_id, patient_id)
        versions = cast(
            list[dict[str, Any]],
            self.db.table("care_plan_versions")
            .select("*")
            .eq("id", str(version_id))
            .eq("patient_id", str(patient_id))
            .execute()
            .data
            or [],
        )
        plan = self.plan(versions[0]["care_plan_id"]) if versions else None
        mine = {str(scope.care_team_id) for scope in scopes}
        if (
            not versions
            or plan is None
            or plan.get("ownership_state") != "owned"
            or str(plan.get("care_team_id")) not in mine
        ):
            raise NotFoundError("Care plan", str(version_id))
        return versions[0], plan
