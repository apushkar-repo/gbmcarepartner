import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Bell,
  CalendarDays,
  Check,
  Clock3,
  FileText,
  HeartHandshake,
  Info,
  LockKeyhole,
  MessageCircle,
  Plus,
  Send,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Badge, Empty, Modal, PageHeading } from "../components";
import { useCare } from "../context";
import { visitDateParts, type Question } from "../domain";
import {
  answerQuestion,
  approveReminder,
  approvePreparationPlan,
  createCareQuestion,
  createPreparationPlan,
  documentContentUrl,
  getCurrentReminder,
  getCurrentPreparationPlan,
  getReminderConsent,
  listCareQuestions,
  listCarePartners,
  listPatientActivity,
  orchestratePreparationPlan,
  saveReminderDraft,
  simulateReminderDelivery,
  stopReminder,
  updatePreparationTask,
  updateReminderConsent,
  reconcileReminderDelivery,
  updateCareQuestion,
  updateCarePartnerPermission,
  type AnswerCitation,
  type ActivityItem,
  type CareQuestion,
  type CareQuestionStatus,
  type CarePartnerPermission,
  type PersistedReminder,
  type PreparationPlan,
  type ReminderChannel,
  type ReminderConsent,
  type ReminderDraftInput,
} from "../api";

const questionStatusLabels: Record<CareQuestionStatus, Question["status"]> = {
  open: "Open",
  discussed: "Discussed",
  follow_up_needed: "Follow-up needed",
  resolved: "Resolved",
};

const questionStatusValues: Record<Question["status"], CareQuestionStatus> = {
  Open: "open",
  Discussed: "discussed",
  "Follow-up needed": "follow_up_needed",
  Resolved: "resolved",
};

function toUiQuestion(question: CareQuestion): Question {
  return {
    id: question.id,
    text: question.text,
    original: question.original_text,
    source: question.source_label,
    status: questionStatusLabels[question.status],
    clinicianResponse: question.clinician_response ?? undefined,
  };
}

