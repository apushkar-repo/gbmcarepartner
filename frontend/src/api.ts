const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";
function actorQuery() {
  return new URLSearchParams({
    actor_role: sessionStorage.getItem("carebridge.role") ?? "",
    actor_id: sessionStorage.getItem("carebridge.actorId") ?? "",
  }).toString();
}
export const documentContentUrl = (documentId: string) =>
  `${API_URL}/api/v1/documents/${documentId}/content?${actorQuery()}`;

export interface UploadReceipt {
  id: string;
  filename: string;
  status: string;
  extraction_job_id: string;
}

export async function uploadDocument(
  file: File,
  patientId?: string,
): Promise<UploadReceipt> {
  const body = new FormData();
  body.append("file", file);
  const query = new URLSearchParams(actorQuery());
  if (patientId) query.set("patient_id", patientId);
  const response = await fetch(`${API_URL}/api/v1/documents?${query}`, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Upload failed (${response.status}).`);
  }
  return response.json() as Promise<UploadReceipt>;
}

export interface Patient {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  summary_count?: number;
}
export async function listPatients(): Promise<Patient[]> {
  const response = await fetch(`${API_URL}/api/v1/patients?${actorQuery()}`);
  if (!response.ok) throw new Error("Patients could not be loaded.");
  return response.json();
}
export async function createPatient(input: {
  name: string;
  email?: string;
  phone?: string;
}): Promise<Patient> {
  const response = await fetch(`${API_URL}/api/v1/patients?${actorQuery()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Patient could not be created.");
  }
  return response.json();
}

export interface PublishedSummary {
  id: string;
  version: number;
  status: string;
  payload: { text: string; audience: string };
  created_at: string;
  document_id: string;
  filename: string;
}
export async function listPatientSummaries(
  patientId: string,
): Promise<PublishedSummary[]> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/summaries?${actorQuery()}`,
  );
  if (!response.ok) throw new Error("Visit summaries could not be loaded.");
  return response.json();
}

export async function grantCarePartner(
  patientId: string,
  partnerEmail: string,
): Promise<void> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/care-partners?${actorQuery()}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ partner_email: partnerEmail }),
    },
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(
      detail.detail ??
        `Care-partner access could not be granted (${response.status}).`,
    );
  }
}

export interface CarePartnerPermission {
  id: string;
  partner_email: string;
  status: "active" | "revoked";
  can_view_records: boolean;
  can_manage_questions: boolean;
  can_approve_actions: boolean;
  version: number;
  created_at: string;
  updated_at: string | null;
}

export async function listCarePartners(
  patientId: string,
): Promise<CarePartnerPermission[]> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/care-partners?${actorQuery()}`,
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(
      detail.detail ??
        `Sharing permissions could not be loaded (${response.status}).`,
    );
  }
  return response.json();
}

export async function updateCarePartnerPermission(
  patientId: string,
  grant: CarePartnerPermission,
  change: Partial<
    Pick<
      CarePartnerPermission,
      | "status"
      | "can_view_records"
      | "can_manage_questions"
      | "can_approve_actions"
    >
  >,
): Promise<CarePartnerPermission> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/care-partners/${encodeURIComponent(grant.id)}?${actorQuery()}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...change, expected_version: grant.version }),
    },
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(
      detail.detail ?? "Sharing permissions could not be updated.",
    );
  }
  return response.json();
}

