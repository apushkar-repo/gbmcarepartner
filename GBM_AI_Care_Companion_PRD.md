# GBM CareBridge — Product Requirements Document

Version 2.0 · Final hackathon scope · 12 September 2026

This revision supersedes the earlier broad GBM AI Care Companion MVP. Existing filenames are retained for continuity. “Final” refers to the agreed design scope, not a validated or deployed clinical product.

## 1. Use case and pitch

**Turn a handwritten doctor's patient summary into an understandable visit record, a saved question list, and an approved preparation plan for the next appointment.**

The patient or authorized care partner uploads a photograph or scan. CareBridge extracts today's summary, written recommendations and next appointment details, asks for verification where needed, and preserves the original evidence. The user can ask questions across past summaries, save questions for the next visit, and approve preparation reminders. A bounded orchestrator coordinates these steps and responds to missing information, conflicting dates and changes in permission.

Demo promise: **Understand the summary. Capture your questions. Prepare for the visit. Remember the next step.**

Audience: hackathon judges and prospective implementation partners. Primary user: patient and authorized care partner. Clinical navigator: future pilot collaborator and clinical-content reviewer. The demo uses fictional data and simulated notification delivery. No clinical efficacy or production-readiness claim is made.

## 2. Problem and outcome

The initiating artifact is a handwritten patient summary containing today's observations, recommendations and the next appointment date. Reading, remembering and acting on it requires several manual steps. Details can be illegible, missing or inconsistent with earlier documents. Questions raised at home can be forgotten by the next visit.

CareBridge provides one persistent preparation workspace. It distinguishes what was written, what was extracted, what the user confirmed, what remains uncertain and what the app proposes. The target benefit is less preparation effort and fewer forgotten questions or unresolved logistics items. Validate those hypotheses against manual preparation and a single-pass RAG summary on the same scenarios.

## 3. Scope and non-goals

| Included in the hackathon | Deferred or excluded |
|---|---|
| Photo/scan upload, quality checks, handwriting transcription and structured extraction | Production EHR or portal integration |
| Side-by-side source review and correction history | Autonomous interpretation of ambiguous clinical instructions |
| Historical RAG over authorized summaries with source citations | Open-web medical answering, diagnosis, prognosis or scan interpretation |
| Saved and editable next-visit questions | Treatment selection, dose calculations or medication/treatment reminders |
| Evidence-linked preparation checklist and approved reminders | Autonomous clinician/family messages, calendar booking or emergency contact |
| Persistent workflow state, simulated delivery, cancellation and rescheduling | Broad family-update, resource-navigation and trial features |
| Evals, synthetic fixtures, trace viewer and safety demonstration | Claims of clinical validation from synthetic testing |

The original Phase 1/2/3 workbook names remain. Their scope now means: Phase 1 proves document understanding and historical RAG; Phase 2 proves questions and preparation; Phase 3 proves bounded orchestration and reminder lifecycle. Implement these as one vertical demo, not three broad product releases.

## 4. Roles and permissions

| Role | Allowed capability |
|---|---|
| Patient | Review records, correct transcription, manage sharing, save questions and approve actions |
| Authorized care partner | Work only within granted document/action scope; can approve reminders only if that capability was explicitly delegated |
| Logistics helper | See only separately approved task fields; no access to summary documents or their metadata by default |
| Clinical reviewer | Review fictional content and eval expectations; later access only via a separately authorized clinical workflow |

Consent is versioned and revocable. Verify patient/document identity before indexing. Names alone do not prove identity. Ambiguous or mismatched identity is quarantined for review. Approval does not grant new recipient or record permissions.

## 5. Primary flow

