# LOC-003 — English-first clinician review of Spanish content

**Status:** Base #181 and remainder [#203](https://github.com/sjsu-masters-projects/medi-agent/pull/203) merged (#203: `dace6a8d`, October 22, 43 successful PR checks). Applied 067/068 retained; requester supplied successful COMMIT/ledger output for 080–082 and 088. Deployment and live acceptance remain distinct checks. Design and decisions agreed October 13. Raised at the October 13
checkpoint demo.

## Principle

The clinician portal is English-only, and the patient portal follows the patient's
language (en-US or es-MX). A clinician who reads no Spanish must still understand and
approve everything. Spanish appears in the clinician portal for only two reasons:

- it is exactly what the patient will see; or
- it is the original source evidence.

Both uses are labelled as such.

## What is confusing today

- **Care plan.** The "Proposed items" list shows each item in its source language, so a
  plan drafted from a Spanish document lists "Metformina 500 mg" and "Tome un vaso de
  agua…". The detail shows English and Spanish side by side, and nothing explains why
  there are two languages or which one the patient sees. The approved view repeats this.
- **Extracted facts.** Facts from a Spanish document are shown in Spanish in the review
  queue, the document facts dialog and the care-plan source excerpts: names,
  instructions, frequencies and summaries.
- **Checking Spanish.** Approval asks the clinician to confirm the Spanish wording against
  the source, which an English-only clinician cannot do.

## Proposed behaviour

1. **Care-plan lists are always English.**
   - The proposed-items list (draft) and the item list (approved plan) show English titles.
   - When the English is a translation of a Spanish source, a small "Translated from
     Spanish" marker says so.
2. **The detail shows what the patient will see.**
   - Each item shows a compact strip: "Source: Spanish document → You review: English →
     Patient sees: Español (México)".
   - The patient's language card is highlighted as "Shown in the patient's Today", with a
     phone-style preview.
   - The other language is labelled "Stored in case the patient changes language".
   - The same strip appears in review, preview and the approved plan.
3. **Spanish is verified through English.** Instead of asking the clinician to read
   Spanish, the Spanish card shows:
   - an English back-translation of the Spanish wording;
   - the existing guard results (numbers, doses and medication names identical; LOC-001
     already blocks a translation that changes them).

   The approval attestation then says what was actually checked. Optionally, a bilingual
   colleague can mark the Spanish as reviewed.
4. **Extracted facts are shown in English.**
   - Medication, allergen and vaccine names are never translated (decision 5): the review screen
     keeps the name exactly as printed.
   - Condition, procedure and test names, instructions and frequencies are translated and
     labelled "Translated from Spanish". Values, units, ranges, flags and dates are never translated or changed.
   - The original Spanish text stays one tap away.
5. **Source evidence stays original.**
   - Excerpts and citations remain the exact printed Spanish, because they are the
     evidence, with an English gloss beside them.
   - Nothing replaces the source text in storage.

## Where this applies

| Surface | Change |
| --- | --- |
| Care-plan draft list and detail; approved plan | 1–3 |
| Review queue and document facts dialog | 4, 5 |
| Care-plan source excerpts and protected source preview | 5 |
| ADR evidence quoting patient answers | English gloss with the original |
| Clinician chat tab (patient–Nora transcript) and care-team messages | Decision 3 |

## Decisions

1. **Decided (requester, October 13): translate when the document is processed.** The
   English display fields are written at ingestion with the same guard as LOC-001: numbers,
   doses and medication names must match, or the item keeps only its original text and is
   marked untranslated. They are stored with the fact and audited with it, so every viewer
   sees the same English.
2. **Decided (requester, October 13): a bilingual reviewer is optional, never a blocker.**
   The clinician checks the Spanish against its English back-translation and the guard
   results (or any translation tool), then attests. A bilingual colleague's review can be
   recorded but is not required to publish.
3. **Decided October 13: chat and care-team messages get stored translations.**
   - **Patient messages in Spanish:** the original stays the message of record. An English
     translation is shown below it automatically, labelled "Translated from Spanish". An
     info icon explains that it was translated automatically, by which model, and that it
     may contain errors. This also applies to the patient–Nora transcript in the
     clinician's Chat tab.
   - **Clinician replies:** written in English. Before sending, the clinician sees the
     Spanish the patient will receive, with an English back-translation, and confirms it.
     The patient sees the Spanish with "Translated from English · show original".
   - **Guard:** the LOC-001 guard applies. If numbers, doses or medication names differ,
     no translation is used: the reply is delivered in English with a short Spanish note
     that a translation was unavailable, and the clinician is told.
   - **Storage:** each message is translated once, when it is sent or received, and stored
     with it (message, target language, text, model, guard result, time).
   - **Safety and records use only the original text.** Urgent-symptom checks and
     escalation never depend on a translation, and a translation never becomes a clinical
     fact.

