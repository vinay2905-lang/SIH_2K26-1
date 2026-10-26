import {
  Bell, BookOpenCheck, FileChartColumn, FolderOpen, History, Inbox, LayoutDashboard, LogOut, Search, ShieldCheck,
} from "lucide-react";
import { ReactNode, useEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { AlertItem, api } from "../api";
import { ROLE_LABEL, useAuth } from "../auth";
import { useLang, useT } from "../i18n";
import { ago } from "./ui";

export function Mark() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden>
      <path d="M7 2.8h7.2l4 4V20a1.2 1.2 0 0 1-1.2 1.2H7A1.2 1.2 0 0 1 5.8 20V4A1.2 1.2 0 0 1 7 2.8z" fill="none" stroke="#1F3A5F" strokeWidth="1.9" strokeLinejoin="round" />
      <path d="M14 3v4h4" fill="none" stroke="#1F3A5F" strokeWidth="1.9" strokeLinejoin="round" />
      <path d="M8.8 13.9l2.3 2.3 4.4-4.6" fill="none" stroke="#C8641E" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const SEV_CLASS: Record<string, string> = { critical: "red", serious: "amber", warning: "amber", info: "slate" };

function AlertsBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AlertItem[]>([]);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { user } = useAuth();

  const load = () => api<AlertItem[]>("/api/alerts").then(setItems).catch(() => {});
  useEffect(() => {
    load();
    const id = window.setInterval(load, 20000);
    return () => window.clearInterval(id);
  }, []);
  useEffect(() => {
    const onClick = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const unread = items.filter((a) => !a.read).length;
  const openAlert = async (a: AlertItem) => {
    if (!a.read) await api(`/api/alerts/${a.id}/read`, { method: "POST" }).catch(() => {});
    setOpen(false);
    load();
    if (a.application_id) navigate(user?.role === "institution" ? `/my/${a.application_id}` : `/applications/${a.application_id}`);
  };
  return (
    <div style={{ position: "relative" }} ref={ref}>
      <button className="iconbtn" onClick={() => setOpen(!open)} aria-label={`Alerts (${unread} unread)`}>
        <Bell size={18} />
        {unread > 0 && <b>{unread}</b>}
      </button>
      {open && (
        <div className="dropdown">
          <div className="chd"><h2>Alerts</h2><span className="sub">{items.length} open</span></div>
          {items.length === 0 && <div className="empty">No open alerts</div>}
          {items.map((a) => (
            <button key={a.id} className={`alert-item${a.read ? "" : " unread"}`} onClick={() => openAlert(a)}
              style={{ all: "unset", display: "flex", gap: 10, padding: "10px 14px", borderBottom: "1px solid var(--line)", cursor: "pointer", fontSize: 12.5 }}>
              <span className={`chip xs ${SEV_CLASS[a.severity] || "slate"}`} style={{ textTransform: "capitalize" }}>{a.severity}</span>
              <span className="grow">
                <span style={{ fontWeight: a.read ? 400 : 600 }}>{a.message}</span>
                <span className="faint small" style={{ display: "block" }}>{ago(a.created_at)}{a.application_id ? ` · ${a.application_id}` : ""}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function initials(name: string) {
  return name.split(/\s+/).filter((w) => /^[A-Z]/.test(w)).slice(0, 2).map((w) => w[0]).join("") || name.slice(0, 2).toUpperCase();
}

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { lang, setLang } = useLang();
  const t = useT();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  if (!user) return null;
  const institution = user.role === "institution";
  const nav = institution
    ? [{ to: "/my", icon: FolderOpen, label: "My applications" }]
    : [
        { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
        { to: "/queue", icon: Inbox, label: "Scrutiny queue" },
        { to: "/verification", icon: ShieldCheck, label: "Verification" },
        { label: "Governance" },
        { to: "/rulebook", icon: BookOpenCheck, label: "Rulebook" },
        { to: "/audit", icon: History, label: "Audit trail" },
      ];
  const search = (e: React.FormEvent) => {
    e.preventDefault();
    const term = q.trim();
    if (!term) return;
    if (/^APP-\d{4}-\d{5}$/i.test(term)) navigate(institution ? `/my/${term.toUpperCase()}` : `/applications/${term.toUpperCase()}`);
    else navigate(`${institution ? "/my" : "/queue"}?q=${encodeURIComponent(term)}`);
  };
  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="mark"><Mark /></span>
          <span className="wordmark">PRAMAAN<small>{institution ? "Institution portal" : "AICTE approval scrutiny"}</small></span>
        </Link>
        <span className="env" title="All institutions, documents and issuer records here are synthetic">Sandbox · synthetic data</span>
        <form className="tsearch" onSubmit={search} role="search">
          <Search size={14} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={institution ? "Search my applications" : "Search application ID or institution"} aria-label="Search" />
        </form>
        <div className="tright">
          <div className="lang" role="group" aria-label="Language">
            <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>EN</button>
            <button className={lang === "hi" ? "on" : ""} onClick={() => setLang("hi")} style={{ fontFamily: "'Noto Sans Devanagari', Inter" }}>हिंदी</button>
          </div>
          <AlertsBell />
          <div className="user">
            <div className="avatar" aria-hidden>{initials(user.full_name)}</div>
            <div>
              <div className="n">{user.full_name}</div>
              <div className="r">{ROLE_LABEL[user.role]}{user.region && !institution ? ` · ${user.region}` : ""}</div>
            </div>
          </div>
          <button className="iconbtn" onClick={() => { logout(); navigate("/login"); }} title={t("Sign out")} aria-label={t("Sign out")}>
            <LogOut size={17} />
          </button>
        </div>
      </header>
      <nav className="sidebar" aria-label="Main">
        <div className="navlabel">{institution ? "Application 2026-27" : "Scrutiny"}</div>
        {nav.map((n, i) =>
          "to" in n && n.to ? (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => `nav${isActive ? " active" : ""}`}>
              {n.icon && <n.icon size={16} />}
              <span>{t(n.label)}</span>
            </NavLink>
          ) : (
            <div key={i} className="navlabel">{n.label}</div>
          ),
        )}
        <div className="sfoot">
          {institution ? (
            <span>The pre-check only advises. AICTE officials decide.</span>
          ) : (
            <span className="row"><FileChartColumn size={14} />Approval cycle 2026-27</span>
          )}
        </div>
      </nav>
      <main className="main" id="main">{children}</main>
    </div>
  );
}
