import { Download, Link2, Lock, Printer, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, AuditEvent, Detail, downloadFile, Verification } from "../api";
import { useAuth } from "../auth";
import { Meter } from "../components/Charts";
import {
  CategoryChip, Empty, ErrorBox, fmtDate, fmtDateTime, fmtTime, OverallChip, SeverityChip, Spinner, StatusChip, useLoad, useToast,
} from "../components/ui";

export function Report() {
  const { id = "" } = useParams();
  const { data, error, loading } = useLoad(() => api<Detail>(`/api/applications/${id}/report`), [id]);
  if (error) return <ErrorBox error={error} />;
  if (loading || !data) return <Empty><Spinner label="Building the report…" /></Empty>;
  const app = data.application;
  const s = data.verification_summary || {};
  return (
    <>
      <div className="pagehead">
        <div>
          <div className="crumb no-print"><Link to={`/applications/${id}`}>{id}</Link> › Validation report</div>
          <h1>Validation report · {app.institution}, {app.city}</h1>
          <div className="crumb">Generated {fmtDateTime(data.generated_at)} · {app.rulebook_version} · report for {app.id} ({app.app_type_label} {app.cycle})</div>
        </div>
        <div className="actions no-print"><button className="btn primary" onClick={() => window.print()}><Printer />Print or save as PDF</button></div>
      </div>
      <div className="kpis">
        <div className="card kpi"><div className="kl">Overall</div><div><OverallChip status={app.overall_status} /></div><div className="kd">{app.status.replace(/_/g, " ").toLowerCase()}</div></div>
        <div className="card kpi"><div className="kl">Risk score</div><div className="kv">{app.risk_score}<span className="muted small"> / 100</span></div><Meter value={app.risk_score} tone={app.risk_score >= 60 ? "red" : undefined} /></div>
        <div className="card kpi"><div className="kl">Checklist</div><div className="kv">{data.checklist.filter((c) => c.uploaded > 0).length}<span className="muted small"> of {data.checklist.length}</span></div><div className="kd">document types uploaded</div></div>
        <div className="card kpi"><div className="kl">Findings</div><div className="kv">{data.findings.length}</div><div className="kd">{app.counts.critical} critical · {app.counts.high} high · {app.counts.warning} warning</div></div>
        <div className="card kpi"><div className="kl">Issuer checks</div><div className="kv">{data.verifications.length}</div><div className="kd">{Object.entries(s).map(([k, v]) => `${v} ${k.toLowerCase().replace("_", " ")}`).join(" · ")}</div></div>
      </div>
      <div className="card">
        <div className="chd"><h2>Verification matrix</h2><span className="sub">every source, method, result and time is logged</span></div>
        <div className="tablewrap"><table>
          <thead><tr><th>Document</th><th>Issuing source</th><th>Method</th><th>Result</th><th>Note</th><th>Checked</th></tr></thead>
          <tbody>{data.checklist.map((c) => {
            const v = data.verifications.find((x) => x.doc_type === c.doc_type);
            return (
              <tr key={c.doc_type}><td><b style={{ fontWeight: 550 }}>{c.label}</b></td><td>{v?.source || "—"}</td><td className="small muted">{v?.method || "—"}</td>
                <td>{v ? <StatusChip status={v.status} xs /> : <StatusChip status={c.state} xs />}</td>
                <td className="small">{v?.note || c.note || ""}</td><td className="mono small">{v ? fmtTime(v.checked_at) : "—"}</td></tr>
            );
          })}</tbody>
        </table></div>
      </div>
      <div className="card">
        <div className="chd"><h2>Findings</h2></div>
        <div className="tablewrap"><table>
          <thead><tr><th>Severity</th><th>Category</th><th>Finding</th><th>Rule</th><th>Evidence</th><th>Review</th></tr></thead>
          <tbody>{data.findings.map((f) => (
            <tr key={f.id}><td><SeverityChip severity={f.severity} /></td><td><CategoryChip category={f.category} /></td>
              <td><b style={{ fontWeight: 550 }}>{f.title}</b><div className="small muted">{f.message}</div></td>
              <td className="mono small">{f.rule_id}</td>
              <td className="small">{f.evidence.map((e) => `${e.label}: ${e.filename || e.kind}${e.value ? ` “${e.value}”` : ""}`).join("; ")}</td>
              <td className="small">{f.status === "OPEN" ? "Open" : `${f.status.toLowerCase()} by ${f.decision_by}`}</td></tr>))}</tbody>
        </table></div>
      </div>
      <p className="small muted">This report supports, and does not replace, statutory scrutiny. Physical inspections and final decisions rest with the competent authority. Forensic indicators are preliminary.</p>
    </>
  );
}