export function Ask() {
  const { notify, update } = useCare();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<{
    question: string;
    text: string;
    citations: AnswerCitation[];
    abstained: boolean;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [source, setSource] = useState<AnswerCitation | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [savedQuestions, setSavedQuestions] = useState<CareQuestion[]>([]);
  const [saving, setSaving] = useState(false);
  const patientId = sessionStorage.getItem("carebridge.patientId");
  useEffect(() => {
    if (!patientId) return;
    listCareQuestions(patientId)
      .then((questions) => {
        setSavedQuestions(questions);
        update((state) => ({
          ...state,
          questions: questions.map(toUiQuestion),
        }));
      })
      .catch((e) =>
        setError(
          e instanceof Error
            ? e.message
            : "Saved questions could not be loaded.",
        ),
      );
  }, [patientId]);
  async function ask(text = question) {
    if (!text.trim()) return;
    setLoading(true);
    setError("");
    setAnswer(null);
    try {
      if (!patientId) throw new Error("Select a patient workspace first.");
      const result = await answerQuestion(patientId, text.trim());
      setAnswer({
        question: result.question,
        text: result.answer,
        citations: result.citations,
        abstained: result.abstained,
      });
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The summaries could not be searched.",
      );
    } finally {
      setLoading(false);
    }
  }
  const alreadySaved =
    draft !== null &&
    savedQuestions.some(
      (q) => q.text.toLowerCase() === draft.trim().toLowerCase(),
    );
  return (
    <>
      <PageHeading
        eyebrow="UNDERSTANDING STARTS WITH A QUESTION"
        title="Ask about your summaries"
        description="Look back at reviewed notes. Every supported answer links back to its source."
      />
      <div className="ask-layout">
        <section className="card conversation">
          <div className="conversation-intro">
            <span className="sparkle-box">
              <Sparkles size={25} />
            </span>
            <h2>What’s on your mind?</h2>
            <p>
              Start with what was written, or save a question to ask at your
              next visit.
            </p>
          </div>
          <div className="suggestion-chips">
            {[
              "What should I bring to my visit?",
              "Where is the appointment time written?",
            ].map((q) => (
              <button
                key={q}
                disabled={loading}
                onClick={() => {
                  setQuestion(q);
                  void ask(q);
                }}
              >
                {q}
                <ArrowRight size={15} />
              </button>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void ask();
            }}
          >
            <label className="sr-only" htmlFor="ask-question">
              Your question
            </label>
            <div className="question-input">
              <input
                id="ask-question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask about your reviewed summaries…"
                maxLength={1000}
              />
              <button
                className="icon-button send-button"
                type="submit"
                disabled={loading || !question.trim()}
                aria-label="Ask question"
              >
                <Send size={19} />
              </button>
            </div>
          </form>
          <p className="small muted">
            Answers use approved summaries only and link to their source
            document
          </p>
          {loading && (
            <p className="loading-line" role="status">
              Searching approved summaries…
            </p>
          )}
          {error && (
            <p role="alert" className="form-error">
              {error}
            </p>
          )}
          {answer && (
            <article className="answer-card" aria-live="polite">
              <div className="answer-label">
                <Sparkles size={17} />
                {!answer.abstained
                  ? "ANSWER FROM APPROVED SUMMARIES"
                  : "NOT FOUND IN AVAILABLE EVIDENCE"}
              </div>
              <h3>{answer.question}</h3>
              <p>{answer.text}</p>
              {answer.citations.map((citation) => (
                <button
                  className="citation"
                  key={citation.version_id}
                  onClick={() => setSource(citation)}
                >
                  <FileText size={17} />
                  <span>
                    {citation.filename} · Version {citation.version}
                  </span>
                  <ArrowRight size={16} />
                </button>
              ))}
              <button
                className="button secondary"
                onClick={() => setDraft(answer.question)}
              >
                <Plus size={16} />
                Save as a question for your visit
              </button>
            </article>
          )}
        </section>
        <aside className="card evidence-sidebar">
          <span className="metric-icon sage">
            <FileText size={22} />
          </span>
          <h3>Your source summaries</h3>
          <p>
            Results come only from approved, indexed summaries in the selected
            patient workspace.
          </p>
          <div className="notice compact">
            <Info size={18} />
            <p>
              For unclear clinical instructions, save a question for your care
              team. The app does not decide what an instruction means
              clinically.
            </p>
          </div>
        </aside>
      </div>
      <section className="card saved-question-list">
        <div className="section-heading">
          <div>
            <p className="eyebrow">SAVED FOR YOUR CARE TEAM</p>
            <h2>Your questions</h2>
          </div>
          <span className="count-pill">{savedQuestions.length}</span>
        </div>
        {savedQuestions.length === 0 ? (
          <Empty icon={MessageCircle} title="No saved questions yet">
            Ask about a summary or write your own question, then save it for the
            care team.
          </Empty>
        ) : (
          savedQuestions.map((item, index) => (
            <article className="question-row" key={item.id}>
              <span className="question-number">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div className="grow">
                <div className="section-heading compact-heading">
                  <h3>{item.text}</h3>
                  <Badge
                    tone={item.status === "resolved" ? "green" : "neutral"}
                  >
                    {item.status.replaceAll("_", " ")}
                  </Badge>
                </div>
                <p>{item.source_label}</p>
                {item.clinician_response && (
                  <div className="clinician-response">
                    <strong>Care-team response</strong>
                    <p>{item.clinician_response}</p>
                  </div>
                )}
              </div>
            </article>
          ))
        )}
      </section>
      {source !== null && (
        <Modal
          title={`${source.filename} · Version ${source.version}`}
          onClose={() => setSource(null)}
        >
          <img
            className="source-paper"
            src={documentContentUrl(source.document_id)}
            alt="Original visit summary"
          />
        </Modal>
      )}
      {draft !== null && (
        <Modal title="Make the question yours" onClose={() => setDraft(null)}>
          <label htmlFor="saved-question">Question for your next visit</label>
          <textarea
            id="saved-question"
            rows={4}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <p className="muted">
            This will be saved in the patient workspace and visible to the care
            team.
          </p>
          <button
            className="button primary wide"
            disabled={!draft.trim() || alreadySaved || saving}
            onClick={async () => {
              if (!patientId || !answer) return;
              setSaving(true);
              setError("");
              try {
                const sourceLabel =
                  answer.citations
                    .map(
                      (citation) =>
                        `${citation.filename} · Version ${citation.version}`,
                    )
                    .join(", ") || "Original question";
                const saved = await createCareQuestion(patientId, {
                  text: draft.trim(),
                  original_text: answer.question,
                  source_label: sourceLabel,
                  source_version_ids: answer.citations.map(
                    (citation) => citation.version_id,
                  ),
                });
                setSavedQuestions((current) => [saved, ...current]);
                update((state) => ({
                  ...state,
                  questions: [toUiQuestion(saved), ...state.questions],
                }));
                notify("Question saved for your care team");
                setDraft(null);
              } catch (e) {
                setError(
                  e instanceof Error
                    ? e.message
                    : "The question could not be saved.",
                );
              } finally {
                setSaving(false);
              }
            }}
          >
            {alreadySaved
              ? "This question is already saved"
              : saving
                ? "Saving…"
                : "Save question"}
          </button>
        </Modal>
      )}
    </>
  );
}

export function Visit() {
  const { state, update, persona, notify } = useCare();
  const [draft, setDraft] = useState<Question | null>(null);
  const [questionError, setQuestionError] = useState("");
  const [savingQuestion, setSavingQuestion] = useState(false);
  const [plan, setPlan] = useState<PreparationPlan | null>(null);
  const [planError, setPlanError] = useState("");
  const [planLoading, setPlanLoading] = useState(false);
  const planLoadPatient = useRef<string | null>(null);
  const preparationLoadPatient = useRef<string | null>(null);
  const patientId = sessionStorage.getItem("carebridge.patientId");
  useEffect(() => {
    if (!patientId) return;
    if (planLoadPatient.current === patientId) return;
    planLoadPatient.current = patientId;
    listCareQuestions(patientId)
      .then((questions) =>
        update((current) => ({
          ...current,
          questions: questions.map(toUiQuestion),
        })),
      )
      .catch((e) =>
        setQuestionError(
          e instanceof Error
            ? e.message
            : "Saved questions could not be loaded.",
        ),
      );
  }, [patientId]);
  useEffect(() => {
    if (!patientId) return;
    if (preparationLoadPatient.current === patientId) return;
    preparationLoadPatient.current = patientId;
    setPlanLoading(true);
    setPlanError("");
    getCurrentPreparationPlan(patientId)
      .then(async (current) => {
        if (current) {
          setPlan(current);
          return;
        }
        const generated = await createPreparationPlan(patientId);
        setPlan(generated);
      })
      .catch((error) =>
        setPlanError(
          error instanceof Error
            ? error.message
            : "Your preparation checklist could not be created.",
        ),
      )
      .finally(() => setPlanLoading(false));
  }, [patientId]);
  const complete =
    plan?.items.filter((item) => item.status === "completed").length ?? 0;
  const visit = state.fieldDate ? visitDateParts(state.fieldDate) : null;
  return (
    <>
      <PageHeading
        eyebrow="ROOM FOR WHAT MATTERS TO YOU"
        title="Prepare for your visit"
        description="Gather your questions and take the small practical steps at your own pace."
      >
        <button
          className="button primary"
          onClick={() =>
            setDraft({
              id: crypto.randomUUID(),
              text: "",
              original: "",
              status: "Open",
              source: "Added by you",
            })
          }
        >
          <Plus size={17} />
          Add a question
        </button>
      </PageHeading>
      <div className="visit-strip">
        <span className="metric-icon sage">
          <CalendarDays size={24} />
        </span>
        <div>
          <strong>
            {visit
              ? `${visit.weekday}, ${visit.full}`
              : "Visit date needs confirmation"}
          </strong>
          <p>Fieldstone Clinic · Appointment time needs confirmation</p>
        </div>
        <Badge tone="amber">Date only</Badge>
      </div>
      {questionError && (
        <p className="form-error" role="alert">
          {questionError}
        </p>
      )}
      <div className="two-column">
        <section className="card">
          <div className="section-heading">
            <h2>Your visit questions</h2>
            <span className="count-pill">{state.questions.length}</span>
          </div>
          {state.questions.length === 0 && (
            <Empty icon={MessageCircle} title="A place for your questions">
              Add one when you’re ready.
            </Empty>
          )}
          {state.questions.map((q, i) => (
            <div className="question-row" key={q.id}>
              <span className="question-number">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div className="grow">
                <h3>{q.text}</h3>
                <p>{q.source}</p>
                <div className="question-controls">
                  <select
                    aria-label={`Status for ${q.text}`}
                    value={q.status}
                    onChange={async (e) => {
                      if (!patientId) return;
                      const status = e.target.value as Question["status"];
                      setQuestionError("");
                      try {
                        const saved = await updateCareQuestion(
                          patientId,
                          q.id,
                          { status: questionStatusValues[status] },
                        );
                        update(
                          (s) => ({
                            ...s,
                            questions: s.questions.map((item) =>
                              item.id === saved.id ? toUiQuestion(saved) : item,
                            ),
                          }),
                          "Question status updated",
                        );
                      } catch (error) {
                        setQuestionError(
                          error instanceof Error
                            ? error.message
                            : "The question could not be updated.",
                        );
                      }
                    }}
                  >
                    {["Open", "Discussed", "Follow-up needed", "Resolved"].map(
                      (status) => (
                        <option key={status}>{status}</option>
                      ),
                    )}
                  </select>
                  <button
                    className="text-button"
                    onClick={() => setDraft({ ...q })}
                  >
                    Edit
                  </button>
                </div>
                {q.clinicianResponse && (
                  <div className="clinician-response">
                    <strong>Care-team response</strong>
                    <p>{q.clinicianResponse}</p>
                  </div>
                )}
              </div>
            </div>
          ))}
          <Link className="text-link section-bottom" to="/app/ask">
            Find a question in your summaries
            <ArrowRight size={16} />
          </Link>
        </section>
        <div className="stack">
          <section className="card">
            <div className="section-heading">
              <div>
                <h2>Your preparation list</h2>
                <p className="small muted">
                  Built from approved summaries and active questions
                </p>
              </div>
              {plan?.status === "approved" ? (
                <span className="small muted">
                  {complete} of {plan.items.length} done
                </span>
              ) : plan?.status === "needs_review" ? (
                <Badge tone="amber">Sources changed</Badge>
              ) : plan ? (
                <Badge tone="amber">Review draft</Badge>
              ) : null}
            </div>
            {planError && (
              <p className="form-error" role="alert">
                {planError}
              </p>
            )}
            {!plan && !planLoading && (
              <Empty icon={Check} title="No preparation checklist yet">
                CareBridge could not find an actionable instruction in your
                approved summaries or saved questions. You can try again after
                another summary or question is added.
              </Empty>
            )}
            {planLoading && (
              <p className="loading-line" role="status">
                Reviewing your approved summaries and preparing suggestions…
              </p>
            )}
            {plan && <p>{plan.summary}</p>}
            {plan?.items.map((t) => (
              <div
                className={`task-row ${t.status === "completed" ? "done" : ""}`}
                key={t.id}
              >
                <input
                  type="checkbox"
                  aria-label={`Complete ${t.title}`}
                  checked={t.status === "completed"}
                  disabled={
                    plan.status !== "approved" ||
                    !!t.blocked_reason ||
                    persona?.role !== "patient" ||
                    planLoading
                  }
                  onChange={async (e) => {
                    if (!patientId) return;
                    setPlanLoading(true);
                    setPlanError("");
                    try {
                      const updated = await updatePreparationTask(
                        patientId,
                        t.id,
                        e.target.checked,
                      );
                      setPlan(updated);
                      notify(
                        e.target.checked
                          ? "Preparation item completed"
                          : "Preparation item reopened",
                      );
                    } catch (error) {
                      setPlanError(
                        error instanceof Error
                          ? error.message
                          : "The preparation item could not be updated.",
                      );
                    } finally {
                      setPlanLoading(false);
                    }
                  }}
                />
                <div>
                  <h3>{t.title}</h3>
                  <p>{t.description}</p>
                  <span className="source-ref">
                    {t.origin_type === "app_suggestion"
                      ? `CareBridge travel option based on ${t.source_labels.join(" · ") || "the documented appointment"}`
                      : t.source_labels.join(" · ") ||
                        t.origin_type.replaceAll("_", " ")}
                  </span>
                  {t.action.action_type !== "none" && (
                    <div className="task-agent-result">
                      <Badge
                        tone={
                          t.action.specialist_status === "confirmed"
                            ? "green"
                            : t.action.specialist_status ===
                                "awaiting_information"
                              ? "amber"
                              : "blue"
                        }
                      >
                        {t.action.specialist_status === "confirmed"
                          ? "Added to schedule"
                          : t.action.specialist_status ===
                              "awaiting_information"
                            ? "Details needed"
                            : t.action.specialist_status === "awaiting_approval"
                              ? "Ready for review"
                              : "Preparing"}
                      </Badge>
                      <span className="small muted">
                        {t.action.action_type.replaceAll("_", " ")}
                        {t.action.documented_date
                          ? ` · ${t.action.documented_date}`
                          : ""}
                      </span>
                      {t.action.arrangement_id && (
                        <Link className="text-link" to="/app/arrangements">
                          Review proposal
                          <ArrowRight size={14} />
                        </Link>
                      )}
                    </div>
                  )}
                  {t.blocked_reason && (
                    <p className="blocked-text">
                      <Clock3 size={14} />
                      {t.blocked_reason}
                    </p>
                  )}
                </div>
              </div>
            ))}
            {plan && <p className="small muted">{plan.message}</p>}
            {plan?.status === "draft" && plan.items.length > 0 && (
              <button
                className="button primary wide"
                disabled={planLoading || persona?.role !== "patient"}
                onClick={async () => {
                  if (!patientId) return;
                  setPlanLoading(true);
                  setPlanError("");
                  try {
                    const approved = await approvePreparationPlan(
                      patientId,
                      plan.id,
                    );
                    setPlan(approved);
                    notify(
                      "Checklist saved and preparation agents have proposed the next actions",
                    );
                  } catch (error) {
                    setPlanError(
                      error instanceof Error
                        ? error.message
                        : "The preparation checklist could not be saved.",
                    );
                  } finally {
                    setPlanLoading(false);
                  }
                }}
              >
                <ShieldCheck size={17} />
                Save this checklist
              </button>
            )}
            {plan?.status === "draft" && persona?.role === "partner" && (
              <p className="small muted">
                The patient must review and save this checklist.
              </p>
            )}
            {plan?.status === "approved" &&
              plan.items.some(
                (item) =>
                  item.action.action_type !== "none" &&
                  !item.action.arrangement_id,
              ) && (
                <button
                  className="button secondary wide"
                  disabled={planLoading}
                  onClick={async () => {
                    if (!patientId) return;
                    setPlanLoading(true);
                    setPlanError("");
                    try {
                      const updated = await orchestratePreparationPlan(
                        patientId,
                        plan.id,
                      );
                      setPlan(updated);
                      notify(
                        "Preparation action proposals are ready to review",
                      );
                    } catch (error) {
                      setPlanError(
                        error instanceof Error
                          ? error.message
                          : "Preparation actions could not be proposed.",
                      );
                    } finally {
                      setPlanLoading(false);
                    }
                  }}
                >
                  <Sparkles size={17} />
                  Retry action planning
                </button>
              )}
            <button
              className="button secondary wide"
              disabled={planLoading}
              onClick={async () => {
                if (!patientId) return;
                setPlanLoading(true);
                setPlanError("");
                try {
                  const generated = await createPreparationPlan(patientId);
                  setPlan(generated);
                } catch (error) {
                  setPlanError(
                    error instanceof Error
                      ? error.message
                      : "A preparation draft could not be created.",
                  );
                } finally {
                  setPlanLoading(false);
                }
              }}
            >
              <Sparkles size={17} />
              {plan ? "Build a new draft" : "Build preparation checklist"}
            </button>
          </section>
          <section className="card arrangement-card">
            <div className="section-heading">
              <h2>Preparation actions</h2>
              <Badge tone="blue">Your approval required</Badge>
            </div>
            <p>
              Review visit, laboratory, imaging, and travel proposals created
              from your approved checklist. You decide whether each simulated
              booking may proceed.
            </p>
            <Link className="button secondary wide" to="/app/arrangements">
              Open arrangements
              <ArrowRight size={16} />
            </Link>
          </section>
        </div>
      </div>
      {draft && (
        <Modal
          title={
            state.questions.some((q) => q.id === draft.id)
              ? "Edit visit question"
              : "Add a visit question"
          }
          onClose={() => setDraft(null)}
        >
          <label htmlFor="question-draft">Question</label>
          <textarea
            id="question-draft"
            rows={4}
            value={draft.text}
            onChange={(e) => setDraft({ ...draft, text: e.target.value })}
          />
          <p className="small muted">
            Target visit: September 24 · Original wording and source lineage are
            retained.
          </p>
          <button
            className="button primary wide"
            disabled={!draft.text.trim() || savingQuestion}
            onClick={async () => {
              if (!patientId) return;
              setSavingQuestion(true);
              setQuestionError("");
              try {
                const exists = state.questions.some(
                  (question) => question.id === draft.id,
                );
                const saved = exists
                  ? await updateCareQuestion(patientId, draft.id, {
                      text: draft.text.trim(),
                    })
                  : await createCareQuestion(patientId, {
                      text: draft.text.trim(),
                      original_text: draft.original || draft.text.trim(),
                      source_label: draft.source,
                    });
                update(
                  (s) => ({
                    ...s,
                    questions: exists
                      ? s.questions.map((question) =>
                          question.id === saved.id
                            ? toUiQuestion(saved)
                            : question,
                        )
                      : [...s.questions, toUiQuestion(saved)],
                  }),
                  "Visit question saved",
                );
                setDraft(null);
              } catch (error) {
                setQuestionError(
                  error instanceof Error
                    ? error.message
                    : "The question could not be saved.",
                );
              } finally {
                setSavingQuestion(false);
              }
            }}
          >
            {savingQuestion ? "Saving…" : "Save question"}
          </button>
        </Modal>
      )}
    </>
  );
}

export function Reminders() {
  const { persona, notify } = useCare();
  const [editing, setEditing] = useState(false);
  const [reminder, setReminder] = useState<PersistedReminder | null>(null);
  const [plan, setPlan] = useState<PreparationPlan | null>(null);
  const [consent, setConsent] = useState<ReminderConsent | null>(null);
  const [draft, setDraft] = useState<ReminderDraftInput>({
    task_id: "",
    text: "Prepare for your upcoming visit.",
    local_date: "",
    local_time: "09:00",
    timezone: "America/New_York",
    channel: "in_app",
  });
  const [review, setReview] = useState(false);
  const [deliveryTest, setDeliveryTest] = useState(false);
  const [deliveryOutcome, setDeliveryOutcome] = useState<
    "delivered" | "failed" | "timeout_before_commit" | "timeout_after_commit"
  >("delivered");
  const [checked, setChecked] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const patientId = sessionStorage.getItem("carebridge.patientId");
  useEffect(() => {
    if (!patientId) return;
    Promise.all([
      getCurrentReminder(patientId),
      getCurrentPreparationPlan(patientId),
      getReminderConsent(patientId),
    ])
      .then(([currentReminder, currentPlan, currentConsent]) => {
        setReminder(currentReminder);
        setPlan(currentPlan);
        setConsent(currentConsent);
      })
      .catch((reason) =>
        setError(
          reason instanceof Error
            ? reason.message
            : "Reminder details could not be loaded.",
        ),
      );
  }, [patientId]);
  const eligibleTasks =
    plan?.status === "approved"
      ? plan.items.filter(
          (item) => item.status === "open" && !item.blocked_reason,
        )
      : [];
  const reminderTaskOptions = eligibleTasks.map((item) => ({
    id: item.id,
    title: item.title,
  }));
  if (
    reminder &&
    !reminderTaskOptions.some((item) => item.id === reminder.task_id)
  ) {
    reminderTaskOptions.unshift({
      id: reminder.task_id,
      title: reminder.task_title,
    });
  }
  const valid =
    !!draft.text.trim() &&
    !!draft.local_date &&
    !!draft.local_time &&
    !!draft.task_id;
  const isPatient = persona?.role === "patient";
  const channelLabels: Record<ReminderChannel, string> = {
    in_app: "In-app",
    email: "Email",
    sms: "SMS",
  };
  const statusLabels = {
    awaiting_approval: "Awaiting approval",
    awaiting_reapproval: "Awaiting reapproval",
    scheduled: "Scheduled · simulated",
    attempted: "Delivery attempted",
    outcome_unknown: "Outcome needs reconciliation",
    delivered: "Delivered · simulated",
    failed: "Delivery failed · simulated",
    paused: "Paused",
    cancelled: "Cancelled",
  } as const;
  function openEditor() {
    const taskId = reminder?.task_id ?? eligibleTasks[0]?.id ?? "";
    setDraft(
      reminder
        ? {
            task_id: reminder.task_id,
            text: reminder.text,
            local_date: reminder.local_date,
            local_time: reminder.local_time,
            timezone: reminder.timezone,
            channel: reminder.channel,
            expected_version: reminder.current_version,
          }
        : {
            task_id: taskId,
            text: "Prepare for your upcoming visit.",
            local_date: "",
            local_time: "09:00",
            timezone: "America/New_York",
            channel: "in_app",
          },
    );
    setEditing(true);
  }
  function openReview() {
    setChecked(false);
    setReview(true);
  }
  return (
    <>
      <PageHeading
        eyebrow="A GENTLE NUDGE, ON YOUR TERMS"
        title="Preparation reminders"
        description="You choose the timing and who receives it. Every reminder needs your approval."
      />
      <div className="notice">
        <Bell size={20} />
        <div>
          <strong>Reminder delivery is simulated</strong>
          <p>
            The backend validates future local times and daylight-saving
            changes. Every approved reminder receives a confirmation reference
            and remains within this hackathon environment.
          </p>
        </div>
      </div>
      <section className="quiet-banner">
        <ShieldCheck size={22} />
        <div className="grow">
          <h3>
            Reminder permission: {consent?.enabled === false ? "Off" : "On"}
          </h3>
          <p>
            Turning this off immediately pauses pending simulated reminders.
            Turning it on creates a new permission version; reminders still
            require exact approval.
          </p>
        </div>
        <button
          className={
            consent?.enabled === false
              ? "button secondary"
              : "text-button danger"
          }
          disabled={!isPatient || loading || !consent}
          onClick={async () => {
            if (!patientId || !consent) return;
            setLoading(true);
            setError("");
            try {
              const updated = await updateReminderConsent(
                patientId,
                !consent.enabled,
              );
              setConsent(updated);
              if (!updated.enabled) {
                setReminder(await getCurrentReminder(patientId));
              }
              notify(
                updated.enabled
                  ? "Reminder permission enabled"
                  : "Reminder permission disabled",
              );
            } catch (reason) {
              setError(
                reason instanceof Error
                  ? reason.message
                  : "Reminder permission could not be updated.",
              );
            } finally {
              setLoading(false);
            }
          }}
        >
          {consent?.enabled === false
            ? "Enable reminders"
            : "Disable reminders"}
        </button>
      </section>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {!reminder && (
        <section className="card reminder-card">
          <Empty icon={Bell} title="No reminder created yet">
            Choose an open preparation item, timing, and channel. You will
            review the exact reminder before it is scheduled.
          </Empty>
          <button
            className="button primary wide"
            disabled={
              loading || eligibleTasks.length === 0 || !consent?.enabled
            }
            onClick={openEditor}
          >
            <Plus size={17} />
            Create reminder draft
          </button>
          {eligibleTasks.length === 0 && (
            <p className="small muted">
              Save a preparation checklist with an open item before creating a
              reminder.
            </p>
          )}
        </section>
      )}
      {reminder && (
        <section className="card reminder-card">
          <div className="section-heading">
            <div className="row">
              <span className="metric-icon lilac">
                <Bell size={23} />
              </span>
              <div>
                <h2>Before your next visit</h2>
                <p className="small muted">
                  User-selected preparation · Version {reminder.version}
                </p>
              </div>
            </div>
            <Badge
              tone={
                ["scheduled", "delivered"].includes(reminder.status)
                  ? "green"
                  : "amber"
              }
            >
              {statusLabels[reminder.status]}
            </Badge>
          </div>
          <blockquote>{reminder.text}</blockquote>
          <div className="reminder-details">
            <div>
              <span>WHEN</span>
              <strong>{reminder.local_date}</strong>
              <p>
                {reminder.local_time} · {reminder.timezone}
              </p>
            </div>
            <div>
              <span>RECIPIENT</span>
              <strong>{reminder.recipient_label}</strong>
              <p>Only you · No clinical details are shown</p>
            </div>
            <div>
              <span>CHANNEL</span>
              <strong>{channelLabels[reminder.channel]}</strong>
              <p>Simulated · No real delivery</p>
            </div>
          </div>
          <div className="reminder-source">
            <FileText size={17} />
            Based on preparation item: {reminder.task_title}
          </div>
          {reminder.provider_receipt && (
            <p className="small muted">
              Confirmation reference: {reminder.provider_receipt}
            </p>
          )}
          {reminder.status === "paused" && reminder.status_reason && (
            <p className="blocked-text">
              <Clock3 size={16} />
              {reminder.status_reason}
            </p>
          )}
          <div className="bottom-actions">
            <button
              className="button secondary"
              disabled={
                loading ||
                ["cancelled", "delivered"].includes(reminder.status) ||
                !consent?.enabled
              }
              onClick={openEditor}
            >
              Edit reminder
            </button>
            <div className="row">
              {reminder.status === "scheduled" && (
                <button
                  className="button primary"
                  disabled={loading || !isPatient || !consent?.enabled}
                  onClick={() => setDeliveryTest(true)}
                >
                  Check delivery status
                </button>
              )}
              {reminder.status === "outcome_unknown" && (
                <button
                  className="button primary"
                  disabled={loading}
                  onClick={async () => {
                    if (!patientId) return;
                    setLoading(true);
                    setError("");
                    try {
                      const reconciled = await reconcileReminderDelivery(
                        patientId,
                        reminder.reminder_id,
                      );
                      setReminder(reconciled);
                      notify("Delivery status updated");
                    } catch (reason) {
                      setError(
                        reason instanceof Error
                          ? reason.message
                          : "The delivery status could not be reconciled.",
                      );
                    } finally {
                      setLoading(false);
                    }
                  }}
                >
                  Reconcile provider status
                </button>
              )}
              {reminder.status === "scheduled" && (
                <button
                  className="text-button"
                  disabled={loading || !isPatient || !consent?.enabled}
                  onClick={async () => {
                    if (!patientId) return;
                    setLoading(true);
                    setError("");
                    try {
                      setReminder(
                        await stopReminder(
                          patientId,
                          reminder.reminder_id,
                          "pause",
                        ),
                      );
                      notify("Reminder paused");
                    } catch (reason) {
                      setError(
                        reason instanceof Error
                          ? reason.message
                          : "The reminder could not be paused.",
                      );
                    } finally {
                      setLoading(false);
                    }
                  }}
                >
                  Pause reminder
                </button>
              )}
              {!["cancelled", "delivered"].includes(reminder.status) && (
                <button
                  className="text-button danger"
                  disabled={loading || !isPatient}
                  onClick={async () => {
                    if (!patientId) return;
                    setLoading(true);
                    setError("");
                    try {
                      setReminder(
                        await stopReminder(
                          patientId,
                          reminder.reminder_id,
                          "cancel",
                        ),
                      );
                      notify("Reminder cancelled");
                    } catch (reason) {
                      setError(
                        reason instanceof Error
                          ? reason.message
                          : "The reminder could not be cancelled.",
                      );
                    } finally {
                      setLoading(false);
                    }
                  }}
                >
                  Cancel reminder
                </button>
              )}
              {["awaiting_approval", "awaiting_reapproval"].includes(
                reminder.status,
              ) && (
                <button
                  className="button primary"
                  disabled={loading || !isPatient || !consent?.enabled}
                  onClick={openReview}
                >
                  Review & approve
                  <ArrowRight size={17} />
                </button>
              )}
            </div>
          </div>
          {!isPatient && (
            <p className="blocked-text">
              <LockKeyhole size={16} />
              The patient must approve, pause, or cancel this reminder.
            </p>
          )}
        </section>
      )}
      <section className="quiet-banner">
        <ShieldCheck size={22} />
        <div>
          <h3>A scheduled reminder isn’t a completed task.</h3>
          <p>
            Only you or an authorized person can mark a preparation task
            complete.
          </p>
        </div>
      </section>
      {editing && (
        <Modal title="Edit reminder details" onClose={() => setEditing(false)}>
          <label htmlFor="reminder-task">Preparation item</label>
          <select
            id="reminder-task"
            value={draft.task_id}
            onChange={(event) =>
              setDraft({ ...draft, task_id: event.target.value })
            }
          >
            {reminderTaskOptions.map((item) => (
              <option value={item.id} key={item.id}>
                {item.title}
              </option>
            ))}
          </select>
          <label htmlFor="reminder-text">Exact reminder text</label>
          <textarea
            id="reminder-text"
            rows={3}
            value={draft.text}
            maxLength={240}
            onChange={(e) => setDraft({ ...draft, text: e.target.value })}
          />
          <div className="form-grid">
            <div>
              <label htmlFor="reminder-date">Preparation date</label>
              <input
                id="reminder-date"
                type="date"
                value={draft.local_date}
                onChange={(e) =>
                  setDraft({ ...draft, local_date: e.target.value })
                }
              />
            </div>
            <div>
              <label htmlFor="reminder-time">Local time</label>
              <input
                id="reminder-time"
                type="time"
                value={draft.local_time}
                onChange={(e) =>
                  setDraft({ ...draft, local_time: e.target.value })
                }
              />
            </div>
          </div>
          <label htmlFor="timezone">Timezone</label>
          <select
            id="timezone"
            value={draft.timezone}
            onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}
          >
            <option>America/New_York</option>
            <option>America/Chicago</option>
            <option>America/Los_Angeles</option>
            <option>Asia/Kolkata</option>
          </select>
          <label htmlFor="channel">Simulated channel</label>
          <select
            id="channel"
            value={draft.channel}
            onChange={(e) =>
              setDraft({
                ...draft,
                channel: e.target.value as ReminderChannel,
              })
            }
          >
            <option value="in_app">In-app</option>
            <option value="email">Email</option>
            <option value="sms">SMS</option>
          </select>
          <p className="inline-note">
            <Info size={16} />
            Editing creates a new version and requires fresh approval.
          </p>
          {!valid && (
            <p className="form-error">
              Choose an open preparation item and enter the reminder text, date,
              and time.
            </p>
          )}
          <button
            className="button primary wide"
            disabled={!valid || loading}
            onClick={async () => {
              if (!patientId) return;
              setLoading(true);
              setError("");
              try {
                const saved = await saveReminderDraft(
                  patientId,
                  draft,
                  reminder?.reminder_id,
                );
                setReminder(saved);
                setEditing(false);
                notify("Reminder saved · approval required");
              } catch (reason) {
                setError(
                  reason instanceof Error
                    ? reason.message
                    : "The reminder could not be saved.",
                );
              } finally {
                setLoading(false);
              }
            }}
          >
            {loading ? "Saving…" : reminder ? "Save new version" : "Save draft"}
          </button>
        </Modal>
      )}
      {review && (
        <Modal
          title="Approve this exact reminder?"
          onClose={() => setReview(false)}
        >
          <div className="approval-summary">
            <p className="eyebrow">
              VERSION {reminder?.version} · SIMULATION ONLY
            </p>
            <h3>{reminder?.text}</h3>
            <dl>
              <dt>Schedule</dt>
              <dd>
                {reminder?.local_date} at {reminder?.local_time}
              </dd>
              <dt>Timezone</dt>
              <dd>{reminder?.timezone}</dd>
              <dt>Recipient</dt>
              <dd>{reminder?.recipient_label}</dd>
              <dt>Channel</dt>
              <dd>{reminder && channelLabels[reminder.channel]}</dd>
              <dt>Source</dt>
              <dd>{reminder?.task_title}</dd>
            </dl>
          </div>
          <label className="check-label">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
            />
            I approve this exact text, recipient, schedule, and channel.
          </label>
          <button
            className="button primary wide"
            disabled={!checked || !isPatient || loading || !reminder}
            onClick={async () => {
              if (!patientId || !reminder) return;
              setLoading(true);
              setError("");
              try {
                const scheduled = await approveReminder(
                  patientId,
                  reminder.reminder_id,
                  reminder.current_version,
                );
                setReminder(scheduled);
                setReview(false);
                notify("Reminder scheduled in simulation");
              } catch (reason) {
                setError(
                  reason instanceof Error
                    ? reason.message
                    : "The reminder could not be scheduled.",
                );
              } finally {
                setLoading(false);
              }
            }}
          >
            Approve simulated reminder
          </button>
        </Modal>
      )}
      {deliveryTest && reminder && (
        <Modal
          title="Update the delivery outcome"
          onClose={() => setDeliveryTest(false)}
        >
          <Badge tone="blue">Hackathon environment</Badge>
          <p>
            This exercises delivery and reconciliation without sending a real
            notification. Task completion remains unchanged.
          </p>
          <label htmlFor="delivery-outcome">Delivery outcome</label>
          <select
            id="delivery-outcome"
            value={deliveryOutcome}
            onChange={(event) =>
              setDeliveryOutcome(event.target.value as typeof deliveryOutcome)
            }
          >
            <option value="delivered">Delivered</option>
            <option value="failed">Confirmed failure</option>
            <option value="timeout_before_commit">
              Timeout before provider commit
            </option>
            <option value="timeout_after_commit">
              Timeout after provider commit
            </option>
          </select>
          <button
            className="button primary wide"
            disabled={loading}
            onClick={async () => {
              if (!patientId) return;
              setLoading(true);
              setError("");
              try {
                const delivered = await simulateReminderDelivery(
                  patientId,
                  reminder.reminder_id,
                  reminder.current_version,
                  deliveryOutcome,
                );
                setReminder(delivered);
                setDeliveryTest(false);
                notify(
                  delivered.status === "outcome_unknown"
                    ? "Delivery outcome needs reconciliation"
                    : `Delivery ${delivered.status}`,
                );
              } catch (reason) {
                setError(
                  reason instanceof Error
                    ? reason.message
                    : "The delivery status could not be updated.",
                );
              } finally {
                setLoading(false);
              }
            }}
          >
            Run delivery simulation
          </button>
        </Modal>
      )}
    </>
  );
}