1. **Capture:** select the patient workspace; upload all pages; validate type, image integrity, cropping, orientation and legibility; keep the immutable original.
2. **Read:** run handwriting/OCR extraction; produce text spans with page and bounding box; preserve strikeouts, uncertainty and original wording.
3. **Structure:** extract today's visit date and summary, each written recommendation, and appointment date/time/location. Missing fields stay null. Preserve authored, visit and ingestion dates separately.
4. **Verify:** show critical fields next to source crops. User may confirm transcription, correct it, mark unreadable or provide separately labeled information. Unclear clinical meaning becomes a care-team question. Confidence scores alone cannot authorize action.
5. **Understand:** provide a plain-language summary of confirmed record facts and labeled uncertainties. Historical RAG answers questions across authorized versions and cites exact sources.
6. **Capture questions:** user saves an answer-derived or original question, edits wording, and assigns it to the next visit or leaves it unassigned. Keep the source claim and original question lineage.
7. **Prepare:** orchestrator combines saved questions, verified appointment information and explicit recommendations into a short checklist. Separate doctor-written instructions, user requests and app suggestions.
8. **Approve reminders:** preview task, schedule, timezone, channel and recipient. User selects timing and approves the exact version. A date-only appointment can support a user-selected preparation time on a prior day; the app must not invent the appointment time.
9. **Track:** simulated scheduler returns a receipt. Scheduled, delivery attempted, delivered and task completed remain distinct. Completion requires authorized confirmation.
10. **Respond to change:** a new record, correction, appointment change or revocation invalidates affected assumptions. Pause unsafe pending reminders, show the difference and seek renewed approval before replacement activation.

Urgent-language requests interrupt the ordinary workflow using a pre-approved safety route. They do not wait for OCR, retrieval or reminder review, and do not trigger autonomous emergency contact.

## 6. Experience design

| Screen | Main content | Primary action | Failure or uncertainty state |
|---|---|---|---|
| Home / Next visit | Confirmed date or “Date needs confirmation”; open questions; pending prep | Upload summary / Prepare for visit | Never display a clinical readiness score |
| Capture | Page thumbnails, orientation and quality feedback | Retake / Upload | Explain which page/region cannot be read |
| Review summary | Original crop beside editable extracted field; provenance and status | Confirm / Correct / Mark unreadable | Do not preselect an uncertain date |
| Ask past summaries | Question, cited answer, source date, scope/date filter | Open source / Save a visit question | “Not found in available summaries”; preserve conflicts |
| Visit preparation | Up to five visible priorities, with expandable remaining questions/tasks | Edit questions / Review reminders | Show blocked items and exact missing prerequisite |
| Reminder review | Exact task, schedule, timezone, recipient and simulated channel | Approve / Edit / Cancel | Activation disabled when required fields or permissions are unresolved |
| Activity / Evidence | Source versions, corrections, approvals, delivery and completion states | Inspect source / Confirm task completion | Pending acknowledgement or delivery failure is visible |

Use large text, plain language, keyboard support, clear focus order and progressive disclosure. Status must use words as well as color. “User-confirmed transcription” must not be displayed as “clinician confirmed.”

## 7. Functional requirements and acceptance

| ID | Requirement | Acceptance example |
|---|---|---|
| FR-01 | Authenticate, bind workspace and authorize before every retrieval, citation and action | A logistics helper cannot retrieve a private summary or infer its title |
| FR-02 | Preserve originals, page coordinates, extraction versions and correction history | A source crop opens from an extracted date in two interactions or fewer |
| FR-03 | Extract the three primary sections independently | Missing appointment does not suppress today's summary; missing year stays unknown |
| FR-04 | Separate field confidence, verification status and clinical authority | High-confidence OCR still requires review for action-driving fields |
| FR-05 | Keep uncertain text out of authoritative facts and automatic actions | Ambiguous 8/9 date cannot activate an appointment-relative reminder |
| FR-06 | Historical RAG answers only with authorized evidence | A stated change cites both dated sources or explicit source wording describing a change |
| FR-07 | Save question text, author, source links, target visit and status | Editing the question preserves lineage; no duplicate from a retried save |
| FR-08 | Keep doctor recommendations distinct from app proposals | “Bring reports” is source-linked; “two days before” is labeled user-selected/app-proposed |
| FR-09 | Draft tasks only from supported instructions or explicit user requests | Missing time creates a confirmation question, not a fabricated time |
| FR-10 | Bind reminder approval to exact payload, schedule, source version and consent | An edit after approval invalidates the approval |
| FR-11 | Handle local timezone, daylight-saving changes, date-only events and past times | Nonexistent local time prompts correction; past reminder time is not silently scheduled |
| FR-12 | Support cancellation, snooze and appointment updates | Cancellation stops pending delivery; changed date requires reapproval of revised timing |
| FR-13 | Execute idempotently and reconcile ambiguous delivery results | Timeout followed by status lookup produces one reminder, not two |
| FR-14 | Gate every send on live permissions and reminder version | Revocation after scheduling blocks the pending notification |
| FR-15 | Keep completion and question status human-controlled | Delivery does not complete a task; a new summary does not automatically answer saved questions |
| FR-16 | Record reconstructable observable traces and versions | Reviewer sees source IDs, tools, validation, approval, outcome and stop reason |

