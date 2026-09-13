import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Check,
  HeartHandshake,
  Info,
  MessageCircle,
  Send,
  ShieldCheck,
} from "lucide-react";
import { Badge, PageHeading } from "../components";
import {
  createPatient,
  grantCarePartner,
  getEvaluationDataset,
  getEvaluationRun,
  getPreparationEvaluationDataset,
  listClinicianQuestions,
  listPatients,
  respondToCareQuestion,
  runEvaluation,
  runPreparationEvaluation,
  type CareQuestion,
  type CareQuestionStatus,
  type EvaluationDataset,
  type EvaluationRun,
  type PreparationEvaluationDataset,
  type Patient,
} from "../api";

export function Clinician() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [partnerEmails, setPartnerEmails] = useState<Record<string, string>>(
    {},
  );
  useEffect(() => {
    listPatients()
      .then(setPatients)
      .catch(() => setError("Start the backend to load patients."));
  }, []);
  async function onboard(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      const patient = await createPatient({
        name: String(data.get("name")),
        email: String(data.get("email")),
        phone: String(data.get("phone")),
      });
      setPatients((current) => [...current, patient]);
      setShowForm(false);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Patient could not be created.",
      );
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="CLINICIAN WORKSPACE"
        title="Choose a patient to continue."
        description="Open an existing patient or onboard someone new before adding a visit summary."
      />
      <section className="card">
        <div className="section-heading">
          <h2>Your patients</h2>
          <button
            className="button secondary"
            onClick={() => setShowForm(!showForm)}
          >
            Onboard a patient
          </button>
        </div>
        {showForm && (
          <form className="review-fields" onSubmit={onboard}>
            <label htmlFor="patient-name">Patient name</label>
            <input id="patient-name" name="name" required />
            <label htmlFor="patient-email">Email</label>
            <input id="patient-email" name="email" type="email" />
            <label htmlFor="patient-phone">Phone</label>
            <input id="patient-phone" name="phone" type="tel" />
            <p className="small muted">
              A patient ID is generated automatically. Provide at least one
              contact method.
            </p>
            <button className="button primary" type="submit">
              Create patient
            </button>
          </form>
        )}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        {patients.length === 0 && !showForm && (
          <p className="muted">
            No patients yet. Onboard your first patient to continue.
          </p>
        )}
        {patients.map((patient) => (
          <div className="clinician-patient" key={patient.id}>
            <span className="avatar large">
              {patient.name
                .split(" ")
                .map((part) => part[0])
                .join("")
                .slice(0, 2)}
            </span>
            <div className="grow">
              <h2>{patient.name}</h2>
              <p>
                {patient.id} · {patient.email || patient.phone}
              </p>
              <Badge tone={patient.summary_count ? "green" : "neutral"}>
                {patient.summary_count ?? 0} published summaries
              </Badge>
              <form
                onSubmit={async (event) => {
                  event.preventDefault();
                  try {
                    await grantCarePartner(
                      patient.id,
                      partnerEmails[patient.id] ?? "",
                    );
                    setPartnerEmails((current) => ({
                      ...current,
                      [patient.id]: "",
                    }));
                  } catch (e) {
                    setError(
                      e instanceof Error
                        ? e.message
                        : "Access could not be granted.",
                    );
                  }
                }}
              >
                <label className="sr-only" htmlFor={`partner-${patient.id}`}>
                  Care-partner email
                </label>
                <div className="split">
                  <input
                    id={`partner-${patient.id}`}
                    type="email"
                    placeholder="Care-partner email"
                    value={partnerEmails[patient.id] ?? ""}
                    onChange={(event) =>
                      setPartnerEmails((current) => ({
                        ...current,
                        [patient.id]: event.target.value,
                      }))
                    }
                    required
                  />
                  <button className="button secondary" type="submit">
                    Authorize care partner
                  </button>
                </div>
              </form>
            </div>
            <div className="stack compact-actions">
              {Boolean(patient.summary_count) && (
                <Link
                  className="button secondary"
                  to="/app/documents"
                  onClick={() =>
                    sessionStorage.setItem("carebridge.patientId", patient.id)
                  }
                >
                  View summaries
                </Link>
              )}
              <Link
                className="button primary"
                to={`/app/capture?patientId=${encodeURIComponent(patient.id)}&patientName=${encodeURIComponent(patient.name)}`}
              >
                Add visit summary
                <ArrowRight size={17} />
              </Link>
            </div>
          </div>
        ))}
      </section>
      <div className="quiet-banner">
        <ShieldCheck size={23} />
        <div>
          <h3>Publication and action approval are separate.</h3>
          <p>
            Your clinical approval does not book an appointment, send a message,
            or grant new sharing permissions.
          </p>
        </div>
      </div>
    </>
  );
}