export function ActivityPage() {
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [error, setError] = useState("");
  const patientId = sessionStorage.getItem("carebridge.patientId");
  useEffect(() => {
    if (patientId)
      listPatientActivity(patientId)
        .then(setActivity)
        .catch((reason) =>
          setError(
            reason instanceof Error
              ? reason.message
              : "Activity could not be loaded.",
          ),
        );
  }, [patientId]);
  function readableTime(value: string) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
  }
  return (
    <>
      <PageHeading
        eyebrow="A CLEAR RECORD OF EACH STEP"
        title="Activity"
        description="Review summary, question, preparation, reminder, provider, and agent workflow activity in one place."
      />
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <section className="card timeline">
        {activity.length === 0 && !error && (
          <div className="empty">
            <Info size={24} />
            <h3>No activity yet</h3>
            <p>Saved and approved workflow activity will appear here.</p>
          </div>
        )}
        {activity.map((item, i) => (
          <div className="timeline-event" key={item.id}>
            <span className={`timeline-marker ${i === 0 ? "current" : ""}`}>
              <Check size={15} />
            </span>
            <div className="grow">
              <span className="tiny-label">
                {i === 0 ? "MOST RECENT" : item.category.toUpperCase()}
              </span>
              <h3>{item.title}</h3>
              <p>
                {item.detail} · {readableTime(item.created_at)} ·{" "}
                {item.actor_role.replaceAll("_", " ")}
              </p>
              {item.stop_reason && (
                <p className="small muted">
                  Stop reason: {item.stop_reason.replaceAll("_", " ")}
                </p>
              )}
              {item.document_id && (
                <a
                  className="text-link"
                  href={documentContentUrl(item.document_id)}
                  target="_blank"
                  rel="noreferrer"
                >
                  View source summary
                </a>
              )}
            </div>
            {item.status && (
              <Badge tone={item.status === "completed" ? "green" : "neutral"}>
                {item.status.replaceAll("_", " ")}
              </Badge>
            )}
          </div>
        ))}
      </section>
    </>
  );
}