const VSTATUS = ["", "VERIFIED", "MISMATCH", "EXPIRED", "SOURCE_UNAVAILABLE", "MANUAL_REVIEW", "PENDING"];

export function VerificationLog() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const navigate = useNavigate();
  const { data, error, loading } = useLoad(() => api<Verification[]>(`/api/verifications${status ? `?status=${status}` : ""}`), [status]);
  return (
    <>
      <div className="pagehead"><div><h1>Issuer verification</h1><div className="crumb">Latest check of every document, per application. Sources run in sandbox mode.</div></div></div>
      <div className="tabs">
        {VSTATUS.map((v) => <button key={v || "all"} className={status === v ? "on" : ""} onClick={() => setParams(v ? { status: v } : {})}>
          {v ? v.replace("_", " ").toLowerCase().replace(/^./, (c) => c.toUpperCase()) : "All"}</button>)}
      </div>
      {error && <ErrorBox error={error} />}
      <div className="card">
        {loading && !data ? <Empty><Spinner /></Empty> : !data?.length ? <Empty>Nothing here.</Empty> : (
          <div className="tablewrap"><table>
            <thead><tr><th>Application</th><th>Document</th><th>Source</th><th>Method</th><th>Result</th><th>Note</th><th className="r">Attempts</th><th>Checked</th></tr></thead>
            <tbody>{data.map((v) => (
              <tr key={v.id} className="clickable" onClick={() => navigate(`/applications/${v.application_id}`)}>
                <td><span className="mono">{v.application_id}</span><div className="small muted">{v.institution}</div></td>
                <td>{v.doc_label}</td><td>{v.source}</td><td className="small muted">{v.method}</td><td><StatusChip status={v.status} xs /></td>
                <td className="small" style={{ maxWidth: 360 }}>{v.note}</td><td className="r num">{v.attempts}</td>
                <td className="small mono">{fmtDate(v.checked_at)} {fmtTime(v.checked_at)}</td></tr>))}</tbody>
          </table></div>
        )}
      </div>
    </>
  );
}