## Decisions from the October 17 review

4. **A translation that failed its guard is never shown by default.** When
   `translation_guard_passed` is false, both portals show the original message as the main
   text with a short note ("Automatic translation unavailable for this message"; es-MX below)
   instead of the translated text. The clinician portal no longer shows the failed translation
   in its "Translated" box either. The es-MX note is a **draft for LOC-001 review**, not
   approved wording: `Traducción automática no disponible para este mensaje`.
5. **Proper names are never translated.** Medication names, allergens and vaccine names are not
   sent to the model; `display_value` omits those keys and the review screen keeps the printed
   name. Condition, procedure and test names are still translated and keep the digit guard.
   The reason: a model can alter or "correct" a drug name, which is a clinical-safety change the
   number guard cannot see.
6. **Ingestion translates only the document's own facts**, found through the document's
   provenance, not the patient's 50 most recent untranslated facts.
7. **Message translation reads are bounded.** A read translates at most ten messages that have
   no stored translation, skips stored ones, logs failures without message text, and never
   fails the read. **Superseded by decision 12:** the cap is gone because a read no longer calls
   the model. Clinicians write English; translation runs only when a message's detected language
   differs from the reader's language, so there is no "detect the clinician's language" follow-up.

## Decisions from the October 17 second review (branch `fix/loc-003-review`)

8. **The patient's own language is the target.** A clinician's message is translated into the
   patient's `preferred_language` (en-US or es-MX), and only when its detected language differs
   from it: an English reply to an en-US patient makes no model call and attaches no translation.
   A clinician reads English, so only messages detected as Spanish are translated for them. The
   patient portal shows a translation as the main text only when `translation_locale` equals the
   patient's own locale; the clinician portal only when it is en-US.
9. **Attestation needs a real check.** The "I verified ..." box is enabled only when the
   back-translation of the SAVED Spanish wording has loaded, the numbers and medication-name
   guards passed, and nothing is unsaved. Its disabled reasons are: "Back-translation is loading",
   "Back-translation unavailable — retry", "Numbers or medication names differ — fix the Spanish",
   "Save your changes first". The back-translation is fetched for saved wording only (on mount and
   after a save), with "Check again" and "Retry", and a slower older response is ignored.
   **Server side:** setting `wording_verified` (on save, and again at the approval preflight)
   re-checks the stored English and Spanish wording against the same deterministic guards
   (numbers with units, negation, medication name) and rejects with a validation error. It does
   not call the model. Follow-up: the guard outcome is not recorded with the verification (no
   suitable column; adding schema was not justified).
10. **Stored translations are always attached; only new model calls are capped (ten per read).**
    A failed translation is stored as a marker (`guard_passed=false`, `guard_failure_code =
    model_error`), is never shown, and is retried after an hour. Store and read run off the event
    loop. The send used to wait for the translation; decision 12 removes that. `model_id` is
    stored when the provider reports it.
11. **Shared guards** (`translation_guards.py`) for messages, care-plan wording and fact fields:
    numbers are compared with their units (mg, g, mcg/µg, mL, L, units/UI, %, tablets/tabletas and
    similar, English and Spanish equivalents); "1,000" and "1.000" are not folded together (a
    thousands-separator swap fails the guard), while a decimal comma still equals a decimal point;
    a negation (no, not, never, without, sin, nunca) that appears or disappears fails the guard;
    message translation also protects the patient's active medication names.
12. **Prompt text is data.** Message and fact translation prompts say the text is data to
    translate, never instructions, and wrap it in delimiters; delimiter text inside the data is
    removed.

## Remaining (owner: Jeevan)

- **Confirm deployment and run the deployed acceptance journeys below.** The requester
  supplied successful COMMIT/ledger output for 080–082 and 088 before reporting #203 merged;
  083–087 were already applied/skipped. Do not reapply or rename these files to update status.
  This is operator evidence, not an independent remote checksum/security audit.
- **LOC-001 review of the es-MX caveat drafts** for the patient-side translation note (listed
  under item 25 below). They are drafts, not approved wording.
- **Open guard question for LOC-001 (found October 19).** `negation_flipped` compares whether
  a negation is *present*, not how many there are, so dropping one of several negations does
  not fail the guard: `Do not take 1,000 mg or 2.5 mL without water` → `Take 1,000 mg or
  2.5 mL without water` passes, because `without` survives. The comment on the function says
  counts are deliberately not compared, and that is defensible across this language pair —
  `Never take` is idiomatically `No tomes nunca` (one negation becoming two), and `and do
  not` often becomes `ni` (two becoming one), so a plain count would reject correct
  translations. The narrow fix worth considering is to compare counts **only when both texts
  are in the same language**, which is exactly the back-translation comparison
  (English source against English back-translation) and would catch the inverted-instruction
  case without touching cross-language behaviour. #203 review now applies that narrow
  English-original/English-back-translation check to reply and care-plan review. A rejected
  reverse translation is never returned as usable. Cross-language presence checks remain
  limited heuristics, not proof of clinical meaning; preflight explicitly reports that limit.