## 8. Orchestrator design

One orchestrator selects allowed steps based on workflow state. Specialist functions can share a model. Deterministic services own permissions, schema validation, approval checks and delivery. The model cannot create its own tools or change policy.

| Function | Inputs | Output / tool boundary |
|---|---|---|
| Document understanding | Authorized image pages and extraction schema | Text spans, fields and uncertainty; no task activation |
| Evidence / RAG | Authorized reviewed summaries, structured metadata and optional current approved education | Claim-to-source map; no new patient facts from general education |
| Preparation planner | Reviewed fields, question list, explicit user preferences | Draft checklist and reminder proposals |
| Verifier | Draft, source map, verification status and policy | Accept, revise once, ask, or stop; cannot override deterministic denials |
| Action gateway | Exact approved payload and current policy | One idempotent scheduler action and receipt |

Initial bounds: 12 tool calls, two targeted retrieval refinements, one draft revision, and 60 seconds active computation per execution. Human review is a durable waiting state. Return a safe partial result when budget is exhausted. Do not run an indefinite agent loop while awaiting a person.

## 9. RAG and data rules

The patient summary corpus is the core. Optional institution and general education corpora remain separate, audience-filtered and governed. Public web search is not an application tool in the demo.

Store an immutable original, raw extracted text, corrected text, verification state, page/bounding box, source version and access scope. Reviewed text is the default historical answer source. Unverified text may appear only in a clearly labeled review experience and cannot drive reminder creation. User-supplied appointment information may be used after explicit confirmation with a distinct provenance label.

Filter authorization and source status before retrieving candidates; hybrid lexical/semantic retrieval and reranking operate only on permitted content. Fetch exact dates, questions and reminder states from structured storage. Label retrieved passages as data, never as instructions. Cite supported claims and verify entailment. Missing evidence produces a scoped abstention. Newness alone does not resolve conflicts; explicit supersession or separately recorded confirmation is required.

Corrections produce new versions, invalidate affected derived claims and pending actions, and refresh indexes. Older versions remain auditable but are not silently mixed into current answers. Revocation covers snippets, cached answers, citations, crops and notification previews.

## 10. State and reminder contract

Document: received → quality review / extracted → awaiting verification → reviewed → indexed. Unreadable or wrong-patient documents remain quarantined. Clinical ambiguity can remain unresolved even when other fields are reviewed.

Question: open → discussed → follow-up needed or resolved, with an authorized user recording the transition. Appointment reassignment retains the original linkage and history.

Reminder: draft → awaiting approval → scheduled → delivery attempted → delivered / failed. Alternative states: paused, cancelled, awaiting reapproval. Task completion is a separate field with confirmer, timestamp and evidence. Retrying must reuse the idempotency key; query status after an uncertain result before attempting another send.

Minimum reminder payload: reminder ID, patient/workspace, task ID, source/version references, appointment ID/version when applicable, exact text, owner/recipient, channel, local schedule, IANA timezone, UTC timestamp, approver, consent version, approval hash, expiry and idempotency key. Never place diagnosis or clinical detail in a lock-screen preview by default.

