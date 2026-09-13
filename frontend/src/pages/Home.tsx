import {
  ArrowRight,
  ArrowUpRight,
  Bell,
  Check,
  ChevronRight,
  Clock3,
  FileText,
  MapPin,
  MessageCircle,
  Plus,
  Sparkles,
  Heart,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { Badge, PageHeading, TextLink } from "../components";
import { useCare } from "../context";
import { visitDateParts } from "../domain";
import {
  getCurrentReminder,
  listCareQuestions,
  listPatientSummaries,
  type PersistedReminder,
  type PublishedSummary,
} from "../api";

export function Home() {
  const { persona, state, update } = useCare();
  const [apiSummaries, setApiSummaries] = useState<PublishedSummary[]>([]);
  const [reminder, setReminder] = useState<PersistedReminder | null>(null);
  const patientId = sessionStorage.getItem("carebridge.patientId");
  useEffect(() => {
    if (patientId) {
      listPatientSummaries(patientId)
        .then(setApiSummaries)
        .catch(() => setApiSummaries([]));
      listCareQuestions(patientId)
        .then((questions) =>
          update((current) => ({
            ...current,
            questions: questions.map((question) => ({
              id: question.id,
              text: question.text,
              original: question.original_text,
              source: question.source_label,
              status:
                question.status === "follow_up_needed"
                  ? "Follow-up needed"
                  : ((question.status.charAt(0).toUpperCase() +
                      question.status.slice(1)) as
                      "Open" | "Discussed" | "Resolved"),
              clinicianResponse: question.clinician_response ?? undefined,
            })),
          })),
        )
        .catch(() => undefined);
      getCurrentReminder(patientId)
        .then(setReminder)
        .catch(() => setReminder(null));
    }
  }, [patientId]);
  const open = state.questions.filter((q) => q.status === "Open").length;
  if (!state.fieldDate)
    return (
      <>
        <PageHeading
          eyebrow="YOUR CARE WORKSPACE"
          title={
            apiSummaries.length
              ? "Your approved visit summaries"
              : "No visit summaries yet"
          }
          description={
            apiSummaries.length
              ? "Your clinician has published the following summaries."
              : "An approved visit summary will appear here after your clinician publishes it."
          }
        />
        {apiSummaries.length === 0 ? (
          <section className="card">
            <h2>Your workspace is ready</h2>
            <p className="muted">There are no approved summaries to show.</p>
          </section>
        ) : (
          <section className="card recent-card">
            {apiSummaries.map((summary) => (
              <div className="document-row" key={summary.id}>
                <div className="document-icon">
                  <FileText size={25} />
                </div>
                <div className="grow">
                  <h3>{summary.filename}</h3>
                  <p>Version {summary.version} · Approved</p>
                </div>
                <Link
                  className="button secondary"
                  to={`/app/summaries/${summary.id}`}
                >
                  Open summary
                </Link>
              </div>
            ))}
          </section>
        )}
      </>
    );
  const visit = visitDateParts(state.fieldDate);
  return (
    <>
      <PageHeading
        eyebrow="YOUR EVERYDAY CARE COMPANION"
        title={
          persona?.role === "patient"
            ? "A little more clarity, Maya."
            : "A little more support for Maya."
        }
        description="Your notes, your questions, your next steps. All in one place."
      >
        <Link className="button primary" to="/app/capture">
          <Plus size={18} />
          Upload a summary
        </Link>
      </PageHeading>
      <section className="visit-hero">
        <div className="visit-hero-main">
          <div className="hero-eyebrow">
            <span className="light-dot" /> YOUR NEXT VISIT
          </div>
          <div className="hero-date">
            <div className="date-tile">
              <span>{visit.month.toUpperCase()}</span>
              <strong>{visit.day}</strong>
              <small>{visit.weekday.toUpperCase()}</small>
            </div>
            <div>
              <h2>
                A little preparation.
                <br />
                More room for your questions.
              </h2>
              <p>
                <MapPin size={15} />
                Fieldstone Clinic
              </p>
              <p>
                <Clock3 size={15} />
                Appointment time needs confirmation
              </p>
            </div>
          </div>
          <div className="hero-actions">
            <Link className="button cream" to="/app/visit">
              Prepare for this visit
              <ArrowRight size={17} />
            </Link>
            <span>{visit.full} · Date from reviewed summary</span>
          </div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="art-orbit orbit-one" />
          <div className="art-orbit orbit-two" />
          <div className="art-flower">
            <i />
            <i />
            <i />
            <i />
            <span>
              <Heart size={29} />
            </span>
          </div>
          <div className="art-note">
            <Check size={17} />
            <span>One step at a time</span>
          </div>
        </div>
      </section>
      <div className="metric-grid">
        <Link to="/app/documents" className="metric-card">
          <span className="metric-icon sage">
            <FileText size={22} />
          </span>
          <div>
            <strong>
              02 <span>Visit summaries</span>
            </strong>
            <p>
              {state.published
                ? "Two reviewed summaries"
                : "One reviewed, one ready to check"}
            </p>
          </div>
          <ArrowUpRight size={17} />
        </Link>
        <Link to="/app/visit" className="metric-card">
          <span className="metric-icon peach">
            <MessageCircle size={22} />
          </span>
          <div>
            <strong>
              {String(open).padStart(2, "0")} <span>Open questions</span>
            </strong>
            <p>A place for what’s on your mind</p>
          </div>
          <ArrowUpRight size={17} />
        </Link>
        <Link to="/app/reminders" className="metric-card">
          <span className="metric-icon lilac">
            <Bell size={22} />
          </span>
          <div>
            <strong>
              {reminder &&
              ["awaiting_approval", "awaiting_reapproval"].includes(
                reminder.status,
              )
                ? "01"
                : "00"}{" "}
              <span>To review</span>
            </strong>
            <p>
              {reminder?.status === "awaiting_approval"
                ? "A reminder needs your approval"
                : reminder?.status === "awaiting_reapproval"
                  ? "A changed reminder needs fresh approval"
                  : reminder?.status === "scheduled"
                    ? "Reminder scheduled · simulated"
                    : reminder?.status === "paused"
                      ? "Reminder paused"
                      : reminder?.status === "cancelled"
                        ? "Reminder cancelled"
                        : "No reminder created"}
            </p>
          </div>
          <ArrowUpRight size={17} />
        </Link>
      </div>
      <div className="dashboard-grid">
        <div className="dashboard-left">
          <section className="card">
            <div className="section-heading">
              <h2>Let’s take the next small step</h2>
              <span className="section-caption">MADE MANAGEABLE</span>
            </div>
            <Link className="next-step" to="/app/documents/draft/review">
              <span className="step-number">01</span>
              <div>
                <Badge tone={state.published ? "green" : "amber"}>
                  {state.published ? "Reviewed" : "Your review needed"}
                </Badge>
                <h3>
                  {state.published
                    ? "Revisit your latest summary"
                    : "Check your latest summary"}
                </h3>
                <p>
                  Review the written recommendations and confirm the next visit
                  date.
                </p>
              </div>
              <ChevronRight size={21} />
            </Link>
            <Link className="next-step" to="/app/visit">
              <span className="step-number">02</span>
              <div>
                <h3>Bring your questions together</h3>
                <p>
                  {open} saved questions for your next conversation. Add or edit
                  anytime.
                </p>
              </div>
              <ChevronRight size={21} />
            </Link>
            <Link className="next-step" to="/app/reminders">
              <span className="step-number">03</span>
              <div>
                <h3>Give yourself a gentle reminder</h3>
                <p>
                  Choose when and how. Nothing activates without your approval.
                </p>
              </div>
              <ChevronRight size={21} />
            </Link>
          </section>
          <section className="card recent-card">
            <div className="section-heading">
              <h2>Your recent summaries</h2>
              <TextLink to="/app/documents">View all</TextLink>
            </div>
            <div className="document-row">
              <div className="document-icon">
                <FileText size={25} />
              </div>
              <div className="grow">
                <h3>September 8 visit summary</h3>
                <p>Reviewed by Maya · 1 page</p>
              </div>
              <Badge>Patient-reviewed</Badge>
              <Link
                className="icon-button"
                aria-label="Open September 8 summary"
                to="/app/documents/reviewed/review"
              >
                <ArrowUpRight size={19} />
              </Link>
            </div>
            <div className="document-row">
              <div className="document-icon peach">
                <FileText size={25} />
              </div>
              <div className="grow">
                <h3>New summary draft</h3>
                <p>Visit summary · 1 page</p>
              </div>
              <Badge tone={state.published ? "green" : "amber"}>
                {state.published ? "Published" : "Needs review"}
              </Badge>
              <Link
                className="icon-button"
                aria-label="Open draft summary"
                to="/app/documents/draft/review"
              >
                <ArrowUpRight size={19} />
              </Link>
            </div>
          </section>
        </div>
        <div className="dashboard-right">
          <section className="ask-card">
            <div className="sparkle-box">
              <Sparkles size={22} />
            </div>
            <p className="eyebrow">MAKE SENSE OF YOUR NOTES</p>
            <h2>
              Your questions
              <br />
              deserve a place.
            </h2>
            <p>
              Look back at your summaries, find the source, and save a question
              for your next visit.
            </p>
            <Link className="suggestion-link" to="/app/ask">
              “What should I bring to my visit?”
              <ArrowUpRight size={17} />
            </Link>
            <TextLink to="/app/ask">Ask about your summaries</TextLink>
          </section>
          <section className="quiet-card">
            <span className="small-icon">
              <Heart size={20} />
            </span>
            <h3>You set the pace.</h3>
            <p>
              You can return to a draft later. An unclear detail stays unclear
              until it’s confirmed.
            </p>
            <span className="tiny-label">YOUR REVIEW. YOUR CHOICE.</span>
          </section>
        </div>
      </div>
    </>
  );
}