export function AuditTrail() {
  const { user } = useAuth();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const appId = params.get("application_id") || "";
  const actor = params.get("actor_type") || "";
  const [q, setQ] = useState(params.get("q") || "");
  const query = new URLSearchParams({ limit: "300", ...(appId ? { application_id: appId } : {}), ...(actor ? { actor_type: actor } : {}), ...(params.get("q") ? { q: params.get("q")! } : {}) });
  const { data, error, loading } = useLoad(() => api<AuditEvent[]>(`/api/audit?${query}`), [query.toString()]);
  const chain = useLoad(() => api<{ valid: boolean; events: number; head?: string; broken_at?: number; reason?: string }>("/api/audit/verify"), []);
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const set = (k: string, v: string) => {
    const next = Object.fromEntries(params.entries());
    if (v) next[k] = v; else delete next[k];
    setParams(next);
  };
  return (
    <>
      <div className="pagehead">
        <div><h1>Audit trail</h1><div className="crumb">Every rule, record check, source response, alert and human action, in order</div></div>
        <div className="actions">
          {chain.data && (chain.data.valid
            ? <span className="chip green"><ShieldCheck />Chain verified · {chain.data.events} events</span>
            : <span className="chip red"><ShieldAlert />Chain broken at event {chain.data.broken_at}: {chain.data.reason}</span>)}
          <button className="btn sm" onClick={() => chain.reload()}>Re-verify</button>
          {(user?.role === "auditor" || user?.role === "senior_officer") && (
            <button className="btn sm" onClick={() => downloadFile(`/api/audit/export.csv${appId ? `?application_id=${appId}` : ""}`, "pramaan-audit.csv").catch((e) => toast(e.message, true))}><Download />Export CSV</button>
          )}
        </div>
      </div>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <input className="input" style={{ width: 200 }} placeholder="Application ID" defaultValue={appId} onKeyDown={(e) => e.key === "Enter" && set("application_id", (e.target as HTMLInputElement).value.trim().toUpperCase())} aria-label="Application ID" />
        <select className="input" style={{ width: 160 }} value={actor} onChange={(e) => set("actor_type", e.target.value)} aria-label="Actor type">
          <option value="">All actors</option><option value="USER">People</option><option value="SYSTEM">System</option><option value="ADAPTER">Issuer adapters</option>
        </select>
        <input className="input" style={{ width: 240 }} placeholder="Search action, actor or object" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && set("q", q)} aria-label="Search" />
      </div>
      {error && <ErrorBox error={error} />}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 380px", gap: 14, alignItems: "start" }}>
        <div className="card">
          {loading && !data ? <Empty><Spinner /></Empty> : (
            <div className="tablewrap"><table>
              <thead><tr><th>#</th><th>Time (IST)</th><th>Actor</th><th>Event</th><th>Object</th><th>Hash</th></tr></thead>
              <tbody>{data?.map((e) => (
                <tr key={e.id} className="clickable" onClick={() => setSelected(e)} style={selected?.id === e.id ? { background: "var(--blue-bg)" } : undefined}>
                  <td className="num small faint">{e.id}</td><td className="mono small">{fmtDate(e.ts)} {fmtTime(e.ts)}</td>
                  <td className="small">{e.actor}</td><td><b style={{ fontWeight: 550 }}>{e.action}</b></td>
                  <td className="small">{e.application_id ? <Link to={`/applications/${e.application_id}`} onClick={(ev) => ev.stopPropagation()}>{e.application_id}</Link> : null} <span className="muted">{e.object_id}</span></td>
                  <td className="mono small faint">{e.hash.slice(0, 4)}…{e.hash.slice(-4)}</td></tr>))}</tbody>
            </table></div>
          )}
        </div>
        <div className="card" style={{ position: "sticky", top: 70 }}>
          <div className="chd"><h2>Event detail</h2>{selected && <span className="right mono muted">#{selected.id}</span>}</div>
          {!selected ? <Empty>Select an event.</Empty> : (
            <div className="cbody col">
              <div className="small"><b>{selected.action}</b> · {selected.actor} ({selected.actor_type.toLowerCase()})</div>
              <div className="small muted">{fmtDateTime(selected.ts)} · {selected.object_type} {selected.object_id}</div>
              <pre className="mono" style={{ background: "var(--surface-2)", border: "1px solid var(--line)", borderRadius: 7, padding: 10, whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0 }}>
                {JSON.stringify(selected.details, null, 2)}</pre>
              <div className="lbl">Hash chain</div>
              <div className="small"><span className="muted">Previous</span><div className="mono" style={{ wordBreak: "break-all" }}>{selected.prev_hash}</div></div>
              <div className="row faint"><Link2 size={14} /></div>
              <div className="small"><span className="muted">This event</span><div className="mono" style={{ wordBreak: "break-all" }}>{selected.hash}</div></div>
              <div className="row small muted"><Lock size={14} />Append-only. Editing any past event breaks the chain.</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