export function Sharing() {
  const [grants, setGrants] = useState<CarePartnerPermission[]>([]);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const patientId = sessionStorage.getItem("carebridge.patientId");
  useEffect(() => {
    if (patientId)
      listCarePartners(patientId)
        .then(setGrants)
        .catch((reason) =>
          setError(
            reason instanceof Error
              ? reason.message
              : "Sharing permissions could not be loaded.",
          ),
        );
  }, [patientId]);
  async function change(
    grant: CarePartnerPermission,
    update: Parameters<typeof updateCarePartnerPermission>[2],
  ) {
    if (!patientId) return;
    setSaving(grant.id);
    setError("");
    try {
      const changed = await updateCarePartnerPermission(
        patientId,
        grant,
        update,
      );
      setGrants((current) =>
        current.map((item) =>
          item.id === grant.id ? { ...item, ...changed } : item,
        ),
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Sharing permissions could not be updated.",
      );
    } finally {
      setSaving("");
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="THE RIGHT HELP. THE RIGHT PERMISSIONS."
        title="People & permissions"
        description="Choose who can help and exactly what they can see or do."
      />
      <div className="notice">
        <ShieldCheck size={20} />
        <div>
          <strong>You stay in control</strong>
          <p>
            Sharing records does not automatically allow someone to approve
            reminders or arrangements.
          </p>
        </div>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <section className="card">
        {grants.length === 0 && (
          <Empty icon={HeartHandshake} title="No authorized care partners">
            Ask your clinician to add a care partner before managing access.
          </Empty>
        )}
        {grants.map((grant) => (
          <div key={grant.id} className="sharing-grant">
            <div className="person-permission">
              <span className="avatar">
                {grant.partner_email.slice(0, 2).toUpperCase()}
              </span>
              <div className="grow">
                <h2>{grant.partner_email}</h2>
                <p>Authorized care partner</p>
              </div>
              <Badge tone={grant.status === "active" ? "green" : "neutral"}>
                {grant.status}
              </Badge>
            </div>
            <div className="permission-line">
              <div>
                <h3>Reviewed summaries and visit questions</h3>
                <p>View shared records and help prepare questions.</p>
              </div>
              <span>{grant.can_view_records ? "Allowed" : "Revoked"}</span>
            </div>
            <div className="permission-line">
              <div>
                <h3>Approve arrangements</h3>
                <p>Separate delegation for exact action approvals.</p>
              </div>
              <label className="switch-label">
                <input
                  type="checkbox"
                  checked={grant.can_approve_actions}
                  disabled={grant.status !== "active" || saving === grant.id}
                  onChange={(event) =>
                    void change(grant, {
                      can_approve_actions: event.target.checked,
                    })
                  }
                />
                <span>
                  {grant.can_approve_actions ? "Allowed" : "Not delegated"}
                </span>
              </label>
            </div>
            <div className="bottom-actions">
              <span className="small muted">
                Stored permission version {grant.version}
              </span>
              <button
                className="button secondary"
                disabled={grant.status !== "active" || saving === grant.id}
                onClick={() => void change(grant, { status: "revoked" })}
              >
                {saving === grant.id ? "Saving…" : "Revoke access"}
              </button>
            </div>
          </div>
        ))}
      </section>
    </>
  );
}
