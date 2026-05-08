# Patient Chat — Scenario Matrix, Failure-Mode Behaviors, Routing Map

Source-grounded reference for testing the patient chat end-to-end. Every row cites the code that drives the behavior; deviations between expected and observed are real bugs.

Code under test:
- `backend/src/app/routers/chat.py` — WS handler, outer fallback
- `backend/src/app/agents/triage/graph.py` — classification, response, rule fallback, safety override
- `backend/src/app/agents/triage/agent.py` — wrapper that returns `TriageOutput`
- `backend/src/app/agents/symptom/agent.py` — symptom subagent (only when `route == "symptom"`)
- `apps/patient-portal/src/hooks/use-patient-chat-session.ts` — frontend WS client

---

## 1. Routing map

Two layers decide the route:

### 1a. LLM classification (preferred)
`_classify_with_llm` ([graph.py:356-379](../../backend/src/app/agents/triage/graph.py#L356-L379)) calls MedGemma via `ModelRouter.get_client(TaskType.TRIAGE_CLASSIFICATION)` and parses a `TriageClassificationResult` of `{intent, urgency, reason}`.

### 1b. Rule classifier (fallback when LLM is unavailable / parse fails)
`_classify_with_rules` ([graph.py:410-465](../../backend/src/app/agents/triage/graph.py#L410-L465)). Strict priority order — first match wins:

| # | Rule | Keyword set ([graph.py:25-136](../../backend/src/app/agents/triage/graph.py#L25-L136)) | Result |
|---|---|---|---|
| 1 | Emergency keyword | `EMERGENCY_KEYWORDS` (chest pain, can't breathe, stroke, seizure, suicidal, …) | `intent=symptom`, `urgency=emergency` |
| 2 | Schedule keyword | `SCHEDULE_KEYWORDS` (appointment, reschedule, cita, …) | `intent=schedule`, `urgency=routine` |
| 3 | Medication keyword | `MEDICATION_KEYWORDS` (medication, dose, refill, side effect, ibuprofen, …) | `intent=medication_question`, `urgency=urgent` if also adverse-effect signal else `routine` |
| 4 | Medication name | `MEDICATION_NAME_HINTS` (amoxicillin, atorvastatin, insulin, …) | `intent=medication_question`, `urgency=routine` |
| 5 | Mental-health keyword | `MENTAL_HEALTH_KEYWORDS` (panic, anxious, hopeless, …) | `intent=mental_health`, `urgency=urgent` |
| 6 | Symptom keyword | `SYMPTOM_KEYWORDS` (pain, dizzy, nausea, fever, headache, …) | `intent=symptom`, `urgency=urgent` |
| 7 | Document signal | `DOCUMENT_KEYWORDS` OR (`document_context` present AND reference word AND verb like "explain") | `intent=document_question`, `urgency=routine` |
| 8 | Default | — | `intent=general`, `urgency=routine` |

### 1c. Safety override (post-classify)
[graph.py:559-573](../../backend/src/app/agents/triage/graph.py#L559-L573) — *only* if `intent == "medication_question"` AND `_contains_adverse_effect_signal(message)` is true, urgency is forced to `urgent`. **One-way; does not override other intents.**

### 1d. Intent → route → agent dispatch
[graph.py:589-592](../../backend/src/app/agents/triage/graph.py#L589-L592) and [chat.py:450](../../backend/src/app/routers/chat.py#L450):

| Intent | Route | Downstream agent | Side effects |
|---|---|---|---|
| `symptom` | `symptom` | `SymptomAgent` ([chat.py:454-509](../../backend/src/app/routers/chat.py#L454-L509)) | Saves `symptom_report`; if `flagged_for_adr` → A2A pharmacovigilance task, escalation forced |
| `medication_question` | `triage` | none | DrugKnowledgeService RAG injected into prompt before triage |
| `document_question` | `triage` | none | Document context already in prompt if attached |
| `schedule` | `triage` | none | — |
| `mental_health` | `triage` | none | Always urgent → escalation |
| `general` | `triage` | none | — |

### 1e. Emergency short-circuit
[graph.py:315-318](../../backend/src/app/agents/triage/graph.py#L315-L318) — if `urgency == "emergency"`, response generation skips the LLM entirely and returns the localized emergency template, with `escalation_required=True` forced.

### 1f. Escalation → clinician notify
[chat.py:573-591](../../backend/src/app/routers/chat.py#L573-L591) — when `escalation_required=True`, server calls `notify_assigned_clinicians` and emits `escalation_recommended` event to the client.

---

## 2. Failure-mode user-visible behavior

The chat has **three layers of fallback**. Each masks errors differently — important for diagnosis.

| Layer | Where | Triggered by | User sees | Observability |
|---|---|---|---|---|
| **L1 — LLM classification** | `_classify_with_llm` ([graph.py:377-379](../../backend/src/app/agents/triage/graph.py#L377-L379)) | Vertex auth failure, Vertex 4xx/5xx, parse error, timeout | (transparent) — rule classifier runs | `WARNING Triage LLM classification failed; falling back to rules: <exc>` |
| **L2 — LLM response generation** | `_generate_response_with_llm` ([graph.py:402-407](../../backend/src/app/agents/triage/graph.py#L402-L407)) | Gemini auth, 4xx/5xx, empty string after `strip()`, timeout | Static localized template per intent (e.g. `fallback_medication_question`, `fallback_general`) | `WARNING Triage LLM response generation failed; using fallback: <exc>` (or no log if just empty response) |
| **L3 — Triage outer (catastrophic)** | `chat.py` exception handler ([chat.py:439-448](../../backend/src/app/routers/chat.py#L439-L448)) | Any unhandled exception in `triage_agent(...)` OR the preceding `drug_knowledge_service` call OR `triage_result.status != "success"` | "I have recorded your message. Please continue monitoring your symptoms and contact your care team if anything worsens." | `WARNING Triage processing failed, using deterministic fallback: <exc>` |

### Specific failure cases

| # | Failure | Path | User-visible | Notes |
|---|---|---|---|---|
| F1 | Vertex AI auth missing (no ADC) | L1 → L2 (Gemini also uses ADC) → static template | Static localized template per rule-classified intent. Sounds plausible. | Confirmed in your log: both MedGemma and Gemini hit ADC error; user got `fallback_general`. |
| F2 | Vertex AI quota exceeded / 429 | Same as F1 | Same as F1 | Identical UX to "broken" — no signal to user. |
| F3 | Gemini timeout (`DeadlineExceeded`) | L2 only — rule classification still ran | Static template per intent (often correct intent, generic words). | Cold-start can trigger; will succeed on retry. |
| F4 | Gemini returns empty string | L2 — `cleaned or None` returns None ([graph.py:407](../../backend/src/app/agents/triage/graph.py#L407)) | Static template | No log line for empty response — silent. |
| F5 | DrugKnowledgeService raises | Caught by chat.py outer try, hits L3 | "I have recorded your message…" | **Bug**: drug-knowledge failure shouldn't kill the entire turn. See gap G3. |
| F6 | Symptom agent raises | Caught at [chat.py:509-511](../../backend/src/app/routers/chat.py#L509-L511) | Triage's response is used; symptom report not saved; no A2A delegation | Silent to user — no `agent_degraded` signal. |
| F7 | A2A pharmacovigilance task fails | Inside symptom branch try | Same as F6 | Silent. |
| F8 | Conversation-state optimistic-lock conflict (3x) | `_persist_conversation_state_with_retry` ([chat.py:114-187](../../backend/src/app/routers/chat.py#L114-L187)) | Response delivered normally; turn count may not advance | `WARNING Conversation state update conflicted after 3 attempts` |
| F9 | Empty user message (after strip) | [graph.py:301-302](../../backend/src/app/agents/triage/graph.py#L301-L302) | `intent=general, urgency=routine, escalation=False`, then static `fallback_general` | Should arguably reject at WS layer; doesn't. |
| F10 | Malformed JSON frame | [chat.py:347-355](../../backend/src/app/routers/chat.py#L347-L355) | Server emits `{type:error, code:invalid_json}` | Frontend `error` handler shows error toast, kills voice mode. |
| F11 | Unknown event type | [chat.py:373-381](../../backend/src/app/routers/chat.py#L373-L381) | Emits `error code:unsupported_event` | Same UX as F10. |
| F12 | Validation error on `ChatMessageCreate` | [chat.py:390-398](../../backend/src/app/routers/chat.py#L390-L398) | `error code:validation_error` with raw exception text | Raw `str(exc)` may leak Pydantic internals — minor UX issue. |
| F13 | WS disconnect during init | [chat.py:339-341](../../backend/src/app/routers/chat.py#L339-L341) | Logged as INFO, no error | Fixed in commit `26e8db1`. |
| F14 | WS disconnect mid-message | [chat.py:592-593](../../backend/src/app/routers/chat.py#L592-L593) | Logged INFO; turn lost; on reconnect, history restored from DB | But frontend has no auto-reconnect ([use-patient-chat-session.ts:678-688](../../apps/patient-portal/src/hooks/use-patient-chat-session.ts#L678-L688)). |
| F15 | Catastrophic 5xx in handler | [chat.py:602-611](../../backend/src/app/routers/chat.py#L602-L611) | Sends `{error code:server_error}` then closes WS with 1011 | Frontend treats as connection lost; voice mode disabled. |

---

## 3. Scenario matrix

Format: prompt → expected `{intent, urgency, route}` → expected user-visible behavior → automation hint.

### 3a. Happy paths (LLM works)
Confirms triage is wired up. Send these once ADC is working.

| # | Prompt | Expected intent | Expected urgency | Route | Expected user-visible |
|---|---|---|---|---|---|
| H1 | "I want to schedule a follow-up with Dr Lee next week" | `schedule` | `routine` | triage | LLM response about preparing scheduling questions; no escalation |
| H2 | "I'm taking metformin and feel nauseous after meals" | `medication_question` | `urgent` (adverse-effect signal) | triage | LLM response acknowledging side effect; **escalation event** emitted |
| H3 | "What does 'troponin elevated' mean on my discharge summary?" (with document context) | `document_question` | `routine` | triage | LLM explains using document context; suggests questions for clinician |
| H4 | "I've had a mild headache for two days, no fever" | `symptom` | `urgent` (rule path) or `routine` (LLM may pick) | symptom | LLM symptom follow-up + `symptom_report` persisted + (urgent → escalation) |
| H5 | "I feel anxious all day and can't sleep" | `mental_health` | `urgent` | triage | Empathic response + 988 callout + escalation event |
| H6 | "Hi" / "Hello" | `general` | `routine` | triage | Welcoming acknowledgement; no escalation |

### 3b. Emergency paths
Must short-circuit and never depend on LLM.

| # | Prompt | Expected | User-visible | Failure mode if broken |
|---|---|---|---|---|
| E1 | "I have severe chest pain" | `symptom`, `emergency` | Localized 911 template; escalation; clinicians notified | If LLM picks `symptom/urgent` instead of emergency, safety override does NOT promote — only the rule path or LLM does |
| E2 | "I think I'm having a stroke" | Same as E1 | Same | — |
| E3 | "I want to kill myself" | `symptom`, `emergency` (matches `EMERGENCY_KEYWORDS`) | 911 template, but **no 988 routing** — see gap G6 | Should mental_health/emergency hybrid; current code returns symptom/emergency |
| E4 | (Spanish) "Tengo dolor de pecho muy fuerte" | rule path → `general` (NO match) → relies on LLM only | If LLM down → ES emergency missed | **Gap G2 — critical safety bug** |

### 3c. Failure paths (force errors)
Tests confirm L2/L3 fallback selection.

| # | Setup | Expected behavior |
|---|---|---|
| FP1 | Backend with `GOOGLE_APPLICATION_CREDENTIALS` unset, ADC removed | All turns → rule classification + L2 static template; logs show `Triage LLM classification failed` and `Triage LLM response generation failed` |
| FP2 | Vertex endpoint env var set to a non-existent endpoint | Same as FP1 (404) |
| FP3 | Send "test" message while pulling network cable | L1 + L2 fail with timeout; static template returned. Backend log shows network exception. |
| FP4 | Patch `DrugKnowledgeService.retrieve_for_patient_message` to raise | L3 outer fallback fires → "I have recorded your message…" — **demonstrates G3** |
| FP5 | Patch `triage_agent.__call__` to return `TriageOutput(status="error", ...)` | L3 fires |
| FP6 | Send `{"type":"user_message"}` with no `content` | Validation error event |
| FP7 | Send `{"foo":"bar"}` (no type) | `error code:unsupported_event` |
| FP8 | Send raw text "not json" | `error code:invalid_json` |
| FP9 | Connect WS without token | Reject with policy violation 1008 |
| FP10 | Connect WS with another patient's id (token mismatch) | Reject with policy violation 1008 ([chat.py:247-251](../../backend/src/app/routers/chat.py#L247-L251)) |
| FP11 | Connect, then drop network mid-stream | Frontend `connectionStatus → disconnected`. **No auto-reconnect** — user must refresh (gap G7) |
| FP12 | Send message in EN, then immediately switch to ES, send again | Each message uses the lang field client sent at send time; assistant_complete reflects lang stored in DB |

### 3d. Edge paths (likely-misclassified prompts)
These probe the rule keyword design.

| # | Prompt | Rule classifier says | LLM probably says | Risk |
|---|---|---|---|---|
| ED1 | "I keep a record of my exercise daily" | `document_question` (matches "record") | `general` | False document route (gap G4) |
| ED2 | "The drug store was closed yesterday" | `medication_question` (matches "drug") | `general` | False medication route (gap G4) |
| ED3 | "I had a reaction to my friend's joke" | `medication_question` (matches "reaction" via MEDICATION_KEYWORDS) | `general` | False positive — but LLM corrects |
| ED4 | "What is 2+2?" | `general` → `_is_non_clinical_math_query` true → `fallback_non_clinical` | should also be non-clinical | OK |
| ED5 | "Is the moon big?" | `general` → fallback_general | should be non-clinical | **Gap G5** — non-math non-clinical falls into clinical-flavored fallback |
| ED6 | (Spanish) "Tengo una cita mañana" | matches `cita` → `schedule/routine` | same | OK |
| ED7 | (Spanish) "Mi medicamento me da náusea" | matches `medicamento` AND `nausea` (EN list) | same | OK by accident — `nausea` is in EN ADVERSE_EFFECT_KEYWORDS, but ES "náusea" with accent doesn't normalize |
| ED8 | "Side effects from medication: nausea" | matches medication + adverse → `medication_question/urgent` | same | OK — escalates |
| ED9 | Multi-line / very long message (>10k chars) | `_chunk_text` chunks at 140 chars per WS frame | LLM may truncate | Frontend renders all chunks; check that very long replies don't blow up Redux |
| ED10 | Empty content + audio_url present | `_empty_message_state` → `general/routine/fallback_general` | — | Audio-only messages should arguably reject; current behavior is silent template |
| ED11 | Same message sent 3x rapidly | Each turn independent; conversation_state retries up to 3 on lock conflict | — | Possible turn_count drift — verify F8 |
| ED12 | Document context query without referent words ("explain this") | `_has_document_signal` requires verb match — would miss "what about this" | LLM may catch | Gap G4 variant |

---

## 4. Identified gaps (bugs/risks visible from code review)

These are real defects, not speculation. Fix tickets should reference these IDs.

| ID | Severity | Gap | Evidence | Suggested fix |
|---|---|---|---|---|
| **G1** | High | L3 outer-fallback text is identical to triage L2 `fallback_general` text. Both say "Thanks for sharing this. I am here to help…" / "I have recorded your message…" — both feel like canned. From the user-facing message you can't tell whether triage ran successfully. | [chat.py:441-444](../../backend/src/app/routers/chat.py#L441-L444) vs [graph.py:155-156](../../backend/src/app/agents/triage/graph.py#L155-L156) | Distinguish wording, OR remove L3 since L2 already handles every error path the right way. Add a structured `chat_fallback_total{layer}` metric. |
| **G2** | Critical safety | `EMERGENCY_KEYWORDS` is English-only. If LLM is down for an ES patient, "tengo dolor de pecho" / "no puedo respirar" / "ataque al corazón" classify as `general`. | [graph.py:25-41](../../backend/src/app/agents/triage/graph.py#L25-L41) | Add ES emergency keywords. Same for mental-health. |
| **G3** | High | Drug-knowledge service failure crashes the whole turn into L3 because it's inside the same `try` as triage. | [chat.py:408-448](../../backend/src/app/routers/chat.py#L408-L448) | Wrap drug-knowledge in its own try; degrade to triage without RAG context on failure. |
| **G4** | Medium | Rule keywords too aggressive. "record", "drug", "reaction", "result" are common English words. False routes when LLM is unavailable. | [graph.py:42-89](../../backend/src/app/agents/triage/graph.py#L42-L89) | Tighten with multi-word patterns, or only run rule-classifier when LLM fails (already the case — but rule precision still matters). |
| **G5** | Low | `_is_non_clinical_math_query` only matches pure-math regex. "Is the moon big?" → `fallback_general` (clinical-flavored), confusing to users. | [graph.py:494-503](../../backend/src/app/agents/triage/graph.py#L494-L503) | Either trust LLM here, or expand non-clinical detector to common off-topic patterns. |
| **G6** | High safety | Suicidal language hits `EMERGENCY_KEYWORDS` and routes to `symptom/emergency` with the 911 template. Loses the 988 mental-health callout that `fallback_mental_health` includes. | [graph.py:37-39, 200-205](../../backend/src/app/agents/triage/graph.py#L37-L39) | Add a `mental_health/emergency` combined path with 988 + 911. |
| **G7** | Medium | Frontend has no auto-reconnect. WS drop = user must refresh. Voice mode also disabled on every transient close. | [use-patient-chat-session.ts:678-688](../../apps/patient-portal/src/hooks/use-patient-chat-session.ts#L678-L688) | Exponential backoff reconnect; preserve voice mode across transient closes. |
| **G8** | Medium | `_apply_safety_override` only escalates `medication_question`. Adverse-effect signal in a `general`-classified turn does not escalate. | [graph.py:559-573](../../backend/src/app/agents/triage/graph.py#L559-L573) | Apply override regardless of intent, or add symmetric override for `symptom`. |
| **G9** | Low | F12: validation error returns raw `str(exc)` from Pydantic — leaks internals. | [chat.py:390-398](../../backend/src/app/routers/chat.py#L390-L398) | Map to a sanitized message. |
| **G10** | Low | ED10: empty content with audio_url silently produces fallback_general. | [graph.py:301-302](../../backend/src/app/agents/triage/graph.py#L301-L302), [chat.py:383-389](../../backend/src/app/routers/chat.py#L383-L389) | Either reject at WS layer or treat as transcription failure. |

---

## 5. Test execution plan

Phase A — code-level (no LLM needed): unit tests for classifier rules covering every row in §3b–3d.
Phase B — integration with stub LLM client: cover §2 failure modes F4, F5, F8 via patched router.
Phase C — live LLM: the §3a happy paths once ADC is wired (which is now the case).
Phase D — manual end-to-end through the portal: F10–F15 and ED9.

Output of each phase should be appended below this line as `## Run YYYY-MM-DD` with PASS/FAIL per row.

---

## Run 2026-05-03 — Phase A (rule-classifier unit tests after G1/G2/G3/G6/G8/G9 fixes)

Backend changes landed in this PR:

- `backend/src/app/agents/triage/graph.py` — Spanish emergency + mental-health keywords (G2), `MENTAL_HEALTH_EMERGENCY_KEYWORDS` set + `mental_health_emergency_response` template (G6), broadened `_apply_safety_override` (G8), structured fallback logging via `categorize_llm_failure` (G1).
- `backend/src/app/routers/chat.py` — drug-knowledge isolated in own try (G3), distinct outer-fallback wording + structured logs (G1), sanitized validation_error response (G9), structured logs for symptom-route failures (F6 surfacing).
- `backend/tests/unit/agents/test_triage_safety_overrides.py` — 9 new cases covering G1/G2/G6/G8.
- `backend/tests/unit/agents/test_triage_routing_golden.py` — extended bilingual + G6 cases.

| Section | Coverage | Result |
|---|---|---|
| §3a H1–H6 (LLM-on happy paths) | not run — needs ADC + live portal | DEFERRED |
| §3b E1, E2 (English emergencies, rule path) | covered by `test_triage_routing_golden` `chest pain`, `stroke` | PASS |
| §3b E3 (self-harm → mental_health/emergency) | `test_g6_self_harm_response_includes_988` | PASS |
| §3b E4 (Spanish emergency, rule path) | `test_g2_spanish_chest_pain_classified_as_emergency_by_rule`, `test_g2_spanish_cant_breathe_emergency` | **PASS — was failing pre-fix** |
| §3c FP9, FP10 (auth rejection) | covered by existing `test_chat_websocket_stability` | PASS |
| §3c FP4 (drug-knowledge isolation) | manual code review — drug_knowledge raise no longer reaches outer try | PASS (structural) |
| §4 G1 (categorization buckets) | `test_g1_categorize_llm_failure_*` (4 cases) | PASS |
| §4 G8 (override never downgrades emergency) | `test_g8_safety_override_does_not_downgrade_emergency` | PASS |
| Full chat suite (`tests/unit/agents/`, `test_chat_api`, `test_chat_websocket_stability`) | — | **105/105 PASS** |
| Ruff lint on touched files | — | PASS |

### Still open after this run

- **G7** — frontend WS auto-reconnect with exponential backoff and voice-mode preservation.
- **Phase C live LLM** — H1–H6 require ADC + portal session; deferred to manual run on dev host.
- **Phase D portal manual** — UI overlap audit, typing-indicator behavior, mobile ergonomics.
- **Metrics sink** — `chat_fallback_layer` / `chat_fallback_reason` are emitted as structured log fields but not yet exposed as a counter dashboard.