export function ClinicianQuestions() {
  const [questions, setQuestions] = useState<CareQuestion[]>([]);
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [statuses, setStatuses] = useState<
    Record<string, Exclude<CareQuestionStatus, "open">>
  >({});
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listClinicianQuestions()
      .then(setQuestions)
      .catch((e) =>
        setError(
          e instanceof Error
            ? e.message
            : "Patient questions could not be loaded.",
        ),
      );
  }, []);

  async function respond(question: CareQuestion) {
    const response = responses[question.id]?.trim() ?? "";
    if (!response) return;
    setSavingId(question.id);
    setError("");
    try {
      const updated = await respondToCareQuestion(
        question.id,
        response,
        statuses[question.id] ?? "discussed",
      );
      setQuestions((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setResponses((current) => ({ ...current, [question.id]: "" }));
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The response could not be saved.",
      );
    } finally {
      setSavingId(null);
    }
  }

  const openCount = questions.filter(
    (question) =>
      question.status === "open" || question.status === "follow_up_needed",
  ).length;
  return (
    <>
      <PageHeading
        eyebrow="CLINICIAN QUESTION INBOX"
        title="Patient questions"
        description="Review questions saved by patients and authorized care partners, then record a response and status."
      />
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <section className="card question-inbox">
        <div className="section-heading">
          <div>
            <h2>Questions awaiting review</h2>
            <p className="muted">{openCount} open or needing follow-up</p>
          </div>
          <Badge tone={openCount ? "amber" : "green"}>
            {openCount ? `${openCount} to review` : "All reviewed"}
          </Badge>
        </div>
        {questions.length === 0 ? (
          <div className="empty-state">
            <MessageCircle size={30} />
            <h3>No patient questions yet</h3>
            <p>Saved patient questions will appear here.</p>
          </div>
        ) : (
          questions.map((question) => (
            <article className="inbox-question" key={question.id}>
              <div className="section-heading compact-heading">
                <div>
                  <p className="eyebrow">{question.patient_name}</p>
                  <h3>{question.text}</h3>
                  <p className="muted">
                    {question.patient_id} · {question.source_label}
                  </p>
                </div>
                <Badge
                  tone={question.status === "resolved" ? "green" : "neutral"}
                >
                  {question.status.replaceAll("_", " ")}
                </Badge>
              </div>
              {question.clinician_response && (
                <div className="clinician-response">
                  <strong>Current response</strong>
                  <p>{question.clinician_response}</p>
                </div>
              )}
              <label htmlFor={`response-${question.id}`}>
                Care-team response
              </label>
              <textarea
                id={`response-${question.id}`}
                rows={3}
                maxLength={4000}
                value={responses[question.id] ?? ""}
                onChange={(event) =>
                  setResponses((current) => ({
                    ...current,
                    [question.id]: event.target.value,
                  }))
                }
                placeholder="Record the response shared with the patient"
              />
              <div className="question-response-actions">
                <label htmlFor={`status-${question.id}`}>Status</label>
                <select
                  id={`status-${question.id}`}
                  value={statuses[question.id] ?? "discussed"}
                  onChange={(event) =>
                    setStatuses((current) => ({
                      ...current,
                      [question.id]: event.target.value as Exclude<
                        CareQuestionStatus,
                        "open"
                      >,
                    }))
                  }
                >
                  <option value="discussed">Discussed</option>
                  <option value="follow_up_needed">Follow-up needed</option>
                  <option value="resolved">Resolved</option>
                </select>
                <button
                  className="button primary"
                  disabled={
                    savingId === question.id || !responses[question.id]?.trim()
                  }
                  onClick={() => void respond(question)}
                >
                  <Send size={16} />
                  {savingId === question.id ? "Saving…" : "Save response"}
                </button>
              </div>
            </article>
          ))
        )}
      </section>
    </>
  );
}
export function Helper() {
  const [done, setDone] = useState(false);
  return (
    <>
      <PageHeading
        eyebrow="LOGISTICS HELPER WORKSPACE"
        title="A small task. A meaningful hand."
        description="Only the task details explicitly shared with you appear here."
      />
      <section className="card helper-task">
        <span className="metric-icon peach">
          <HeartHandshake size={26} />
        </span>
        <Badge tone="neutral">Approved task fields only</Badge>
        <h2>Help organize a folder</h2>
        <p>
          Prepare an empty folder for an upcoming visit. The folder contents and
          clinical records have not been shared.
        </p>
        <div className="permission-line">
          <span>Assigned to</span>
          <strong>Jamie Chen</strong>
        </div>
        <div className="permission-line">
          <span>Status</span>
          <strong>{done ? "Completed by you" : "Open"}</strong>
        </div>
        <button
          className={`button ${done ? "secondary" : "primary"} wide`}
          onClick={() => setDone(!done)}
        >
          {done ? "Reopen task" : "Confirm task is complete"}
          <Check size={17} />
        </button>
      </section>
      <p className="inline-note">
        <ShieldCheck size={17} />
        This role has no summary, appointment, or patient-metadata view.
      </p>
    </>
  );
}
export function Reviewer() {
  const [dataset, setDataset] = useState<EvaluationDataset | null>(null);
  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [includeRagas, setIncludeRagas] = useState(false);
  const [running, setRunning] = useState(false);
  const [preparationDataset, setPreparationDataset] =
    useState<PreparationEvaluationDataset | null>(null);
  const [preparationRun, setPreparationRun] = useState<EvaluationRun | null>(
    null,
  );
  const [preparationRunning, setPreparationRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getEvaluationDataset()
      .then(async (loaded) => {
        setDataset(loaded);
        if (loaded.latest_run) {
          setRun(await getEvaluationRun(loaded.latest_run.id));
        }
      })
      .catch((caught) =>
        setError(
          caught instanceof Error
            ? caught.message
            : "The evaluation dataset could not be loaded.",
        ),
      );
    getPreparationEvaluationDataset()
      .then(async (loaded) => {
        setPreparationDataset(loaded);
        if (loaded.latest_run) {
          setPreparationRun(await getEvaluationRun(loaded.latest_run.id));
        }
      })
      .catch((caught) =>
        setError(
          caught instanceof Error
            ? caught.message
            : "The preparation evaluation dataset could not be loaded.",
        ),
      );
  }, []);

  async function execute() {
    setRunning(true);
    setError("");
    try {
      setRun(await runEvaluation(includeRagas));
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "The evaluation failed.",
      );
    } finally {
      setRunning(false);
    }
  }

  async function executePreparation() {
    setPreparationRunning(true);
    setError("");
    try {
      setPreparationRun(await runPreparationEvaluation());
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The preparation evaluation failed.",
      );
    } finally {
      setPreparationRunning(false);
    }
  }

  const completed = run?.status === "completed" || run?.status === "partial";
  const percent = run?.total_cases
    ? Math.round((run.passed_cases / run.total_cases) * 100)
    : 0;
  return (
    <>
      <PageHeading
        eyebrow="DEVELOPMENT EVALUATIONS"
        title="Measure CareBridge agent workflows."
        description="Run versioned synthetic cases through grounded answers, preparation planning, safety checks, and specialist routing."
      >
        <button
          className="button primary"
          disabled={running || !dataset}
          onClick={execute}
        >
          {running ? "Running answer evaluation…" : "Run answer evaluation"}
          <ArrowRight size={17} />
        </button>
      </PageHeading>
      <div className="notice">
        <Info size={20} />
        <p>
          This suite uses synthetic text fixtures and does not measure OCR,
          clinical quality, production safety, or real-patient outcomes. Gold
          answers remain in the evaluation runner and are never sent to the
          CareBridge answering workflow.
        </p>
      </div>
      {error && (
        <div className="notice error">
          <Info size={20} />
          <p>{error}</p>
        </div>
      )}
      <section className="card eval-controls">
        <div>
          <span className="tiny-label">DATASET</span>
          <h2>{dataset?.name ?? "Loading dataset…"}</h2>
          <p className="muted">
            {dataset
              ? `Version ${dataset.version} · ${dataset.case_count} cases · ${dataset.scope}`
              : ""}
          </p>
        </div>
        <label className="eval-option">
          <input
            type="checkbox"
            checked={includeRagas}
            onChange={(event) => setIncludeRagas(event.target.checked)}
          />
          <span>
            <strong>Add RAGAS semantic scoring</strong>
            <small>
              Uses additional model calls for faithfulness and context metrics.
            </small>
          </span>
        </label>
      </section>
      <section className="card eval-controls">
        <div>
          <span className="tiny-label">PREPARATION AND ACTION DATASET</span>
          <h2>{preparationDataset?.name ?? "Loading dataset…"}</h2>
          <p className="muted">
            {preparationDataset
              ? `Version ${preparationDataset.version} · ${preparationDataset.case_count} cases · ${preparationDataset.scope}`
              : ""}
          </p>
          {preparationRun && (
            <p className="small muted">
              Latest run: {preparationRun.passed_cases}/
              {preparationRun.total_cases} passed · {preparationRun.status}
            </p>
          )}
        </div>
        <button
          className="button secondary"
          disabled={preparationRunning || !preparationDataset}
          onClick={executePreparation}
        >
          {preparationRunning
            ? "Running preparation evaluation…"
            : "Run preparation evaluation"}
          <ArrowRight size={17} />
        </button>
      </section>
      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-icon sage">
            <Activity size={24} />
          </span>
          <div>
            <strong>{run ? run.status.replace("_", " ") : "Not Run"}</strong>
            <p>Latest run status</p>
          </div>
        </div>
        <div className="metric-card">
          <span className="metric-icon sage">
            <Check size={24} />
          </span>
          <div>
            <strong>
              {completed ? `${run?.passed_cases}/${run?.total_cases}` : "—"}
            </strong>
            <p>Cases passing deterministic checks</p>
          </div>
        </div>
        <div className="metric-card">
          <span className="metric-icon sage">
            <ShieldCheck size={24} />
          </span>
          <div>
            <strong>{completed ? `${percent}%` : "—"}</strong>
            <p>Pass rate for this small fixture set</p>
          </div>
        </div>
      </div>
      {run && (
        <p className="small muted eval-run-meta">
          Run {run.id} · model {run.model ?? "unrecorded"} ·{" "}
          {run.include_ragas ? "RAGAS included" : "deterministic checks only"} ·{" "}
          {new Date(run.created_at).toLocaleString()}
        </p>
      )}
      <section className="card">
        <div className="section-heading">
          <h2>Evaluation cases</h2>
          <Badge
            tone={
              completed
                ? run?.status === "completed"
                  ? "green"
                  : "amber"
                : "neutral"
            }
          >
            {run ? run.status : "Not Run"}
          </Badge>
        </div>
        {dataset?.cases.map((definition) => {
          const result = run?.cases?.find(
            (item) => item.case_id === definition.case_id,
          );
          return (
            <div className="review-case" key={definition.case_id}>
              <div className="grow">
                <span className="tiny-label">
                  {definition.case_id} · EXPECTED TO{" "}
                  {definition.expected_behavior.toUpperCase()}
                </span>
                <h3>{definition.title}</h3>
                <p>{definition.question}</p>
                {result?.answer && (
                  <p className="eval-answer">
                    <strong>Observed:</strong> {result.answer}
                  </p>
                )}
                {result?.error && <p className="eval-error">{result.error}</p>}
                {result && Object.keys(result.scores).length > 0 && (
                  <div className="eval-scores">
                    {Object.entries(result.scores)
                      .filter(([name]) => name !== "passed")
                      .map(([name, value]) => (
                        <span key={name}>
                          {name.replaceAll("_", " ")}:{" "}
                          {value === null ? "not scored" : String(value)}
                        </span>
                      ))}
                  </div>
                )}
              </div>
              <Badge
                tone={
                  !result
                    ? "neutral"
                    : result.status === "error" || !result.passed
                      ? "amber"
                      : "green"
                }
              >
                {!result
                  ? "Not Run"
                  : result.status === "error"
                    ? "Error"
                    : result.passed
                      ? "Pass"
                      : "Fail"}
              </Badge>
            </div>
          );
        })}
      </section>
      <p className="small muted">
        A passing run shows only that this build met the assertions in this
        small synthetic dataset. It is not clinical validation.
      </p>
    </>
  );
}
export function Operations() {
  return (
    <>
      <PageHeading
        eyebrow="OPERATIONS WORKSPACE"
        title="The service, without the records."
        description="Infrastructure connection status only. No patient records or private traces are shown."
      />
      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-icon sage">
            <Activity size={24} />
          </span>
          <div>
            <strong>Frontend</strong>
            <p>Running locally</p>
          </div>
        </div>
        <div className="metric-card">
          <span className="metric-icon peach">
            <ShieldCheck size={24} />
          </span>
          <div>
            <strong>Hackathon access</strong>
            <p>Production authentication pending</p>
          </div>
        </div>
      </div>
      <section className="card">
        <div className="section-heading">
          <h2>Integration readiness</h2>
          <Badge tone="neutral">Not connected</Badge>
        </div>
        {[
          "Python API & SQLite",
          "OIDC identity provider",
          "LlamaParse document processing",
          "OpenAI & Pinecone retrieval",
          "LangSmith traces & RAGAS evaluations",
          "Scheduling, messaging, travel, and laboratory integrations",
        ].map((name) => (
          <div className="permission-line" key={name}>
            <strong>{name}</strong>
            <Badge tone="neutral">Planned</Badge>
          </div>
        ))}
      </section>
    </>
  );
}
