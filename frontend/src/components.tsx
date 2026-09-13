import { useEffect, useRef, type ReactNode } from "react";
import { ArrowUpRight, X, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";

export function Brand() {
  return (
    <span className="brand">
      <svg viewBox="0 0 36 36" aria-hidden="true">
        <path d="M6 28V17a12 12 0 0 1 24 0v11M12 28V17a6 6 0 0 1 12 0v11" />
      </svg>
      <span>
        carebridge<span className="brand-dot">.</span>
      </span>
    </span>
  );
}
export function Badge({
  children,
  tone = "green",
}: {
  children: ReactNode;
  tone?: "green" | "amber" | "neutral" | "blue";
}) {
  return (
    <span className={`badge ${tone}`}>
      <span aria-hidden="true" />
      {children}
    </span>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
      </div>
      {children}
    </div>
  );
}
export function Empty({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <Icon size={30} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function TextLink({
  to,
  children,
}: {
  to: string;
  children: ReactNode;
}) {
  return (
    <Link className="text-link" to={to}>
      {children}
      <ArrowUpRight size={16} />
    </Link>
  );
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const dialog = ref.current!;
    dialog.showModal();
    return () => {
      dialog.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="modal-heading">
        <h2>{title}</h2>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function SourcePaper() {
  return (
    <div className="source-paper">
      <div className="paper-header">
        <span>FIELDSTONE CLINIC</span>
        <span>Visit record</span>
      </div>
      <h3>Visit summary</h3>
      <p className="paper-date">September 8, 2026 · Maya Patel</p>
      <div className="paper-rule" />
      <p>We reviewed the questions brought to today’s appointment.</p>
      <h4>Before your next visit</h4>
      <p className="source-highlight">
        Bring previous visit reports and a list of questions.
      </p>
      <h4>Next appointment</h4>
      <p className="source-highlight">September 24, 2026</p>
      <p className="paper-annotation">
        Time needs confirmation from the clinic.
      </p>
      <div className="paper-sign">M. Ellis</div>
      <div className="paper-footer">
        Visit summary source<span>1 / 1</span>
      </div>
    </div>
  );
}
