# CareBridge backend

Run the API from this directory:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Copy `.env.example` to `.env` for local provider configuration. Set
`LLAMA_CLOUD_API_KEY` to enable OCR. Never commit `.env`.

Approved summaries are always indexed in the local SQLite FTS5 index for BM25
search. Semantic search is optional. To enable it:

1. Create a Pinecone dense-vector index whose dimensions match the configured
   OpenAI embedding model.
2. Set `OPENAI_API_KEY`, `PINECONE_API_KEY`, and either
   `PINECONE_INDEX_HOST` (preferred) or `PINECONE_INDEX` in `.env`.
3. Keep `OPENAI_EMBEDDING_MODEL=text-embedding-3-small`, or change it to the
   model used by the Pinecone index. Set `OPENAI_EMBEDDING_DIMENSIONS` to the
   Pinecone index dimension; the checked-in example uses 1536.

The API chunks approved summary text, sends the chunks to OpenAI for embeddings,
and stores vectors plus summary identifiers in a patient-specific Pinecone
namespace. Search combines BM25 and semantic result ranks with reciprocal rank
fusion. If either cloud service is unavailable, BM25 continues to work.

`POST /api/v1/patients/{patient_id}/answer` runs the grounded-answer LangGraph:

1. Authorize the active role and retrieve approved summary versions.
2. Abstain immediately when no evidence is found.
3. Generate a structured answer and source-version citations using
   `OPENAI_ANSWER_MODEL`.
4. Reject unknown citations and run a separate support check over the cited
   evidence.
5. Return the verified answer with source links, or an abstention.

OpenAI response storage is disabled for these answer and verification calls.
The default answer model is `gpt-4o-mini`; set `OPENAI_ANSWER_MODEL` in `.env`
to use another model that supports Structured Outputs.

Patients and authorized care partners can persist questions with
`POST /api/v1/patients/{patient_id}/questions`. The source-version IDs are
validated against the patient's approved summaries. Clinicians use
`GET /api/v1/clinician/questions` and
`POST /api/v1/clinician/questions/{question_id}/respond` for the question inbox.
Question creation, edits and clinician responses also create append-only audit
events in `care_question_events`.

`POST /api/v1/patients/{patient_id}/preparation-plans` runs a second LangGraph
workflow over the latest approved version of each summary and the patient's
active questions. It proposes at most five evidence-linked items and uses a
separate model pass to reject unsupported or clinical recommendations. A draft
must be explicitly approved by the patient before its tasks become actionable.
Task completion and reopening are persisted, human-controlled and recorded in
`preparation_events`. Set `OPENAI_PREPARATION_MODEL` to override the default
`gpt-4o-mini` model. OpenAI response storage is disabled for both model calls.

When a patient approves a checklist, a deterministic LangGraph action
orchestrator routes only evidence-backed action types to separate appointment,
laboratory, and imaging specialist nodes. These nodes call the local mock
integration boundary and persist exact proposals; they do not infer a new care
need. Every proposal retains its source-version IDs and remains inactive until
the patient, or a care partner with delegated approval permission, approves its
exact version. Confirmed mock actions can be exported through
`GET /api/v1/patients/{patient_id}/preparation-calendar.ics`.

Preparation reminders use immutable versions and server-side timezone
validation. Creating or editing a reminder leaves it awaiting approval. Patient
approval is bound to the exact task, source IDs, text, recipient, channel,
local time, IANA timezone and UTC instant with a SHA-256 hash. The local mock
scheduler persists an idempotency key and simulated receipt, so an approval
retry cannot create a second operation. Editing a scheduled reminder cancels
the prior mock operation and requires fresh approval. Pause, cancellation and
task completion remain separate persistent transitions.

Dependency changes propagate through the persisted workflow. Activating a
newer summary version supersedes the older search version, marks preparation
plans that cite it as needing review, and pauses their reminders. Editing or
resolving a cited question, completing a linked task, or approving a replacement
checklist also pauses affected reminders. Each pause records a user-visible
reason and cancels the prior pending mock-provider operation.