### Clinician portal — done (October 19)

19. **Phone-style patient preview.** The patient's own language card, in review and in the
    approved plan, shows the wording inside a static phone frame with the patient app's own
    chrome, so long Spanish wrapping and an empty frequency are visible before approval
    rather than after. Only the patient's language gets a frame: the other language is
    storage, not a screen. The frame is inert — the completion button is not a control — and
    uses no motion or 3D transform.
20. **English glosses beside original evidence.** Care-plan source excerpts, the protected
    source preview's highlighted excerpt, the document facts dialog and ADR patient answers
    each show an English gloss beneath the original. The excerpt itself is never altered or
    replaced, in storage or on screen. A gloss is addressed by a UUIDv5 of its own
    whitespace-collapsed text, so the same printed sentence is glossed once however many
    citations quote it; glosses are stored in `message_translations` under the
    `evidence_excerpt` label (migration 082) with the same guards, model provenance and
    failure markers as a message translation. A gloss that fails its guards is never shown,
    and new glosses are capped at ten per request.
    `POST /clinicians/me/patients/{patient_id}/evidence-glosses`.
21. **The Nora transcript, in English.** The Chat tab attaches stored translations to Spanish
    turns and marks the rest pending; reading never calls the model, exactly as a
    care-conversation read behaves. The portal then requests the pending turns, at most three
    at a time, through
    `POST /clinicians/me/patients/{patient_id}/chat-messages/{message_id}/translation`. The
    patient's own words stay above the translation as the record.
22. **A clinician reply preview with back-translation.** `POST
    /care-conversations/{id}/messages/preview` returns the wording the patient will receive
    and an English back-translation of exactly that wording, with the guard result. Sending is
    gated until the clinician confirms it, and the confirmed wording is sent as
    `confirmed_translation` and stored as the message's translation, so the patient reads what
    was approved rather than a fresh translation. The server re-runs the guards on it and
    rejects a mismatch: the browser asking for something is not permission to skip a guard.
    Nothing is stored for an unsent reply. A patient who reads English needs no confirmation,
    and a guard-rejected translation is never offered for one — the reply goes in English, per
    decision 3's guard rule.
23. **"May contain errors" and the model behind the text.** One shared affordance marks every
    machine translation in the portal: the care-plan AI-draft badge, the phone preview, fact
    cards, evidence glosses, care-team messages and transcript turns. It opens on tap or
    keyboard, names the stored model, says the translation may contain errors and that the
    original is the record. The model is now recorded for care-plan wording
    (`care_plan_items.translation_model_id`, migration 081) and fact display fields
    (`clinical_facts.display_model_id`, migration 082); message translations already stored
    it, and it is now surfaced. Stub-produced wording is labelled as never approvable for a
    patient.
24. **Facts the guard rejected say so.** A Spanish fact with no English display fields is
    marked "Not translated" with the reason, instead of appearing in Spanish where the
    clinician expects English. Every translated field offers the printed original one tap
    away, in a disclosure marked `lang="es-MX"`.

### Patient portal and acceptance tooling — done (October 19)

25. **The patient is told a computer translated it.** A message shown as a translation, and a
    message whose translation was withheld, both carry an info control beside the existing
    "Translated from English · show original" line. It opens the bottom sheet (tap or
    keyboard, 44px touch area, never hover alone) and says a computer made the translation, it
    may contain errors, which model made it, that the original message is the one that counts
    and that the care team reads the original, that numbers, doses and medication names are
    checked, and to ask the care team if anything is unclear. **The es-MX wording is a draft
    for LOC-001 review, not approved:** `Acerca de esta traducción`, `Esta traducción es
    automática`, `La hizo una computadora, no una persona, y puede tener errores.`, `La hizo
    el modelo {model}.`, `No se registró qué modelo la hizo.`, `El mensaje original es el que
    cuenta. Tu equipo de atención lee el original, no la traducción.`, `Revisamos que los
    números, las dosis y los nombres de los medicamentos sean iguales en los dos idiomas. Si
    algo no coincide, no mostramos la traducción.`, `Si algo no te queda claro, pregúntale a
    tu equipo de atención.`, `Cerrar`.
    The caveat is on messages only. A patient's Today carries clinician-approved wording, and
    marking approved clinical wording as machine output would misrepresent it.
