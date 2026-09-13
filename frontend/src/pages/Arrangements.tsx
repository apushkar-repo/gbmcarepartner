import { useEffect, useState } from "react";
import {
  CalendarDays,
  Check,
  Download,
  MapPin,
  ScanLine,
  TestTube2,
} from "lucide-react";
import { Badge, Empty, PageHeading } from "../components";
import {
  createArrangement,
  getMockOptions,
  listArrangements,
  preparationCalendarUrl,
  updateArrangement,
  type Arrangement,
  type ArrangementType,
} from "../api";

const labels: Record<ArrangementType, string> = {
  appointment: "Clinic appointment",
  travel: "Travel",
  lab: "Laboratory appointment",
  imaging: "Imaging appointment",
};
const statusLabels: Record<Arrangement["status"], string> = {
  awaiting_information: "Details needed",
  awaiting_approval: "Ready for review",
  confirmed: "Added to schedule",
  cancelled: "Cancelled",
};

function ArrangementIcon({ type }: { type: ArrangementType }) {
  if (type === "travel") return <MapPin size={20} />;
  if (type === "lab") return <TestTube2 size={20} />;
  if (type === "imaging") return <ScanLine size={20} />;
  return <CalendarDays size={20} />;
}

export function Arrangements() {
  const patientId = sessionStorage.getItem("carebridge.patientId");
  const role = sessionStorage.getItem("carebridge.role");
  const [items, setItems] = useState<Arrangement[]>([]);
  const [type, setType] = useState<ArrangementType>("appointment");
  const [option, setOption] = useState<Record<string, string | number> | null>(
    null,
  );
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const refresh = () =>
    patientId
      ? listArrangements(patientId)
          .then(setItems)
          .catch((e) => setError(e.message))
      : Promise.resolve();

  useEffect(() => {
    void refresh();
  }, [patientId]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const options = await getMockOptions(type);
      setOption(options[0] ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Options could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  async function save() {
    if (!patientId || !option) return;
    setLoading(true);
    try {
      const created = await createArrangement(patientId, type, option);
      setItems((current) => [created, ...current]);
      setOption(null);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Arrangement could not be saved.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function act(item: Arrangement, action: "approve" | "cancel") {
    if (!patientId) return;
    setLoading(true);
    try {
      const changed = await updateArrangement(patientId, item, action);
      setItems((current) =>
        current.map((entry) => (entry.id === changed.id ? changed : entry)),
      );
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Arrangement could not be updated.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PageHeading
        eyebrow="YOUR NEXT STEPS"
        title="Preparation actions"
        description="Review actions identified from approved visit summaries and approve each proposal before it is added to your schedule."
      />
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <section className="card">
        <div className="section-heading">
          <div>
            <h2>Actions from your visit summaries</h2>
            <p className="small muted">
              CareBridge coordinates documented needs with clinic, laboratory,
              and imaging services.
            </p>
          </div>
          <span className="count-pill">{items.length}</span>
        </div>
        {items.length === 0 ? (
          <Empty icon={CalendarDays} title="No preparation actions yet">
            Build and approve a preparation checklist first. Actions supported
            by the summary will appear here for review.
          </Empty>
        ) : (
          items.map((item) => (
            <article className="arrangement-row" key={item.id}>
              <span className="metric-icon sage">
                <ArrangementIcon type={item.action_type} />
              </span>
              <div className="grow">
                <h3>{labels[item.action_type]}</h3>
                <p>
                  {Object.entries(item.payload)
                    .filter(
                      ([key]) =>
                        key !== "missing_inputs" && key !== "simulation",
                    )
                    .map(
                      ([key, value]) =>
                        `${key.replaceAll("_", " ")}: ${String(value)}`,
                    )
                    .join(" · ")}
                </p>
                {item.source_version_ids.length > 0 && (
                  <p className="source-ref">
                    Source:{" "}
                    {item.source_labels.join(" · ") ||
                      `${item.source_version_ids.length} approved summary version${item.source_version_ids.length === 1 ? "" : "s"}`}
                  </p>
                )}
                {item.source_version_ids.length === 0 && (
                  <p className="source-ref">Requested directly by the user</p>
                )}
                {item.status === "awaiting_information" && (
                  <p className="blocked-text">
                    Missing:{" "}
                    {((item.payload.missing_inputs as string[]) ?? []).join(
                      ", ",
                    )}
                  </p>
                )}
                {item.provider_receipt && (
                  <p>
                    <strong>Confirmation reference:</strong>{" "}
                    {item.provider_receipt}
                  </p>
                )}
              </div>
              <Badge
                tone={
                  item.status === "confirmed"
                    ? "green"
                    : item.status === "awaiting_information"
                      ? "amber"
                      : "neutral"
                }
              >
                {statusLabels[item.status]}
              </Badge>
              <div className="bottom-actions">
                {item.status === "awaiting_approval" && (
                  <button
                    className="button primary"
                    disabled={
                      loading || !(role === "patient" || role === "partner")
                    }
                    onClick={() => void act(item, "approve")}
                  >
                    <Check size={16} /> Approve exact terms
                  </button>
                )}
                {!["cancelled", "confirmed"].includes(item.status) && (
                  <button
                    className="text-button danger"
                    disabled={loading}
                    onClick={() => void act(item, "cancel")}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </article>
          ))
        )}
        {patientId && items.some((item) => item.status === "confirmed") && (
          <a
            className="button secondary"
            href={preparationCalendarUrl(patientId)}
            download
          >
            <Download size={17} /> Download preparation calendar
          </a>
        )}
      </section>
      <section className="card">
        <div className="section-heading">
          <h2>Find another option</h2>
          <Badge tone="blue">Available services</Badge>
        </div>
        <div className="arrangement-controls">
          <select
            aria-label="Arrangement type"
            value={type}
            onChange={(e) => {
              setType(e.target.value as ArrangementType);
              setOption(null);
            }}
          >
            <option value="appointment">Clinic appointment</option>
            <option value="travel">Travel</option>
            <option value="lab">Laboratory appointment</option>
            <option value="imaging">Imaging appointment</option>
          </select>
          <button
            className="button secondary"
            disabled={loading}
            onClick={load}
          >
            Check availability
          </button>
        </div>
        {option && (
          <div className="approval-summary">
            <h3>{labels[type]}</h3>
            <dl>
              {Object.entries(option).map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
            </dl>
            {type === "travel" && (
              <label>
                Patient-approved pickup
                <input
                  value={String(option.pickup)}
                  onChange={(e) =>
                    setOption({ ...option, pickup: e.target.value })
                  }
                />
              </label>
            )}
            <button
              className="button primary"
              disabled={loading}
              onClick={save}
            >
              Save exact proposal
            </button>
          </div>
        )}
      </section>
    </>
  );
}
