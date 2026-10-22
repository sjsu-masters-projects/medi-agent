/**
 * Care plans per care team (PLAN-002, CLN-003 slices G and H).
 *
 * Mirrors the JSON the backend returns (snake_case) for the endpoints documented in
 * `.agent/specs/plan-002-care-plans-per-care-team.md#api-contract-pr-210`.
 */

export type PlanOwnershipState = "owned" | "unowned" | "unassigned_legacy";

/** Names only: no contact details. The portals compose the display label. */
export interface PlanOwner {
    care_plan_id: string;
    /** Null while the plan is unowned or unassigned. */
    care_team_id: string | null;
    ownership_state: PlanOwnershipState;
    specialty: string | null;
    clinician_name: string | null;
    clinic_id: string | null;
    clinic_name: string | null;
    /** True for unowned and unassigned plans: show "no longer on your care team". */
    unowned_notice: boolean;
}

export interface CareTeamFilterOption {
    /** Null for the shared "no longer on your care team" bucket (filter value "unowned"). */
    care_team_id: string | null;
    ownership_state: PlanOwnershipState;
    specialty: string | null;
    clinician_name: string | null;
    clinic_name: string | null;
    count: number;
}

// ── Clinician: plans of one patient ──────────────────────────────────────────────────────

export interface ClinicianPlanListEntry {
    care_plan_id: string;
    care_team_id: string | null;
    ownership_state: PlanOwnershipState;
    origin: "native" | "adopted" | "legacy";
    owner: Pick<PlanOwner, "specialty" | "clinician_name" | "clinic_id" | "clinic_name">;
    approved_at: string | null;
    unowned_since: string | null;
    is_mine: boolean;
    /** Present only when is_mine. */
    active_version_id?: string | null;
    draft_version_id?: string | null;
    latest_version_number?: number | null;
    generation?: Record<string, unknown> | null;
    /** Present only for unowned or unassigned plans: my care teams that may adopt it. */
    adoptable_by_care_team_ids?: string[];
}

export interface ClinicianPlanList {
    plans: ClinicianPlanListEntry[];
}

// ── Publication and cross-plan conflicts ─────────────────────────────────────────────────

export type CrossPlanConflictKind =
    | "duplicate_medication"
    | "regimen_difference"
    | "stop_continue"
    | "schedule_overlap";

export interface ConflictMedication {
    name?: string;
    dosage?: string;
    frequency?: string;
    route?: string;
    instructions?: string;
    /** True for a shared-list entry that no plan owns. */
    shared_list?: boolean;
    /** Non-medication overlaps reveal only the category, never the other team's wording. */
    category?: string;
}

export interface CrossPlanConflict {
    fingerprint: string;
    kind: CrossPlanConflictKind;
    /** "blocker" must be resolved; "warning" never blocks. */
    severity: "blocker" | "warning";
    identity_basis: "canonical_target" | "recorded_ingredient" | "recorded_name" | "activity_instruction";
    draft_item_id: string;
    ours: ConflictMedication;
    theirs: ConflictMedication;
    other_plan: {
        care_plan_id: string;
        ownership_state: PlanOwnershipState;
        specialty: string | null;
        clinician_name: string | null;
        clinic_name: string | null;
        approved_at: string | null;
    } | null;
    shared_list_entry_id: string | null;
    acknowledged: boolean;
    acknowledged_reason: string | null;
    asked_other_team: boolean;
}

export interface CrossPlanReview {
    /** Always "not_checked": interaction severity is not assessed (MED-001). */
    interaction_coverage: "not_checked";
    conflicts: CrossPlanConflict[];
}

export interface PublishCarePlanRequest {
    note: string;
    /** One per publish attempt; a retry with the same key publishes once. */
    idempotency_key?: string;
    /** "Publish without this item": the items stay pending in the next draft. */
    excluded_item_ids?: string[];
}

export interface PublishCarePlanResult {
    status: "approved";
    plan_version_id: string;
    care_plan_id: string;
    recommendation_id: string;
    published_item_count: number;
    excluded_item_ids: string[];
    next_draft_version_id?: string;
    acknowledged_fingerprints: string[];
    warnings: Array<{ kind: CrossPlanConflictKind; draft_item_id: string; other_care_plan_id: string | null }>;
    interaction_coverage: "not_checked";
    replayed: boolean;
}

/** HTTP 409 body `error.details` when code is CROSS_PLAN_CONFLICT. */
export interface CrossPlanConflictDetails {
    conflicts: CrossPlanConflict[];
    interaction_coverage: "not_checked";
}

export interface CrossPlanResolutionRequest {
    resolution: "keep_both" | "ask_other_team";
    /** Required, 1-2000 characters; for ask_other_team it is the question. */
    reason: string;
}

// ── Review items, adoption, retirement ───────────────────────────────────────────────────

export type ReviewItemKind =
    | "unassigned_legacy_plan"
    | "unowned_plan"
    | "cross_plan_conflict"
    | "conflict_acknowledged"
    | "conflict_published_without"
    | "conflict_reply"
    | "unowned_clinical_record";