export interface SearchResult {
  version_id: string;
  content: string;
  score: number;
  document_id: string;
  filename: string;
  version: number;
}
export async function searchSummaries(
  patientId: string,
  query: string,
): Promise<SearchResult[]> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/search?q=${encodeURIComponent(query)}&${actorQuery()}`,
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Summary search failed.");
  }
  const body = await response.json();
  return body.results;
}

export interface AnswerCitation {
  version_id: string;
  document_id: string;
  filename: string;
  version: number;
}

export interface GroundedAnswer {
  question: string;
  answer: string;
  abstained: boolean;
  citations: AnswerCitation[];
  retrieval_mode: "bm25" | "hybrid";
}

export async function answerQuestion(
  patientId: string,
  question: string,
  sourceVersionId?: string,
): Promise<GroundedAnswer> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/answer?${actorQuery()}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        source_version_id: sourceVersionId || null,
      }),
    },
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "The question could not be answered.");
  }
  return response.json();
}

export type CareQuestionStatus =
  "open" | "discussed" | "follow_up_needed" | "resolved";

export interface CareQuestion {
  id: string;
  patient_id: string;
  patient_name?: string;
  text: string;
  original_text: string;
  source_label: string;
  source_version_ids: string[];
  status: CareQuestionStatus;
  created_by_role: string;
  clinician_response: string | null;
  responded_by: string | null;
  created_at: string;
  updated_at: string;
}

export async function listCareQuestions(
  patientId: string,
): Promise<CareQuestion[]> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/questions?${actorQuery()}`,
  );
  if (!response.ok) throw new Error("Saved questions could not be loaded.");
  return response.json();
}

export async function createCareQuestion(
  patientId: string,
  input: {
    text: string;
    original_text?: string;
    source_label?: string;
    source_version_ids?: string[];
  },
): Promise<CareQuestion> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/questions?${actorQuery()}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "The question could not be saved.");
  }
  return response.json();
}

export async function updateCareQuestion(
  patientId: string,
  questionId: string,
  input: { text?: string; status?: CareQuestionStatus },
): Promise<CareQuestion> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/questions/${encodeURIComponent(questionId)}?${actorQuery()}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "The question could not be updated.");
  }
  return response.json();
}

export async function listClinicianQuestions(): Promise<CareQuestion[]> {
  const response = await fetch(
    `${API_URL}/api/v1/clinician/questions?${actorQuery()}`,
  );
  if (!response.ok) throw new Error("Patient questions could not be loaded.");
  return response.json();
}

export async function respondToCareQuestion(
  questionId: string,
  responseText: string,
  status: Exclude<CareQuestionStatus, "open">,
): Promise<CareQuestion> {
  const response = await fetch(
    `${API_URL}/api/v1/clinician/questions/${encodeURIComponent(questionId)}/respond?${actorQuery()}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ response: responseText, status }),
    },
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "The response could not be saved.");
  }
  return response.json();
}

export type PreparationPlanStatus =
  "draft" | "approved" | "needs_review" | "superseded";
export type PreparationTaskStatus = "proposed" | "open" | "completed";

export interface PreparationTask {
  id: string;
  plan_id: string;
  patient_id: string;
  title: string;
  description: string;
  origin_type:
    | "document_instruction"
    | "saved_question"
    | "clarification"
    | "app_suggestion";
  source_version_ids: string[];
  source_question_ids: string[];
  source_labels: string[];
  blocked_reason: string | null;
  status: PreparationTaskStatus;
  position: number;
  action: {
    task_id?: string;
    action_type:
      "none" | "clinic_appointment" | "laboratory" | "imaging" | "travel";
    documented_date?: string | null;
    documented_time?: string | null;
    documented_service?: string | null;
    order_reference?: string | null;
    specialist_status: string;
    arrangement_id?: string | null;
  };
}

export interface PreparationPlan {
  id: string;
  patient_id: string;
  status: PreparationPlanStatus;
  summary: string;
  message: string;
  verified: boolean;
  model: string | null;
  created_at: string;
  approved_at: string | null;
  items: PreparationTask[];
  action_orchestration_status?: "completed" | "failed";
}

async function preparationResponse(
  response: Response,
): Promise<PreparationPlan> {
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(
      detail.detail ?? "The preparation checklist could not be updated.",
    );
  }
  return response.json();
}

export async function getCurrentPreparationPlan(
  patientId: string,
): Promise<PreparationPlan | null> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/preparation-plans/current?${actorQuery()}`,
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(
      detail.detail ?? "The preparation checklist could not be loaded.",
    );
  }
  return response.json();
}

export async function createPreparationPlan(
  patientId: string,
): Promise<PreparationPlan> {
  return preparationResponse(
    await fetch(
      `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/preparation-plans?${actorQuery()}`,
      { method: "POST" },
    ),
  );
}

