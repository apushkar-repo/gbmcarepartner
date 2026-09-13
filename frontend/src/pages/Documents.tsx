import { useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  FileText,
  Info,
  Plus,
  RotateCw,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import { Badge, Modal, PageHeading, SourcePaper } from "../components";
import { useCare } from "../context";
import {
  getExtractionResult,
  indexPublishedSummary,
  documentContentUrl,
  processExtraction,
  publishExtraction,
  listPatientSummaries,
  type PublishedSummary,
  saveTranscriptCorrection,
  uploadDocument,
} from "../api";
import { markdownToPlainText } from "../utils/plainText";

export function Documents() {
  const [summaries, setSummaries] = useState<PublishedSummary[]>([]);
  const [error, setError] = useState("");
  const patientId = sessionStorage.getItem("carebridge.patientId");
  useEffect(() => {
    if (patientId)
      listPatientSummaries(patientId)
        .then(setSummaries)
        .catch((e) => setError(e.message));
  }, [patientId]);
  return (
    <>
      <PageHeading
        eyebrow="YOUR RECORDS"
        title="Visit summaries"
        description="Approved visit summaries are loaded from the CareBridge API."
      />
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {!patientId && (
        <div className="empty">
          <FileText size={30} />
          <h2>Select a patient first</h2>
          <p>Return to Assigned patients and choose a patient.</p>
        </div>
      )}
      {patientId && summaries.length === 0 && !error && (
        <div className="empty">
          <FileText size={30} />
          <h2>No saved summaries</h2>
          <p>Approved summaries will appear here.</p>
        </div>
      )}
      <div className="document-grid">
        {summaries.map((summary) => (
          <article className="card document-card" key={summary.id}>
            <div className="mini-paper reviewed">
              <FileText size={45} />
              <span>VERSION {summary.version}</span>
            </div>
            <Badge>Approved</Badge>
            <h2>{summary.filename}</h2>
            <p>
              {markdownToPlainText(summary.payload.text).slice(0, 180)}
              {markdownToPlainText(summary.payload.text).length > 180
                ? "…"
                : ""}
            </p>
            <div className="card-meta">
              Saved {new Date(summary.created_at).toLocaleString()}
            </div>
            <Link
              className="button secondary wide"
              to={`/app/summaries/${summary.id}`}
            >
              Open summary
              <ArrowRight size={17} />
            </Link>
          </article>
        ))}
      </div>
    </>
  );
}

export function PublishedSummaryDetail() {
  const { versionId } = useParams();
  const patientId = sessionStorage.getItem("carebridge.patientId");
  const [summary, setSummary] = useState<PublishedSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!patientId || !versionId) {
      setLoading(false);
      return;
    }
    listPatientSummaries(patientId)
      .then((items) => {
        const selected = items.find((item) => item.id === versionId);
        if (!selected) throw new Error("This visit summary was not found.");
        setSummary(selected);
      })
      .catch((reason) =>
        setError(
          reason instanceof Error
            ? reason.message
            : "The visit summary could not be loaded.",
        ),
      )
      .finally(() => setLoading(false));
  }, [patientId, versionId]);

  if (loading) return <p className="loading-line">Loading visit summary…</p>;
  if (error || !summary)
    return (
      <div className="empty">
        <FileText size={30} />
        <h1>Summary unavailable</h1>
        <p>{error || "Select a patient and try again."}</p>
        <Link to="/app/home">Back to overview</Link>
      </div>
    );

  return (
    <>
      <Link className="back-link" to="/app/home">
        <ArrowLeft size={16} />
        Back to overview
      </Link>
      <PageHeading
        eyebrow="VISIT SUMMARY"
        title={summary.filename}
        description={`Reviewed ${new Date(summary.created_at).toLocaleString()}`}
      >
        <Badge tone="green">Approved</Badge>
      </PageHeading>
      <div className="review-grid">
        <section className="source-container">
          <div className="section-heading">
            <h2>Original document</h2>
            <span className="small muted">Version {summary.version}</span>
          </div>
          <iframe
            className="document-frame"
            src={documentContentUrl(summary.document_id)}
            title={`Original document for ${summary.filename}`}
          />
        </section>
        <section className="card review-fields">
          <div className="section-heading">
            <h2>Reviewed summary</h2>
            <FileText size={20} />
          </div>
          <div className="summary-text">
            {markdownToPlainText(summary.payload.text)}
          </div>
          <Link className="button primary wide" to="/app/ask">
            Ask a question about this summary
            <ArrowRight size={17} />
          </Link>
        </section>
      </div>
    </>
  );
}
export function Capture() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const patientId = searchParams.get("patientId") ?? undefined;
  const patientName = searchParams.get("patientName");
  const [files, setFiles] = useState<File[]>([]);
  const [urls, setUrls] = useState<string[]>([]);
  const [rotation, setRotation] = useState<Record<number, number>>({});
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [receipt, setReceipt] = useState<string[]>([]);
  useEffect(() => {
    if (patientId) sessionStorage.setItem("carebridge.patientId", patientId);
  }, [patientId]);
  useEffect(() => {
    const next = files.map((f) => URL.createObjectURL(f));
    setUrls(next);
    return () => next.forEach(URL.revokeObjectURL);
  }, [files]);
  function add(list: FileList | null) {
    if (!list) return;
    const incoming = Array.from(list);
    if (
      incoming.some(
        (f) =>
          !["image/png", "image/jpeg", "application/pdf"].includes(f.type) ||
          f.size > 10 * 1024 * 1024,
      )
    ) {
      setError("Choose JPG, PNG, or PDF files up to 10 MB each.");
      return;
    }
    if (files.length + incoming.length > 5) {
      setError("You can upload up to five files at a time.");
      return;
    }
    setFiles((s) => [...s, ...incoming]);
    setError("");
  }
  async function sendToApi() {
    if (!files.length || uploading) return;
    setUploading(true);
    setError("");
    try {
      const results = await Promise.all(
        files.map((file) => uploadDocument(file, patientId)),
      );
      const processed = await Promise.allSettled(
        results.map((r) => processExtraction(r.extraction_job_id)),
      );
      setReceipt(
        results.map((r, i) =>
          processed[i].status === "fulfilled"
            ? `${r.filename} · extraction completed (${processed[i].value.pages ?? 0} pages)`
            : `${r.filename} · uploaded; extraction is waiting for OCR configuration`,
        ),
      );
      const completed = processed.findIndex(
        (result) => result.status === "fulfilled",
      );
      if (completed >= 0)
        navigate(`/app/documents/ocr/${results[completed].extraction_job_id}`);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The upload could not be completed.",
      );
    } finally {
      setUploading(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="START WITH THE ORIGINAL"
        title="Add a visit summary"
        description={
          patientName
            ? `Add a summary for ${patientName}. Take a photo or upload a file.`
            : "Take a photo or upload a summary file. Include every page and keep the writing in view."
        }
      />
      <div className="notice">
        <ShieldCheck size={20} />
        <div>
          <strong>Keep patient information protected</strong>
          <p>
            Files are sent securely to CareBridge for text extraction. Use
            sample data in this hackathon environment.
          </p>
        </div>
      </div>
      <section className="card capture-card">
        <label
          className="dropzone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            add(e.dataTransfer.files);
          }}
        >
          <span className="upload-circle">
            <Upload size={30} />
          </span>
          <h2>Drop your pages here</h2>
          <p>Or choose files from your device.</p>
          <span className="button secondary">
            Choose files
            <Plus size={17} />
          </span>
          <small>JPG, PNG, PDF · Up to 10 MB per file · Maximum 5 files</small>
          <input
            type="file"
            aria-label="Choose visit summary files"
            multiple
            accept="image/jpeg,image/png,application/pdf"
            onChange={(e) => {
              add(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
        <label className="button secondary">
          <Upload size={17} />
          Use camera
          <input
            className="sr-only"
            type="file"
            accept="image/*"
            capture="environment"
            aria-label="Take a photo of a visit summary"
            onChange={(event) => {
              add(event.target.files);
              event.target.value = "";
            }}
          />
        </label>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <div className="upload-grid">
          {files.map((f, i) => (
            <div className="upload-preview" key={`${f.name}-${i}`}>
              {f.type.startsWith("image/") ? (
                <img
                  src={urls[i]}
                  alt={`Local preview of page ${i + 1}`}
                  style={{ transform: `rotate(${rotation[i] || 0}deg)` }}
                />
              ) : (
                <div className="pdf-preview">
                  <FileText size={34} />
                  <span>PDF selected · Preview unavailable</span>
                </div>
              )}
              <strong>{f.name}</strong>
              <div className="split">
                <span>File {i + 1}</span>
                <div>
                  {f.type.startsWith("image/") && (
                    <button
                      className="icon-button"
                      aria-label={`Rotate file ${i + 1}`}
                      onClick={() =>
                        setRotation((r) => ({
                          ...r,
                          [i]: ((r[i] || 0) + 90) % 360,
                        }))
                      }
                    >
                      <RotateCw size={17} />
                    </button>
                  )}
                  <button
                    className="icon-button"
                    aria-label={`Remove file ${i + 1}`}
                    onClick={() => {
                      setFiles((s) => s.filter((_, n) => n !== i));
                      setRotation({});
                    }}
                  >
                    <X size={17} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="capture-help">
          <h3>A clearer page makes review easier</h3>
          <p>
            Use even lighting, include all edges, and photograph one page at a
            time. Quality checks will be added with the document backend.
          </p>
        </div>
        {receipt.length > 0 && (
          <div className="notice compact">
            <Info size={18} />
            <p>
              Uploaded to the API:
              <br />
              {receipt.join("\n")}
            </p>
          </div>
        )}
      </section>
      <div className="bottom-actions">
        <Link className="button secondary" to="/app/documents">
          <ArrowLeft size={17} />
          Back to summaries
        </Link>
        <button
          className="button secondary"
          onClick={sendToApi}
          disabled={!files.length || uploading}
        >
          {uploading
            ? "Extracting visit summary…"
            : "Upload and extract summary"}
        </button>
      </div>
    </>
  );
}

export function ExtractionReview() {
  const { jobId } = useParams();
  const [text, setText] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [approval, setApproval] = useState(false);
  const [published, setPublished] = useState("");
  const [savedVersion, setSavedVersion] = useState<number | null>(null);
  useEffect(() => {
    if (!jobId) return;
    getExtractionResult(jobId)
      .then((result) => {
        setText(markdownToPlainText(result.text));
        setDocumentId(result.document_id);
        if (result.patient_id)
          sessionStorage.setItem("carebridge.patientId", result.patient_id);
      })
      .catch((e) =>
        setError(
          e instanceof Error
            ? e.message
            : "The extraction result could not load.",
        ),
      );
  }, [jobId]);
  async function extractAgain() {
    if (!jobId || extracting) return;
    setExtracting(true);
    setError("");
    try {
      await processExtraction(jobId);
      const result = await getExtractionResult(jobId);
      setText(markdownToPlainText(result.text));
      setApproval(false);
      setSavedVersion(null);
      setPublished("");
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "The document could not be extracted again.",
      );
    } finally {
      setExtracting(false);
    }
  }
  async function saveCorrections() {
    if (!jobId) return;
    setSaving(true);
    try {
      const result = await saveTranscriptCorrection(jobId, text);
      setSavedVersion(result.version);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The correction could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  }
  async function publish() {
    if (!jobId || !approval) return;
    setSaving(true);
    setError("");
    try {
      const result = await publishExtraction(
        jobId,
        text,
        "Patient and authorized record viewers",
      );
      const indexed = await indexPublishedSummary(result.id);
      setPublished(
        `Version ${result.version} published; ${indexed.status.replaceAll("_", " ")}.`,
      );
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Publication could not be completed.",
      );
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="REVIEW THE EXTRACTED RECORD"
        title="Review the visit summary"
        description="Compare the uploaded document with the full extracted text. Edit the transcript before saving and approving it."
      />
      {error ? (
        <div className="notice" role="alert">
          <Info size={20} />
          <p>{error}</p>
        </div>
      ) : (
        <div className="review-grid extraction-review-grid">
          <section className="source-container">
            <div className="section-heading">
              <h2>Uploaded document</h2>
              <span className="small muted">Original source</span>
            </div>
            {documentId && (
              <img
                className="source-paper extraction-source-preview"
                src={documentContentUrl(documentId)}
                alt="Uploaded visit summary"
              />
            )}
          </section>
          <section className="card review-fields">
            <div className="section-heading">
              <h2>Extracted text</h2>
              <Badge tone="amber">Needs review</Badge>
            </div>
            <button
              className="button secondary extraction-retry"
              type="button"
              onClick={extractAgain}
              disabled={extracting || saving}
            >
              <RotateCw size={16} />
              {extracting ? "Extracting again…" : "Improve extraction"}
            </button>
            <label htmlFor="reviewed-transcript">Full transcript</label>
            <textarea
              id="reviewed-transcript"
              rows={22}
              value={text}
              onChange={(event) => {
                setText(event.target.value);
                setApproval(false);
                setSavedVersion(null);
              }}
            />
            <div className="notice compact">
              <Info size={18} />
              <p>
                OCR formatting is converted to plain text for review. Any edit
                is saved as a new transcript version.
              </p>
            </div>
            <button
              className="button primary wide"
              onClick={saveCorrections}
              disabled={saving || !text.trim()}
            >
              {saving ? "Saving corrections…" : "Save corrections"}
            </button>
            {savedVersion && (
              <p className="small muted" role="status">
                Transcript version {savedVersion} saved.
              </p>
            )}
            <label className="check-label">
              <input
                type="checkbox"
                checked={approval}
                onChange={(event) => setApproval(event.target.checked)}
              />
              I approve this exact transcript for the patient and authorized
              care partners.
            </label>
            <button
              className="button secondary wide"
              onClick={publish}
              disabled={
                saving || !approval || !text.trim() || savedVersion === null
              }
            >
              {saving ? "Publishing…" : "Publish reviewed version"}
            </button>
            {published && (
              <div role="status">
                <p className="small muted">{published}</p>
                <Link className="button primary wide" to="/app/documents">
                  View saved summaries
                </Link>
              </div>
            )}
          </section>
        </div>
      )}
      <Link className="button secondary" to="/app/capture">
        Back to upload
      </Link>
    </>
  );
}
export function DocumentReview() {
  const { id } = useParams();
  const { state, update, can, persona } = useCare();
  const historical = id === "reviewed";
  const [date, setDate] = useState(state.fieldDate);
  const [note, setNote] = useState(state.fieldNote);
  const [dateConfirmed, setDateConfirmed] = useState(false);
  const [noteConfirmed, setNoteConfirmed] = useState(false);
  const [unreadable, setUnreadable] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [approval, setApproval] = useState(false);
  const clinical = can("clinical");
  if (!["draft", "reviewed"].includes(id ?? ""))
    return (
      <div className="empty">
        <h1>Summary not available</h1>
        <Link to="/app/documents">Back to summaries</Link>
      </div>
    );
  function publish() {
    if (!approval || !dateConfirmed || !noteConfirmed || !date || !note.trim())
      return;
    const type = clinical
      ? "Clinician-approved"
      : persona?.role === "partner"
        ? "Care-partner-confirmed transcription"
        : "Patient-confirmed transcription";
    update(
      (s) => ({
        ...s,
        fieldDate: date,
        fieldNote: note,
        published: true,
        publicationType: type,
        reminder: {
          ...s.reminder,
          version: s.reminder.version + 1,
          approvedVersion: null,
          status:
            s.reminder.status === "Scheduled · simulated"
              ? "Paused · needs reapproval"
              : "Awaiting approval",
        },
      }),
      "Document version published",
      `${type} · Related reminder approval invalidated · Search indexing not connected`,
    );
    setPublishing(false);
    setApproval(false);
  }
  return (
    <>
      <Link className="back-link" to="/app/documents">
        <ArrowLeft size={16} />
        Visit summaries
      </Link>
      <PageHeading
        eyebrow="THE ORIGINAL, ALWAYS WITHIN REACH"
        title={historical ? "September 8 summary" : "Review your summary"}
        description={
          historical
            ? "A reviewed visit record. Source wording is preserved below."
            : "Check the wording and date. Anything unclear can stay unresolved."
        }
      >
        <Badge tone={historical || state.published ? "green" : "amber"}>
          {historical
            ? "Patient-reviewed"
            : state.published
              ? state.publicationType
              : "Awaiting your review"}
        </Badge>
      </PageHeading>
      <div className="review-grid">
        <section className="source-container">
          <div className="section-heading">
            <h2>Original source</h2>
            <span className="small muted">Page 1</span>
          </div>
          <SourcePaper />
        </section>
        <section className="card review-fields">
          <div className="section-heading">
            <h2>{historical ? "Reviewed details" : "Check the details"}</h2>
            <FileText size={20} />
          </div>
          <div className="field-group">
            <span className="field-index">01 / TODAY’S SUMMARY</span>
            <p>Questions brought to the visit were reviewed.</p>
            <span className="source-ref">Source: page 1, first paragraph</span>
          </div>
          <div className="field-group">
            <span className="field-index">02 / WRITTEN RECOMMENDATION</span>
            <label htmlFor="recommendation">Original wording</label>
            <textarea
              id="recommendation"
              rows={3}
              value={
                historical
                  ? "Bring previous visit reports and a list of questions."
                  : note
              }
              readOnly={historical}
              onChange={(e) => {
                setNote(e.target.value);
                setNoteConfirmed(false);
              }}
            />
            <span className="source-ref">
              Source: page 1, “Before your next visit”
            </span>
            {!historical && (
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={noteConfirmed}
                  onChange={(e) => setNoteConfirmed(e.target.checked)}
                />
                I reviewed this transcription against the source.
              </label>
            )}
          </div>
          <div className="field-group">
            <span className="field-index">03 / NEXT APPOINTMENT</span>
            <label htmlFor="visit-date">Visit date</label>
            <input
              id="visit-date"
              type="date"
              value={historical ? "2026-09-24" : date}
              readOnly={historical}
              disabled={unreadable}
              onChange={(e) => {
                setDate(e.target.value);
                setDateConfirmed(false);
              }}
            />
            <p className="inline-note">
              <Info size={16} />
              No appointment time is included, so it remains unknown.
            </p>
            {!historical && (
              <>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={dateConfirmed}
                    disabled={unreadable || !date}
                    onChange={(e) => setDateConfirmed(e.target.checked)}
                  />
                  I reviewed this date against the source.
                </label>
                <button
                  className="text-button"
                  onClick={() => {
                    setUnreadable(!unreadable);
                    setDateConfirmed(false);
                  }}
                >
                  {" "}
                  {unreadable
                    ? "Return to date review"
                    : "Mark date unreadable"}
                </button>
                {unreadable && (
                  <p className="form-error">
                    Date unresolved. Publication in this simplified preview
                    waits for date review. The backend will support partial
                    publication.
                  </p>
                )}
              </>
            )}
          </div>
          {!historical && (
            <>
              <div className="notice compact">
                <ShieldCheck size={18} />
                <p>
                  {clinical
                    ? "Clinical approval is available for this assigned patient only."
                    : "Your review confirms transcription, not the clinical correctness of the instructions."}
                </p>
              </div>
              <button
                className="button primary wide"
                disabled={
                  !dateConfirmed || !noteConfirmed || !date || !note.trim()
                }
                onClick={() => setPublishing(true)}
              >
                Review publication
                <ArrowRight size={17} />
              </button>
              {state.published && (
                <p className="small muted">
                  Saved in memory · Publication preview only. Indexing is not
                  connected.
                </p>
              )}
            </>
          )}
        </section>
      </div>
      {publishing && (
        <Modal
          title="Publish this exact version?"
          onClose={() => setPublishing(false)}
        >
          <div className="approval-summary">
            <p className="eyebrow">PRIVATE WORKSPACE PUBLICATION</p>
            <h3>
              {clinical
                ? "Clinician-approved record"
                : persona?.role === "partner"
                  ? "Care-partner-confirmed transcription"
                  : "Patient-confirmed transcription"}
            </h3>
            <p>{note}</p>
            <dl>
              <dt>Visit date</dt>
              <dd>{date}</dd>
              <dt>Audience</dt>
              <dd>Maya and her authorized record viewers</dd>
              <dt>Appointment time</dt>
              <dd>Unknown</dd>
            </dl>
          </div>
          <p className="muted">
            Publication does not approve a reminder or booking. Changes
            invalidate related reminder approval in this demo.
          </p>
          <label className="check-label">
            <input
              type="checkbox"
              checked={approval}
              onChange={(e) => setApproval(e.target.checked)}
            />
            I approve this exact wording, date, and audience.
          </label>
          <button
            className="button primary wide"
            disabled={!approval}
            onClick={publish}
          >
            Publish in demo
          </button>
        </Modal>
      )}
    </>
  );
}