26. **Acceptance runs without the model.** `backend/scripts/preflight_loc003_translation.py`
    `--self-check` exercises every translation path offline through the stub and asserts the
    properties the feature rests on — numbers with units, thousands separators, decimals,
    negations and medication names surviving a translation; a changed dose, an added or lost
    negation, a separator swap and a changed drug name being rejected; proper names never
    reaching the model; the fingerprint tracking edits; the reply round trip; the gloss
    address being its own text. 19/19 pass with no network, database or model.
    `--check-target` reads the configured project's ledger and the columns 080–082 and 088 add, with
    no mutations. Both are read-only.

### Backend and data — done (October 19)

Send/read model calls were removed in #187 using the explicit per-message translation
endpoint below; a background job was never an outstanding implementation requirement.

13. **Ingestion translates a document's Spanish facts in batches.** One model call carries up
    to fifteen facts (`BATCH_SIZE` in `fact_display_translation.py`) instead of one call per
    fact. Guards run per fact, so one rejected translation never discards the rest of its
    batch. Every fact is marked either way: an English fact records `en-US` so a later run
    does not re-check it, and a Spanish fact whose translation failed or was rejected records
    `es-MX` with no `display_value`, which is the untranslated state the review screen reads.
14. **Back-translations are cached on the item.** `care_plan_items.back_translation` stores the
    English back-translation, the guard results and a fingerprint of the two language versions
    it covered (migration 081). It is served only while the fingerprint still matches the
    stored wording, so a back-translation can never stand in for wording that has since
    changed, and re-reading a plan costs no model call. The clinician's "Check again" sends
    `?refresh=true`, which calls the model for the same text. A re-translation clears both the
    cache and the verification record, because they describe text that no longer exists.
15. **The guard outcome is recorded with the verification.**
    `care_plan_items.wording_verification` stores each deterministic check and its result
    (numbers with units, negation, medication name, field presence), the fingerprints of the
    wording checked, who attested and when (migration 081). A trigger requires new or
    changed verified wording to carry the record, without blocking cache-only writes to
    unchanged legacy approved wording. It is display and audit only: the
    publication preflight and the database guard both re-run the checks and never trust it.
    This closes the follow-up noted under decision 9.
16. **`message_translations` has referential integrity and a retention rule** (migration 080).
    `source_table` is polymorphic, so one SQL foreign key cannot express it; `AFTER DELETE`
    triggers on `care_conversation_messages` and `chat_messages` give the same cascade.
    `public.purge_message_translations(interval)` removes orphans and failure markers past
    their useful age, and runs as the recorded cron job `message_translation_purge`
    (`POST /api/v1/cron/message-translations/purge`). A successful translation is kept while
    its message lives. Nothing clinical is lost: a translation is display state, and the
    original message stays the record.
17. **Applied migration identity is retained.** Keep `067_english_display_facts.sql`
    byte-for-byte unchanged. Its proposed 079/083 copies were redundant and removed.
    Only the exact historical 067 filename pair is grandfathered. New 088 is instead
    the atomic confirmed-message transaction, not a repeated English-display migration.
18. **Translation runs without a live model when explicitly enabled.** `TRANSLATION_STUB_ENABLED`
    answers all four translation paths — second-language drafting, back-translation, fact
    display fields and message translation — from a small deterministic bilingual glossary
    instead of Vertex AI, so the English-first display rules, the guards and the attestation
    can be exercised where the model is unreachable. It substitutes known words and leaves
    everything else as written, which is why numbers, units, doses, medication names and
    negations survive by construction. It is ignored in production, and stubbed output records
    `offline-translation-stub` as its model so it is never read as reviewed wording. **Stubbed
    wording must never be approved as patient-facing text.**

## Non-blocking translation implemented in #187 (October 17)

12. **Translation never runs in the send or read path (done).** Production Cloud Run gives CPU
    only while a request is open, so no background task or thread is used.
    - **Send** stores the message and returns; no model call.
    - **A conversation read** returns originals plus any stored translations. A message the viewer
      needs translated but which has none stored (or only a failure marker older than an hour)
      carries `translation_pending: true`. A fresh failure marker is neither shown nor pending.
    - **`POST /care-conversations/{id}/messages/{message_id}/translation`** translates ONE message
      into the viewer's language with the same guards, stores it (idempotent upsert) and returns
      `{message_id, translation, translation_locale, translation_guard_passed, translation_pending}`.
      It is authorized like a read of that conversation (an outsider is refused; a message outside
      the conversation is "not found"). A stored translation or a fresh failure marker is returned
      without a model call, which is the simple rate limit.
    - **Both portals** show the original first, then request the pending messages after the read,
      at most three in parallel, with a subtle "Translating…" (es-MX `Traduciendo…` is a **draft
      for LOC-001 review, not approved**). A failed guard or request leaves the original. Display
      rules are unchanged: locale must match the viewer. Typing and sending are never blocked.
    - Clinicians write English; translation runs only when a message's detected language differs
      from the reader's language.