export async function approvePreparationPlan(
  patientId: string,
  planId: string,
): Promise<PreparationPlan> {
  return preparationResponse(
    await fetch(
      `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/preparation-plans/${encodeURIComponent(planId)}/approve?${actorQuery()}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approval: true }),
      },
    ),
  );
}

export async function orchestratePreparationPlan(
  patientId: string,
  planId: string,
): Promise<PreparationPlan> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/preparation-plans/${encodeURIComponent(planId)}/orchestrate?${actorQuery()}`,
    { method: "POST" },
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(
      detail.detail ?? "Preparation actions could not be proposed.",
    );
  }
  await response.json();
  const plan = await getCurrentPreparationPlan(patientId);
  if (!plan)
    throw new Error("The approved preparation checklist could not be loaded.");
  return plan;
}

export async function updatePreparationTask(
  patientId: string,
  taskId: string,
  complete: boolean,
): Promise<PreparationPlan> {
  return preparationResponse(
    await fetch(
      `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/preparation-tasks/${encodeURIComponent(taskId)}?${actorQuery()}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ complete }),
      },
    ),
  );
}

export type ReminderStatus =
  | "awaiting_approval"
  | "awaiting_reapproval"
  | "scheduled"
  | "attempted"
  | "outcome_unknown"
  | "delivered"
  | "failed"
  | "paused"
  | "cancelled";
export type ReminderChannel = "in_app" | "email" | "sms";

export interface PersistedReminder {
  reminder_id: string;
  patient_id: string;
  task_id: string;
  task_title: string;
  current_version: number;
  version: number;
  status: ReminderStatus;
  text: string;
  channel: ReminderChannel;
  recipient: string;
  recipient_label: string;
  local_date: string;
  local_time: string;
  timezone: string;
  utc_schedule: string;
  source_version_ids: string[];
  source_question_ids: string[];
  approved_at: string | null;
  provider_receipt: string | null;
  status_reason: string | null;
  simulation: true;
}

export interface ReminderDraftInput {
  task_id: string;
  text: string;
  local_date: string;
  local_time: string;
  timezone: string;
  channel: ReminderChannel;
  expected_version?: number;
}

export interface ReminderConsent {
  patient_id: string;
  enabled: boolean;
  version: number;
  consent_version: string;
  updated_at: string | null;
}

async function reminderResponse(
  response: Response,
): Promise<PersistedReminder> {
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "The reminder could not be updated.");
  }
  return response.json();
}

export async function getCurrentReminder(
  patientId: string,
): Promise<PersistedReminder | null> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/reminders/current?${actorQuery()}`,
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "The reminder could not be loaded.");
  }
  return response.json();
}

export async function getReminderConsent(
  patientId: string,
): Promise<ReminderConsent> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/reminder-consent?${actorQuery()}`,
  );
  if (!response.ok) throw new Error("Reminder permission could not be loaded.");
  return response.json();
}

export async function updateReminderConsent(
  patientId: string,
  enabled: boolean,
): Promise<ReminderConsent> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/reminder-consent?${actorQuery()}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    },
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(
      detail.detail ?? "Reminder permission could not be updated.",
    );
  }
  return response.json();
}

export async function saveReminderDraft(
  patientId: string,
  input: ReminderDraftInput,
  reminderId?: string,
): Promise<PersistedReminder> {
  const path = reminderId
    ? `/reminders/${encodeURIComponent(reminderId)}`
    : "/reminders";
  return reminderResponse(
    await fetch(
      `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}${path}?${actorQuery()}`,
      {
        method: reminderId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      },
    ),
  );
}

export async function approveReminder(
  patientId: string,
  reminderId: string,
  expectedVersion: number,
): Promise<PersistedReminder> {
  return reminderResponse(
    await fetch(
      `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/reminders/${encodeURIComponent(reminderId)}/approve?${actorQuery()}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approval: true,
          expected_version: expectedVersion,
        }),
      },
    ),
  );
}

export async function stopReminder(
  patientId: string,
  reminderId: string,
  action: "pause" | "cancel",
): Promise<PersistedReminder> {
  return reminderResponse(
    await fetch(
      `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/reminders/${encodeURIComponent(reminderId)}/${action}?${actorQuery()}`,
      { method: "POST" },
    ),
  );
}