Date-only appointments require a separately chosen preparation reminder time and timezone. Relative intervals from handwriting cannot be converted without a confirmed reference date and a user-reviewed derived date. Missing year, ambiguous date format and daylight-saving gaps require clarification. If a proposed reminder time has passed, offer a new time for approval.

## 11. Guardrails

- Never diagnose, interpret scans, choose treatment, resolve medication conflicts, or create medication/treatment reminders in this scope.
- Preserve clinical wording and uncertainty. User correction confirms transcription, not clinical correctness; ambiguous clinical instructions go to the care team.
- Enforce identity and permissions outside the model before context and action. A source document cannot authorize sharing or tools.
- Critical extracted fields require review regardless of model confidence. No fabricated date, year, time, location, recommendation or completion state.
- Reminder activation requires explicit approval; send-time checks prevent stale, revoked or cancelled deliveries. Stop pending unsafe sends immediately; obtain fresh approval before changed reminders activate.
- Use approved urgent-language handling independently of routine preparation. No diagnostic inference or autonomous emergency dispatch.
- Provide cancellation, audit trace, workflow disablement, scoped retention, encrypted storage and permission-aware logs. These are design requirements, not implemented certifications.

## 12. Evaluation and datasets

The final starter dataset contains 36 synthetic text-based fixtures and 36 paired specifications: the original 12 workflow seeds plus 24 new handwriting-review, RAG, question and reminder scenarios. These are fixture-level tests, not actual handwriting images or a validated OCR benchmark. All application runs remain Not Run.

The workbooks retain 36 original regression definitions and add 24 final-scope cases (60 definitions total). New cases map directly to CB2-F01 through CB2-F24. The 12 original JSONL seeds remain complementary developer tests. Legacy workbook fixture gaps stay visible. Dashboard readiness must not imply those gaps are filled.

Proposed engineering targets: ≥98% exact match on readable critical extraction fields, 100% correct withholding of action on designated ambiguous fields, ≥95% evidence Recall@5, 100% patient-claim citation coverage, ≥98% citation support, zero privacy leaks/unapproved actions/duplicate effects/false task closure in the designated test suite. Every required case must be completed and adjudicated; critical failures block regardless of averages. Targets are not achieved results or clinical release criteria.

Use source span/field assertions and deterministic trace checks for permissions, dates, approval and scheduling. Human reviewers assess transcription against original images, clinical ambiguity, semantic grounding and usability; a model grader is supplementary. Record sample sizes, repeated-run variability and confidence intervals. Keep gold labels outside model context.

Expansion: 200 fictional episode families, 4–8 summaries each, five role/workflow variants. Split 120/40/40 by family and template lineage into development/validation/held-out; keep paraphrases together. Add genuine human-written fictional summaries from consenting writers, photographed with varied devices and adjudicated at word/field/region level. Keep acquisition consent separate from fictional patient data. No real PHI is needed. Assess OCR on actual images before making any handwriting-performance claim.

## 13. Demo and build order

Build one vertical workflow in this order: source schema and fixtures; upload/extraction/review; historical RAG and question persistence; preparation planner; approval and mock scheduler; correction/revocation/retry handling; trace and eval display.

Five-minute demo: upload a fictional summary; verify a date; ask about an earlier summary and inspect its citation; save an edited question; approve a preparation reminder; introduce ambiguous handwriting or a changed appointment; show the affected reminder safely paused; display the corresponding eval case and actual outcome only if executed.

Success hypotheses: users retrieve the correct historical instruction, retain their questions, and reduce preparation effort without added material errors or excessive review. Measure time, omissions, corrections and reviewer burden against manual and single-pass RAG baselines. Defer a clinical pilot until partner-led clinical, privacy and security review.

## 14. Deliverable map

Architecture document: system, flow, state, RAG and reminder contracts. Proposal: hackathon pitch and demo storyboard. Two evaluation workbooks: original cases plus final additions and corrected build-scoped dashboards. JSONL: fictional fixtures and expected behavior. README and change log: inventory, scope and validation limitations. All deliverables use version 2.0.
