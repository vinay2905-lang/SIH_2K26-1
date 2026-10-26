import {
  CalendarX, CircleCheck, CircleX, Clock, CloudOff, FileX, Loader, TriangleAlert, UserSearch, X,
} from "lucide-react";
import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useT } from "../i18n";

// --------------------------------------------------------------- format --
export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric" }).replace(/\//g, "-");
}

export function fmtDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return `${fmtDate(iso)}, ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })} IST`;
}

export function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Asia/Kolkata" });
}

export function ago(iso?: string | null): string {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 7 * 86400) return `${Math.floor(s / 86400)} d ago`;
  return fmtDate(iso);
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

// ---------------------------------------------------------------- chips --
const V: Record<string, [string, typeof CircleCheck, string]> = {
  VERIFIED: ["green", CircleCheck, "Verified"],
  MISMATCH: ["red", CircleX, "Mismatch"],
  EXPIRED: ["amber", CalendarX, "Expired"],
  PENDING: ["slate", Clock, "Pending"],
  SOURCE_UNAVAILABLE: ["slate", CloudOff, "Source unavailable"],
  MANUAL_REVIEW: ["purple", UserSearch, "Manual review"],
  MISSING: ["red", FileX, "Not uploaded"],
  OPTIONAL: ["slate", FileX, "Optional"],
  INCOMPLETE: ["amber", TriangleAlert, "Incomplete"],
  UNREADABLE: ["amber", TriangleAlert, "Unreadable"],
  PROCESSING: ["blue", Loader, "Reading…"],
  UPLOADED: ["green", CircleCheck, "Uploaded"],
};

export function StatusChip({ status, xs, text }: { status: string; xs?: boolean; text?: string }) {
  const t = useT();
  const [cls, Icon, label] = V[status] || ["slate", Clock, status];
  return (
    <span className={`chip ${cls}${xs ? " xs" : ""}`} title={label}>
      <Icon aria-hidden />
      {text || t(label)}
    </span>
  );
}

const SEV: Record<string, [string, string]> = {
  critical: ["solidred", "Critical"], high: ["red", "High"], warning: ["amber", "Warning"], info: ["slate", "Info"],
};

export function SeverityChip({ severity, xs = true }: { severity: string; xs?: boolean }) {
  const t = useT();
  const [cls, label] = SEV[severity] || ["slate", severity];
  return <span className={`chip ${cls}${xs ? " xs" : ""}`}>{t(label)}</span>;
}

const CAT: Record<string, [string, string]> = {
  MISSING_DOCUMENT: ["red", "Missing document"], EXPIRED_DOCUMENT: ["amber", "Expired document"],
  INCONSISTENCY: ["red", "Inconsistency"], ANOMALY: ["purple", "Anomaly · preliminary"], VERIFICATION: ["blue", "Issuer check"],
  COMPLIANCE_GAP: ["amber", "Compliance gap"], QUALITY: ["slate", "Document quality"],
};

export function CategoryChip({ category }: { category: string }) {
  const [cls, label] = CAT[category] || ["slate", category];
  return <span className={`chip xs ${cls}`}>{label}</span>;
}

export const CATEGORY_LABEL = Object.fromEntries(Object.entries(CAT).map(([k, v]) => [k, v[1]]));

const APP: Record<string, [string, string]> = {
  DRAFT: ["slate", "Draft"], UNDER_SCRUTINY: ["blue", "Under scrutiny"], DEFICIENCY_ISSUED: ["amber", "Deficiency letter issued"],
  RESPONDED: ["purple", "Institution replied"], DECIDED: ["green", "Decided"],
};

export function AppStatusChip({ status }: { status: string }) {
  const [cls, label] = APP[status] || ["slate", status];
  return <span className={`chip ${cls}`}>{label}</span>;
}

export function riskClass(r: number) {
  return r >= 60 ? "red" : r >= 25 ? "amber" : "green";
}

export function RiskBadge({ risk }: { risk: number }) {
  return <span className={`rk ${riskClass(risk)}`} title="Risk score (0–100)">{risk}</span>;
}

export const OVERALL: Record<string, [string, string]> = {
  NEEDS_ACTION: ["red", "Needs action"], NEEDS_REVIEW: ["amber", "Needs review"], MINOR_ISSUES: ["amber", "Minor issues"],
  CLEAR: ["green", "Clear"], NOT_CHECKED: ["slate", "Not checked yet"],
};

export function OverallChip({ status }: { status: string }) {
  const [cls, label] = OVERALL[status] || ["slate", status];
  return <span className={`chip ${cls}`}>{label}</span>;
}

// ----------------------------------------------------------------- misc --
export function Spinner({ label }: { label?: string }) {
  return (
    <span className="row muted small" role="status">
      <span className="spin" />
      {label}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Modal({ title, onClose, children, footer }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="chd">
          <h2>{title}</h2>
          <button className="btn link right" onClick={onClose} aria-label="Close"><X /></button>
        </div>
        <div className="cbody col">{children}</div>
        {footer && <div className="foot">{footer}</div>}
      </div>
    </div>
  );
}

// --------------------------------------------------------------- toasts --
const ToastContext = createContext<(msg: string, bad?: boolean) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ msg: string; bad: boolean } | null>(null);
  const timer = useRef<number>();
  const show = useCallback((msg: string, bad = false) => {
    setToast({ msg, bad });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), bad ? 6000 : 3500);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast && <div className={`toast${toast.bad ? " bad" : ""}`} role="status">{toast.msg}</div>}
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}

// --------------------------------------------------------------- loading --
export function useLoad<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  loadRef.current = load;
  const reload = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, loading, reload, setData };
}

export function ErrorBox({ error }: { error: string }) {
  return <div className="banner bad">{error}</div>;
}