export async function simulateReminderDelivery(
  patientId: string,
  reminderId: string,
  expectedVersion: number,
  outcome:
    "delivered" | "failed" | "timeout_before_commit" | "timeout_after_commit",
): Promise<PersistedReminder> {
  return reminderResponse(
    await fetch(
      `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/reminders/${encodeURIComponent(reminderId)}/dispatch?${actorQuery()}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ outcome, expected_version: expectedVersion }),
      },
    ),
  );
}

export async function reconcileReminderDelivery(
  patientId: string,
  reminderId: string,
): Promise<PersistedReminder> {
  return reminderResponse(
    await fetch(
      `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/reminders/${encodeURIComponent(reminderId)}/reconcile?${actorQuery()}`,
      { method: "POST" },
    ),
  );
}

export type ActivityCategory =
  | "summary"
  | "question"
  | "preparation"
  | "reminder"
  | "arrangement"
  | "workflow";

export interface ActivityItem {
  id: string;
  category: ActivityCategory;
  title: string;
  detail: string;
  status: string | null;
  actor_role: string;
  created_at: string;
  document_id?: string;
  version_id?: string;
  run_id?: string;
  stop_reason?: string | null;
  model?: string | null;
}

export async function listPatientActivity(
  patientId: string,
): Promise<ActivityItem[]> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/activity?${actorQuery()}`,
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Activity could not be loaded.");
  }
  return response.json();
}

export interface EvaluationCaseDefinition {
  case_id: string;
  title: string;
  question: string;
  expected_behavior: "answer" | "abstain";
  reference_context_ids: string[];
  tags: string[];
}

export interface EvaluationCaseResult extends EvaluationCaseDefinition {
  status: "completed" | "error";
  passed: boolean;
  error: string | null;
  actual_behavior?: "answer" | "abstain";
  answer?: string;
  retrieved_context_ids?: string[];
  cited_context_ids?: string[];
  scores: Record<string, number | boolean | null>;
}

export interface EvaluationRun {
  id: string;
  dataset_name: string;
  dataset_version: string;
  status: "running" | "completed" | "partial" | "failed";
  include_ragas: boolean;
  model: string | null;
  total_cases: number;
  completed_cases: number;
  passed_cases: number;
  aggregate_metrics: Record<string, number>;
  error: string | null;
  started_by: string;
  created_at: string;
  completed_at: string | null;
  cases?: EvaluationCaseResult[];
}

export interface EvaluationDataset {
  name: string;
  version: string;
  scope: string;
  case_count: number;
  cases: EvaluationCaseDefinition[];
  latest_run: EvaluationRun | null;
}

export interface PreparationEvaluationDataset {
  name: string;
  version: string;
  scope: string;
  case_count: number;
  cases: Array<{
    case_id: string;
    title: string;
    expected_action_types: string[];
    tags: string[];
  }>;
  latest_run: EvaluationRun | null;
}

async function evaluationResponse(response: Response): Promise<EvaluationRun> {
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "The evaluation could not be run.");
  }
  return response.json();
}

export async function getEvaluationDataset(): Promise<EvaluationDataset> {
  const response = await fetch(
    `${API_URL}/api/v1/evaluations/dataset?${actorQuery()}`,
  );
  if (!response.ok)
    throw new Error("The evaluation dataset could not be loaded.");
  return response.json();
}

export async function getPreparationEvaluationDataset(): Promise<PreparationEvaluationDataset> {
  const response = await fetch(
    `${API_URL}/api/v1/evaluations/preparation-dataset?${actorQuery()}`,
  );
  if (!response.ok)
    throw new Error("The preparation evaluation dataset could not be loaded.");
  return response.json();
}

export async function getEvaluationRun(runId: string): Promise<EvaluationRun> {
  return evaluationResponse(
    await fetch(
      `${API_URL}/api/v1/evaluations/runs/${encodeURIComponent(runId)}?${actorQuery()}`,
    ),
  );
}