export interface PlanReviewItem {
    id: string;
    patient_id: string;
    /** The patient's display name (already visible to the addressed team). */
    patient_name: string | null;
    /** The clinic of the addressed care-team link. */
    clinic_id: string | null;
    clinic_name: string | null;
    care_plan_id: string | null;
    kind: ReviewItemKind;
    target_care_team_id: string;
    conflict_fingerprint: string | null;
    /** Conflict items: { ours, theirs, from }. Medication fields and plan metadata only. */
    summary: Record<string, unknown>;
    request_note: string | null;
    reply_note: string | null;
    status: "open" | "resolved" | "withdrawn";
    created_at: string;
    resolved_at: string | null;
}

/** For a clinic admin: that work exists, never which patient or activity. */
export interface ClinicReviewItem {
    id: string;
    care_plan_id: string | null;
    kind: ReviewItemKind;
    target_clinic_id: string;
    status: "open" | "resolved" | "withdrawn";
    created_at: string;
}

export interface ReviewItemList {
    items: PlanReviewItem[];
    clinic_items: ClinicReviewItem[];
}

export interface UnownedPlanActivities {
    care_plan_id: string;
    ownership_state: Exclude<PlanOwnershipState, "owned">;
    previous_owner: Pick<PlanOwner, "specialty" | "clinician_name" | "clinic_id" | "clinic_name">;
    unowned_since: string | null;
    approved_at: string | null;
    activities: Array<{
        id: string;
        category: string;
        title: string;
        instructions: string;
        frequency: string;
        medication: Record<string, unknown>;
        wording: Record<string, unknown>;
    }>;
}

export interface AdoptPlanRequest {
    care_team_id: string;
    note: string;
}

export interface RetireItemsRequest {
    care_team_id: string;
    item_ids: string[];
    reason: string;
}

// ── Shared clinical core ─────────────────────────────────────────────────────────────────

export interface RecordedBy {
    care_team_id?: string;
    specialty?: string | null;
    clinician_name?: string;
    clinic_id?: string | null;
    clinic_name?: string | null;
}

export interface SharedClinicalSummary {
    medications: Array<{
        id: string; name: string; dosage: string; frequency: string; route: string;
        instructions: string | null; recorded_by: RecordedBy; recorded_by_care_team_id: string | null;
    }>;
    allergies: Array<{
        id: string; allergen: string; reaction: string | null; severity: string;
        recorded_by: RecordedBy; recorded_by_care_team_id: string | null;
    }>;
    /** Active conditions this clinician may see. Never a silently shorter list: see below. */
    conditions: Array<{
        id: string; name: string; icd10_code: string | null; status: string;
        recorded_by: RecordedBy; recorded_by_care_team_id: string | null;
    }>;
    /** True when the patient keeps some active conditions private: show the explicit marker. */
    some_conditions_private: boolean;
    care_teams: Array<RecordedBy & {
        is_mine: boolean;
        plan: { care_plan_id: string; ownership_state: PlanOwnershipState; approved_at: string | null } | null;
    }>;
}

export interface PatientCondition {
    id: string;
    name: string;
    icd10_code: string | null;
    status: string;
    is_sensitive: boolean;
    recorded_by: RecordedBy;
}

// ── Document routing ─────────────────────────────────────────────────────────────────────

export interface UploadCareTeamOption {
    care_team_id: string;
    specialty: string | null;
    clinician_name: string | null;
    clinic_id: string | null;
    clinic_name: string | null;
}

export type DocumentRoutingState = "routed" | "unrouted";

/** Added to document create requests. Patient: choose care_team_id or not_sure. */
export interface DocumentRoutingChoice {
    care_team_id?: string;
    not_sure?: boolean;
}

// ── Patient: merged Today ────────────────────────────────────────────────────────────────

/** Added to every Today task; `plan_owner` is null for activities with no care-plan item. */
export interface TodayTaskOwnership {
    plan_owner: PlanOwner | null;
    /** Every owner when identical activities of several plans are shown as one entry. */
    plan_owners: PlanOwner[];
    /** The underlying medication/obligation ids (the entry's own id first). */
    combined_item_ids: string[];
}

export interface TodayOwnershipSummary {
    care_team_filters: CareTeamFilterOption[];
    /** True when the patient has no active care team and an activity has lost its owner. */
    contact_clinic: boolean;
}

/** POST /care-plans/clinician/records/{adr_assessment|medwatch_draft}/{id}/take */
export interface TakeRecordRequest {
    care_team_id: string;
}

/** Notification-centre item for a care-team work item (event_type "care_plan_review"). */
export interface CarePlanReviewNotificationMetadata {
    review_kind: ReviewItemKind;
    care_plan_id: string | null;
}

/** GET /care-plans/clinician/patients/{id}/care-team-options: my own active links. */
export interface ClinicianCareTeamOption {
    care_team_id: string;
    patient_id: string;
    clinician_id: string;
    clinic_id: string;
    clinic_name: string | null;
    /** Care-team specialty, else the clinician's, else the link's role. Null if none. */
    specialty: string | null;
}
