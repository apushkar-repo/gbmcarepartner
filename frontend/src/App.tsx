import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  ArrowRight,
  Bell,
  CalendarDays,
  Check,
  ClipboardList,
  FileText,
  HeartHandshake,
  House,
  LogOut,
  Menu,
  MessageCircle,
  Settings2,
  ShieldCheck,
  Users,
  X,
  Activity as ActivityIcon,
} from "lucide-react";
import { Brand } from "./components";
import { useCare } from "./context";
import { personas, type Capability, type Role } from "./domain";
import {
  Home,
  Arrangements,
  Documents,
  Capture,
  DocumentReview,
  ExtractionReview,
  PublishedSummaryDetail,
  Ask,
  Visit,
  Reminders,
  ActivityPage,
  Sharing,
  Clinician,
  ClinicianQuestions,
  Helper,
  Reviewer,
  Operations,
} from "./pages";

function Login() {
  const { persona, login } = useCare();
  const [role, setRole] = useState<Role>("patient");
  const [patientId, setPatientId] = useState("");
  const [partnerEmail, setPartnerEmail] = useState("");
  const navigate = useNavigate();
  if (persona) return <Navigate to={persona.home} replace />;
  return (
    <main className="login-page">
      <div className="login-story">
        <Brand />
        <div className="story-content">
          <p className="eyebrow">A LITTLE CLARITY. A LITTLE MORE CONFIDENCE.</p>
          <h1>
            You don’t have to <br />
            keep track of <br />
            <em>everything.</em>
          </h1>
          <p>
            Your visit notes, your questions, and your next steps. <br />
            Together in one thoughtful space.
          </p>
          <div className="story-path">
            <span>
              <FileText size={19} />
              Understand
            </span>
            <i />
            <span>
              <MessageCircle size={19} />
              Ask
            </span>
            <i />
            <span>
              <CalendarDays size={19} />
              Prepare
            </span>
          </div>
        </div>
        <p className="story-footer">
          Made for patients. Shared with the people who help.
        </p>
        <div className="login-orbit" aria-hidden="true" />
      </div>
      <section className="login-form">
        <span className="preview-label">
          <span /> YOUR CARE, ORGANIZED
        </span>
        <h2>Welcome to CareBridge</h2>
        <p className="muted">
          Choose your role to continue to your CareBridge workspace.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sessionStorage.setItem("carebridge.role", role);
            if (role === "clinician") {
              sessionStorage.removeItem("carebridge.patientId");
              sessionStorage.setItem("carebridge.actorId", "demo-clinician");
            } else {
              sessionStorage.setItem("carebridge.patientId", patientId.trim());
              sessionStorage.setItem(
                "carebridge.actorId",
                role === "patient"
                  ? patientId.trim()
                  : partnerEmail.trim().toLowerCase(),
              );
            }
            login(role);
            navigate(personas.find((p) => p.role === role)!.home);
          }}
        >
          <fieldset className="persona-list">
            <legend className="sr-only">CareBridge role</legend>
            {personas.map((p) => (
              <label
                className={`persona-option ${role === p.role ? "selected" : ""}`}
                key={p.role}
              >
                <input
                  type="radio"
                  name="role"
                  value={p.role}
                  checked={role === p.role}
                  onChange={() => setRole(p.role)}
                />
                <span className="avatar small">{p.initials}</span>
                <span>
                  <strong>{p.label}</strong>
                  <small>{p.description}</small>
                </span>
                {role === p.role && <Check size={17} />}
              </label>
            ))}
          </fieldset>
          {role !== "clinician" && (
            <>
              <label htmlFor="workspace-patient-id">Patient ID</label>
              <input
                id="workspace-patient-id"
                value={patientId}
                onChange={(event) => setPatientId(event.target.value)}
                placeholder="CBP-XXXXXXXX"
                required
              />
              <p className="small muted">
                Use the patient ID provided by the treating clinician. This is
                temporary development access, not secure authentication.
              </p>
            </>
          )}
          {role === "partner" && (
            <>
              <label htmlFor="partner-email">
                Authorized care-partner email
              </label>
              <input
                id="partner-email"
                type="email"
                value={partnerEmail}
                onChange={(event) => setPartnerEmail(event.target.value)}
                required
              />
            </>
          )}
          <button className="button primary wide" type="submit">
            Enter CareBridge
            <ArrowRight size={17} />
          </button>
        </form>
        <div className="login-notice">
          <ShieldCheck size={18} />
          <p>
            Hackathon access does not provide production authentication.
            Uploaded documents may be processed by configured cloud services.
            Use sample data in this environment.
          </p>
        </div>
      </section>
    </main>
  );
}
const nav = [
  { to: "/app/home", name: "Overview", icon: House, cap: "prepare" },
  {
    to: "/app/clinician",
    name: "Assigned patients",
    icon: Users,
    cap: "clinical",
  },
  {
    to: "/app/clinician/questions",
    name: "Patient questions",
    icon: MessageCircle,
    cap: "clinical",
  },
  {
    to: "/app/ask",
    name: "Ask about your summaries",
    icon: MessageCircle,
    cap: "questions",
  },
  {
    to: "/app/visit",
    name: "Visit preparation",
    icon: ClipboardList,
    cap: "prepare",
  },
  { to: "/app/reminders", name: "Reminders", icon: Bell, cap: "prepare" },
  {
    to: "/app/arrangements",
    name: "Arrangements",
    icon: CalendarDays,
    cap: "prepare",
  },
  { to: "/app/tasks", name: "Shared tasks", icon: ClipboardList, cap: "tasks" },
  {
    to: "/app/review",
    name: "Evaluation review",
    icon: ShieldCheck,
    cap: "evaluate",
  },
  {
    to: "/app/operations",
    name: "Service overview",
    icon: Settings2,
    cap: "operate",
  },
] as const;