Reminder permission is separately versioned. A patient can disable it through
`PATCH /api/v1/patients/{patient_id}/reminder-consent`, which immediately pauses
pending reminders. Re-enabling permission does not reactivate them: the user
must save and approve a new reminder version bound to the new permission
version.

The delivery simulation supports `delivered`, `failed`,
`timeout_before_commit`, and `timeout_after_commit`. A timeout records
`outcome_unknown`; callers must use the reconcile endpoint before another
delivery attempt. Reconciliation queries the existing provider operation by its
idempotency key, so a timeout after commit resolves to the original delivery
without creating another operation. Signed provider callbacks use
`MOCK_PROVIDER_WEBHOOK_SECRET`, accept only delivered/failed states, and dedupe
on provider event ID. Callbacks received after pause or cancellation are
recorded but cannot reactivate the reminder.

## Activity and tracing

`GET /api/v1/patients/{patient_id}/activity` returns an authorized projection
of summary, question, preparation, reminder, provider and workflow events. It
uses controlled descriptions and excludes question text, reminder text,
recipient contact details, approval hashes and raw provider payloads.

Agent runs also create local `workflow_runs` records with workflow name, model,
status, input/result counts and stop reason. To enable LangSmith tracing, set
`LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT` in
`.env`. The application forces `LANGSMITH_HIDE_INPUTS=true` and
`LANGSMITH_HIDE_OUTPUTS=true` before importing LangGraph whenever tracing is
enabled. Choose an approved `LANGSMITH_ENDPOINT` for the deployment region.
CareBridge creates parent spans for OCR, grounded answers, preparation planning,
and action orchestration. LangGraph node runs appear beneath their workflow
span. Trace metadata is limited to roles, models, provider names, status and
counts; document text, questions, answers, patient identifiers, names, contact
details and uploaded bytes are excluded. Tracing failures do not interrupt the
application, and the local `workflow_runs` records remain authoritative.
Clinicians can verify configuration without exposing credentials through
`GET /api/v1/observability/status?actor_role=clinician&actor_id=<id>`.

## Development evaluations

The clinician-only `/api/v1/evaluations` endpoints expose versioned synthetic
grounded-answer cases and persist every run and case outcome in SQLite. The
`grounded_answer_v1.jsonl` dataset contains six synthetic text cases. The
`preparation_action_v1.jsonl` dataset adds eight cases covering appointment,
laboratory and imaging extraction, missing prerequisites, saved questions,
ambiguous wording, medication safety and prompt injection.

Every run executes deterministic behavior, evidence Recall@5 and citation
precision/recall checks. Selecting RAGAS scoring additionally runs
faithfulness, context recall and context precision for non-abstained answers.
That option uses `OPENAI_API_KEY` and `RAGAS_EVALUATOR_MODEL` and therefore
adds model calls. Reference answers remain inside the evaluation runner and
are never supplied to the CareBridge answering graph. A run with model or
metric errors is stored as partial or failed; unevaluated cases never count as
passes.

Preparation cases use deterministic action precision/recall, source validity,
field-copy accuracy, blocked-prerequisite, prohibited-action, item-bound and
specialist-routing checks in `app/preparation_evaluations.py`. RAGAS is not used
as the sole preparation scorer because these workflow and safety properties
require explicit gold labels. The runner accepts an injected generator for
offline tests and uses the live preparation LangGraph by default.

## Sharing, arrangements, and publication handoff

Care-partner access and arrangement-approval delegation are persisted with
optimistic permission versions. Patient revocation removes subsequent workspace
authorization. Appointment, travel, laboratory, and imaging routes use
fictional options, validate required inputs, bind approval to the exact payload,
and return deterministic idempotent mock receipts. They never contact a provider.

Publishing a reviewed transcript writes a `DocumentPublished` outbox event in
the same SQLite transaction. The publication-index worker consumes pending
events by immutable version ID; retries cannot create another publication
event, and an older event cannot activate over a newer version.