export async function runEvaluation(
  includeRagas: boolean,
): Promise<EvaluationRun> {
  return evaluationResponse(
    await fetch(`${API_URL}/api/v1/evaluations/runs?${actorQuery()}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ include_ragas: includeRagas }),
    }),
  );
}

export async function runPreparationEvaluation(): Promise<EvaluationRun> {
  return evaluationResponse(
    await fetch(
      `${API_URL}/api/v1/evaluations/preparation-runs?${actorQuery()}`,
      { method: "POST" },
    ),
  );
}

export type ArrangementType = "appointment" | "travel" | "lab" | "imaging";
export interface Arrangement {
  id: string;
  patient_id: string;
  action_type: ArrangementType;
  current_version: number;
  status:
    "awaiting_information" | "awaiting_approval" | "confirmed" | "cancelled";
  provider_receipt: string | null;
  payload: Record<string, string | number | boolean | string[]>;
  source_version_ids: string[];
  source_labels: string[];
  approved_by: string | null;
  approved_at: string | null;
  simulation: true;
}
export async function getMockOptions(
  type: ArrangementType,
): Promise<Record<string, string | number>[]> {
  const response = await fetch(
    `${API_URL}/api/v1/mock-integrations/options?action_type=${type}&${actorQuery()}`,
  );
  if (!response.ok) throw new Error("Provider options could not be loaded.");
  return (await response.json()).options;
}
export async function listArrangements(
  patientId: string,
): Promise<Arrangement[]> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/arrangements?${actorQuery()}`,
  );
  if (!response.ok) throw new Error("Arrangements could not be loaded.");
  return response.json();
}

export const preparationCalendarUrl = (patientId: string) =>
  `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/preparation-calendar.ics?${actorQuery()}`;
export async function createArrangement(
  patientId: string,
  action_type: ArrangementType,
  payload: Record<string, string | number>,
): Promise<Arrangement> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/arrangements?${actorQuery()}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_type, payload }),
    },
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Arrangement could not be saved.");
  }
  return response.json();
}
export async function updateArrangement(
  patientId: string,
  item: Arrangement,
  action: "approve" | "cancel",
): Promise<Arrangement> {
  const response = await fetch(
    `${API_URL}/api/v1/patients/${encodeURIComponent(patientId)}/arrangements/${encodeURIComponent(item.id)}/${action}?${actorQuery()}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body:
        action === "approve"
          ? JSON.stringify({
              approval: true,
              expected_version: item.current_version,
            })
          : undefined,
    },
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Arrangement could not be updated.");
  }
  return response.json();
}

export async function processExtraction(
  jobId: string,
): Promise<{ status: string; pages?: number }> {
  const response = await fetch(
    `${API_URL}/api/v1/extraction-jobs/${jobId}/process?${actorQuery()}`,
    { method: "POST" },
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? `Extraction failed (${response.status}).`);
  }
  return response.json();
}

export async function getExtractionResult(jobId: string): Promise<{
  document_id: string;
  patient_id: string | null;
  original_text: string;
  text: string;
  pages: number;
  provider: string;
}> {
  const response = await fetch(
    `${API_URL}/api/v1/extraction-jobs/${jobId}/result?${actorQuery()}`,
  );
  if (!response.ok)
    throw new Error("The extraction result is not available yet.");
  return response.json();
}

export async function publishExtraction(
  jobId: string,
  text: string,
  audience: string,
): Promise<{ id: string; status: string; version: number }> {
  const response = await fetch(
    `${API_URL}/api/v1/extraction-jobs/${jobId}/publish?${actorQuery()}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, audience, approval: true }),
    },
  );
  if (!response.ok) throw new Error("Publication could not be completed.");
  return response.json();
}

export async function indexPublishedSummary(
  versionId: string,
): Promise<{ status: string }> {
  const response = await fetch(
    `${API_URL}/api/v1/document-versions/${versionId}/index?${actorQuery()}`,
    { method: "POST" },
  );
  if (!response.ok)
    throw new Error("The approved summary could not be indexed.");
  return response.json();
}

export async function saveTranscriptCorrection(
  jobId: string,
  text: string,
): Promise<{ version: number }> {
  const response = await fetch(
    `${API_URL}/api/v1/extraction-jobs/${jobId}/transcript?${actorQuery()}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    },
  );
  if (!response.ok)
    throw new Error("The corrected transcript could not be saved.");
  return response.json();
}
