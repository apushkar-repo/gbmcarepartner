# CareBridge frontend

Responsive React, TypeScript and Vite frontend for the CareBridge patient,
authorized care-partner and clinician workflows.

## Run locally

Start the FastAPI backend first. Then run:

```sh
cd gbmcarepartner/frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. All roles enter through the same URL. The current
role selector is development access and is not secure authentication.

## Implemented backend-connected flows

- Clinician patient onboarding and care-partner authorization.
- Camera or file upload followed by LlamaParse OCR.
- Side-by-side source and transcript review, correction, approval and
  publication.
- SQLite FTS5 BM25 search with optional OpenAI/Pinecone semantic retrieval.
- LangGraph grounded answers with source citations, verification and
  abstention.
- Persistent patient and care-partner questions with source lineage.
- Clinician question inbox with persistent responses and statuses.
- Evidence-linked preparation checklist drafts with patient approval,
  persistent completion, and LangGraph routing to appointment, laboratory, and
  imaging specialist agents.
- Versioned reminder drafts with exact patient approval, timezone validation,
  persistent pause/cancel states and idempotent mock scheduling receipts.
- Source-change propagation that marks affected preparation plans for review
  and pauses dependent reminders with a visible reason.
- Patient-controlled, versioned reminder permission with immediate pause on
  revocation and explicit reapproval after re-enablement.
- Mock delivery testing for success, failure and uncertain outcomes, with an
  explicit provider-status reconciliation action.
- A role-scoped Activity & Evidence timeline covering source versions,
  questions, preparation, reminders, provider outcomes and redacted agent-run
  status.
- A clinician-only evaluation screen for executing and inspecting persisted
  grounded-answer cases with optional RAGAS scores and preparation/action cases
  with deterministic extraction, safety, prerequisite, and routing checks.
- Persistent patient-controlled care-partner permissions and separate
  arrangement-approval delegation.
- Persisted appointment, travel, laboratory, and imaging mock proposals with
  exact approval, cancellation, idempotent fictional receipts, and an iCalendar
  download containing only confirmed actions.
- Published visit summaries and activity evidence loaded from FastAPI.

External bookings and reminder delivery remain visibly simulated. Their
application state, exact approvals, cancellations, and mock-provider receipts
are persisted by the backend.

## Development data boundary

This build is not authenticated or suitable for real patient data. Route guards
improve the development experience but do not establish identity. Uploaded
documents can be sent to LlamaParse, summary text can be sent to OpenAI for
embeddings and grounded answers, and embeddings can be stored in Pinecone when
those providers are configured. Use fictional documents and identities.

SQLite persists backend records, saved questions, approved preparation
checklists, permissions, arrangements, reminder versions and mock scheduling
receipts across browser refreshes and sign-out. No clinic booking, notification,
EHR, travel or lab action is sent externally.

## Validation

```sh
npm run build
npx playwright install chromium
npm run test:e2e
```

The production build includes TypeScript checking. Existing browser tests cover
the earlier UI simulation and should be updated as each screen moves to a
backend-connected workflow.