function Layout() {
  const { persona, logout, can, toast, notify, state } = useCare();
  const location = useLocation();
  const [menu, setMenu] = useState(false);
  const [mobile, setMobile] = useState(
    () => matchMedia("(max-width: 760px)").matches,
  );
  const sidebar = useRef<HTMLElement>(null);
  useEffect(() => {
    const media = matchMedia("(max-width: 760px)");
    const change = () => setMobile(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    if (!menu || !mobile) return;
    const nodes = () =>
      Array.from(
        sidebar.current!.querySelectorAll<HTMLElement>("a, button"),
      ).filter((n) => n.offsetParent !== null);
    nodes()[0]?.focus();
    const handle = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenu(false);
        document
          .querySelector<HTMLElement>('[aria-label="Open navigation"]')
          ?.focus();
      }
      if (e.key === "Tab") {
        const list = nodes(),
          first = list[0],
          last = list[list.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  }, [menu, mobile]);
  useEffect(() => {
    setMenu(false);
    document.getElementById("main-content")?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [location.pathname]);
  useEffect(() => {
    if (toast) {
      const id = window.setTimeout(() => notify(""), 5500);
      return () => clearTimeout(id);
    }
  }, [toast, notify]);
  if (!persona) return <Navigate to="/" replace />;
  const clinicalContext = can("records") || can("prepare");
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      {menu && (
        <button
          className="mobile-scrim"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        />
      )}
      <aside
        ref={sidebar}
        inert={mobile && !menu}
        aria-hidden={mobile && !menu ? true : undefined}
        className={`sidebar ${menu ? "open" : ""}`}
      >
        <div className="sidebar-brand">
          <Brand />
          <button
            className="icon-button mobile-only"
            aria-label="Close navigation"
            onClick={() => setMenu(false)}
          >
            <X />
          </button>
        </div>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <div className="workspace-card">
          <span className="avatar">
            {clinicalContext ? "MP" : persona.initials}
          </span>
          <span>
            <strong>
              {clinicalContext ? "Patient care workspace" : persona.label}
            </strong>
            <small>
              {clinicalContext
                ? "Connected care workspace"
                : "Limited role workspace"}
            </small>
          </span>
        </div>
        <nav
          aria-label="Main navigation"
          onClick={() => {
            setMenu(false);
            requestAnimationFrame(() =>
              document
                .getElementById("main-content")
                ?.focus({ preventScroll: true }),
            );
          }}
        >
          {nav
            .filter((n) => can(n.cap))
            .map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/app/clinician"}>
                <n.icon size={19} />
                <span>{n.name}</span>
                {n.to === "/app/visit" && (
                  <span className="nav-count">
                    {state.questions.filter((q) => q.status === "Open").length}
                  </span>
                )}
              </NavLink>
            ))}
          {(clinicalContext || can("records")) && (
            <NavLink to="/app/activity">
              <ActivityIcon size={19} />
              Activity
            </NavLink>
          )}
          {can("share") && (
            <NavLink to="/app/sharing">
              <HeartHandshake size={19} />
              People & permissions
            </NavLink>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="support-note">
            <span className="support-icon">
              <HeartHandshake size={23} />
            </span>
            <strong>A little help, one step at a time.</strong>
            <p>
              Keep your questions close. Your care team is the place for
              clinical advice.
            </p>
          </div>
          <button className="profile-button" onClick={logout}>
            <span className="avatar small">{persona.initials}</span>
            <span>
              <strong>{persona.name}</strong>
              <small>{persona.label} · Sign out</small>
            </span>
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <div className="app-main">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button mobile-only"
              aria-label="Open navigation"
              onClick={() => setMenu(true)}
            >
              <Menu size={23} />
            </button>
            <span className="topbar-context">
              {clinicalContext
                ? "Your care, connected"
                : "CareBridge workspace"}
            </span>
          </div>
          <div className="topbar-right">
            <span className="demo-pill">CareBridge</span>
            <span className="role-pill">{persona.label}</span>
            <span className="avatar small header-avatar">
              {persona.initials}
            </span>
          </div>
        </header>
        <div className="preview-bar">
          Hackathon environment <span>·</span> Provider bookings and messages
          are demonstrated within CareBridge.
        </div>
        <main id="main-content" className="content" tabIndex={-1}>
          <Outlet />
        </main>
        <footer className="app-footer">
          <Brand />
          <span>A little clarity for what’s next.</span>
          <span>Designed for care across the US and India</span>
        </footer>
      </div>
      <div
        className={`toast ${toast ? "visible" : ""}`}
        role="status"
        aria-live="polite"
      >
        {toast && (
          <>
            <Check size={18} />
            <span>{toast}</span>
            <button
              onClick={() => notify("")}
              aria-label="Dismiss notification"
            >
              <X size={16} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
function Guard({ cap, children }: { cap: Capability; children: ReactNode }) {
  const { can } = useCare();
  return can(cap) ? (
    children
  ) : (
    <div className="access-denied">
      <ShieldCheck size={36} />
      <h1>This view isn’t shared with your role</h1>
      <p>
        No record details are available here. Return to your permitted
        workspace.
      </p>
      <NavLink className="button secondary" to="/app">
        Back to my workspace
      </NavLink>
    </div>
  );
}
function Landing() {
  const { persona } = useCare();
  return <Navigate to={persona?.home ?? "/"} replace />;
}
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/app" element={<Layout />}>
        <Route index element={<Landing />} />
        <Route
          path="home"
          element={
            <Guard cap="prepare">
              <Home />
            </Guard>
          }
        />
        <Route
          path="documents"
          element={
            <Guard cap="records">
              <Documents />
            </Guard>
          }
        />
        <Route
          path="summaries/:versionId"
          element={
            <Guard cap="records">
              <PublishedSummaryDetail />
            </Guard>
          }
        />
        <Route
          path="capture"
          element={
            <Guard cap="records">
              <Capture />
            </Guard>
          }
        />
        <Route
          path="documents/:id/review"
          element={
            <Guard cap="records">
              <DocumentReview />
            </Guard>
          }
        />
        <Route
          path="documents/ocr/:jobId"
          element={
            <Guard cap="records">
              <ExtractionReview />
            </Guard>
          }
        />
        <Route
          path="ask"
          element={
            <Guard cap="questions">
              <Ask />
            </Guard>
          }
        />
        <Route
          path="visit"
          element={
            <Guard cap="prepare">
              <Visit />
            </Guard>
          }
        />
        <Route
          path="reminders"
          element={
            <Guard cap="prepare">
              <Reminders />
            </Guard>
          }
        />
        <Route
          path="arrangements"
          element={
            <Guard cap="prepare">
              <Arrangements />
            </Guard>
          }
        />
        <Route
          path="activity"
          element={
            <Guard cap="records">
              <ActivityPage />
            </Guard>
          }
        />
        <Route
          path="sharing"
          element={
            <Guard cap="share">
              <Sharing />
            </Guard>
          }
        />
        <Route
          path="clinician"
          element={
            <Guard cap="clinical">
              <Clinician />
            </Guard>
          }
        />
        <Route
          path="clinician/questions"
          element={
            <Guard cap="clinical">
              <ClinicianQuestions />
            </Guard>
          }
        />
        <Route
          path="tasks"
          element={
            <Guard cap="tasks">
              <Helper />
            </Guard>
          }
        />
        <Route
          path="review"
          element={
            <Guard cap="evaluate">
              <Reviewer />
            </Guard>
          }
        />
        <Route
          path="operations"
          element={
            <Guard cap="operate">
              <Operations />
            </Guard>
          }
        />
        <Route
          path="*"
          element={
            <div className="empty">
              <h1>Page not found</h1>
              <NavLink className="button secondary" to="/app">
                Back to my workspace
              </NavLink>
            </div>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
