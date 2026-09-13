# Team 42 — CareBridge Project Breakout Handout

**The Gen Academy · Mastering Agentic AI · Evals Week Breakout**

## 1. Who is on this team

| # | Full name | Email |
|---:|---|---|
| 1 | Pushkar  |  |
| 2 | Judy |  |
| 3 | Subodh |  |
| 4 | Lowhitha |  |
| 5 |  |  |
| 6 |  |  |
| 7 |  |  |

**Point person:** ______________________________________________

## 2. Warm up: go around the room

Share your name, where you are joining from, and one repetitive task you would hand to an AI agent. For this project, consider the work required after a medical visit: reading handwritten notes, remembering instructions, coordinating appointments, and keeping family members informed.

## 3. Pick a topic and sketch the design

### Q1. Pick the use case

**CareBridge: an AI care companion for patients with glioblastoma and their authorized care partners.**

After a clinical visit, patients may receive a handwritten or scanned summary containing recommendations, tests, and follow-up details. Acting on that information requires several disconnected steps. CareBridge turns the document into a clinician-approved digital visit record, lets the patient ask grounded questions across approved summaries, and creates an actionable preparation plan for the next visit.

The workflow supports three roles through one application URL:

- **Clinician:** onboard a patient; upload or photograph a visit summary; review OCR text beside the original; correct, save, and approve the summary.
- **Patient:** read approved summaries; inspect their sources; ask questions; save questions; approve preparation tasks and arrangements; download a calendar.
- **Authorized care partner:** view permitted summaries and assist with questions and preparation within the patient's delegated permissions.

### Q2. Knowledge and tools

**What the system needs to know**

- Clinician-approved visit-summary text and its version history
- Explicit recommendations, documented tests, and next-appointment details
- Patient questions, task status, permissions, approvals, and arrangement state
- The provenance of every answer and proposed action

**Where RAG fits**

- LlamaParse/LlamaIndex extracts the complete text from uploaded images or PDFs.
- Approved summary versions are chunked and indexed for semantic retrieval in Pinecone.
- BM25 lexical search is combined with semantic retrieval for hybrid ranking.
- The grounded-answer agent receives only authorized passages, answers with citations, and abstains when the available summaries do not support an answer.
- SQLite remains the authority for users, permissions, document versions, approvals, tasks, and booking state.

**Tools and actions**

- Camera and file upload
- OCR/extraction and side-by-side transcript review
- Pinecone vector indexing, BM25 search, and source retrieval
- Patient onboarding and role-based authorization
- Appointment, laboratory, imaging, and travel coordination adapters
- Reminder scheduling and downloadable ICS calendar generation
- LangSmith traces and application activity history
- RAGAS plus deterministic evaluation runners

### Q3. Autonomy and evals

**Autonomy boundary**

CareBridge uses bounded autonomy. Agents may extract text, retrieve approved records, draft grounded answers, identify explicit preparation actions, and prepare scheduling options. Deterministic LangGraph routing invokes the appropriate specialist. Agents cannot diagnose, interpret scans, change treatment, create missing clinical orders, expose another patient's data, or confirm an external action without approval.

The key control gates are:

1. A clinician reviews and approves the exact visit-summary version.
2. The patient reviews and approves the generated preparation checklist.
3. Missing dates, order references, pickup locations, or permissions block the affected action.
4. The patient approves the exact appointment, laboratory, imaging, or travel proposal.
5. Execution uses version checks and idempotency keys to prevent duplicate actions.

**How we evaluate it**

- OCR transcription accuracy and preservation of original wording
- Retrieval recall and ranking across approved patient summaries
- Answer faithfulness, citation correctness, relevance, and appropriate abstention
- Preparation-action precision and recall for clinic, laboratory, imaging, and travel paths
- Correct handling of missing orders, ambiguous dates, changed summaries, and revoked access
- Router and specialist selection accuracy
- Zero unauthorized access and zero unapproved external actions
- Idempotent confirmation, cancellation, retry, and calendar behavior
- Human review of safety-critical cases, supplemented by RAGAS and deterministic scoring

The repository currently includes versioned grounded-answer and preparation-action evaluation datasets, along with automated backend and frontend verification.

## 4. Our project

### CareBridge in one sentence

CareBridge converts a clinician-reviewed visit document into a trusted patient record, grounded answers, and approved actions for the next visit.

### Agentic workflow

1. **Document intake:** the clinician uploads or photographs the visit summary.
2. **OCR and review:** LlamaParse extracts the full transcript; the original and extracted text appear side by side for correction and approval.
3. **Publication and indexing:** an approved version is persisted and indexed through a durable outbox.
4. **Grounded Q&A:** hybrid retrieval finds authorized passages; the answering agent responds with citations or abstains.
5. **Preparation planning:** the planner prioritizes every explicit appointment, laboratory test, and imaging requirement, then adds supported questions and preparation items.
6. **Patient approval:** the patient reviews the checklist before any specialist workflow runs.
7. **Specialist coordination:** the LangGraph orchestrator routes documented actions to appointment, laboratory, imaging, and travel specialists.
8. **Resolve gaps:** missing clinical orders and patient logistics remain visible as blocked items.
9. **Confirm and prepare:** the patient approves exact proposals and downloads a preparation calendar.

### Technology

React and TypeScript · FastAPI and Python · LangGraph · OpenAI · LlamaParse/LlamaIndex · Pinecone · BM25 · SQLite · LangSmith · RAGAS

### What makes it agentic

The system observes an approved visit record, reasons over explicit next steps, produces a source-linked plan, routes each action to a bounded specialist, pauses when prerequisites are missing, and resumes after human approval. It maintains state across the entire workflow instead of producing a one-time summary.

### Success criteria

- Patients can understand what was documented and trace every answer back to its source.
- Explicit follow-up appointments and tests are not omitted from preparation.
- Unsupported clinical claims and actions are never introduced.
- Patients remain in control of sharing, checklist approval, and every arrangement.
- Corrections and permission changes invalidate affected downstream work.
