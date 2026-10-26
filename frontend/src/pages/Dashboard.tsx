import { ArrowRight } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AlertItem, api, AppSummary } from "../api";
import { HBars, LineChart, Meter } from "../components/Charts";
import {
  ago, AppStatusChip, CATEGORY_LABEL, Empty, ErrorBox, fmtDate, OverallChip, RiskBadge, Spinner, StatusChip, useLoad,
} from "../components/ui";
import { useAuth } from "../auth";

interface DashboardData {
  kpis: Record<string, number | null>;
  daily: { date: string; received: number; prechecked: number }[];
  findings_by_category: Record<string, number>;
  verification_outcomes: Record<string, number>;
  states: { state: string; received: number; prechecked: number; critical_open: number; median_risk: number }[];
  alerts: AlertItem[];
  top_risk: AppSummary[];
}

const SEV: Record<string, string> = { critical: "red", serious: "amber", warning: "amber", info: "slate" };

export function Dashboard() {
  const { data, error, loading } = useLoad(() => api<DashboardData>("/api/dashboard"), []);
  const navigate = useNavigate();
  if (error) return <ErrorBox error={error} />;
  if (loading || !data) return <Empty><Spinner label="Loading dashboard…" /></Empty>;
  const k = data.kpis;
  const outcomes = ["VERIFIED", "EXPIRED", "MISMATCH", "SOURCE_UNAVAILABLE", "MANUAL_REVIEW", "PENDING"];
  const total = outcomes.reduce((s, o) => s + (data.verification_outcomes[o] || 0), 0);
  const cats = Object.entries(data.findings_by_category).map(([c, n]) => [CATEGORY_LABEL[c] || c, n] as [string, number])
    .sort((a, b) => b[1] - a[1]);
  const labels = data.daily.map((d, i) => (i === 0 || i === data.daily.length - 1 ? fmtDate(d.date).slice(0, 5) : d.date.slice(8)));
  const tiles: [string, string | number, string][] = [
    ["Applications received", k.received ?? 0, `${k.decided ?? 0} decided`],
    ["Pre-checked by PRAMAAN", k.prechecked ?? 0, k.received ? `${Math.round(((k.prechecked ?? 0) / (k.received || 1)) * 100)}% of received` : ""],
    ["Awaiting scrutiny", k.awaiting_scrutiny ?? 0, `${k.deficiency_letters ?? 0} with a deficiency letter`],
    ["Critical findings open", k.critical_open ?? 0, "need a scrutinizer decision"],
    ["Issuer checks needing a person", k.issuer_pending ?? 0, "manual review or source down"],
    ["Median pre-check time", k.median_precheck_seconds != null ? `${k.median_precheck_seconds}s` : "—", "per application"],
  ];
  return (
    <>
      <div className="pagehead">
        <div><h1>Dashboard</h1><div className="crumb">Approval cycle 2026-27 · all regions · 14 days to {fmtDate(data.daily[data.daily.length - 1]?.date)}</div></div>
        <div className="actions"><Link className="btn" to="/queue">Open scrutiny queue <ArrowRight /></Link></div>
      </div>
      <div className="kpis">
        {tiles.map(([l, v, d]) => (
          <div key={l} className="card kpi"><div className="kl">{l}</div><div className="kv">{v}</div><div className="kd">{d}</div></div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.3fr) minmax(0,1fr) minmax(0,1fr)", gap: 12 }}>
        <div className="card">
          <div className="chd"><h2>Applications received vs pre-checked</h2><span className="sub">per day</span>
            <span className="right legend"><i style={{ background: "var(--s1)" }} />Received<i style={{ background: "var(--s2)" }} />Pre-checked</span></div>
          <div className="cbody">
            <LineChart labels={labels} series={[
              { name: "Received", color: "#2a78d6", values: data.daily.map((d) => d.received) },
              { name: "Pre-checked", color: "#eb6834", values: data.daily.map((d) => d.prechecked) },
            ]} />
          </div>
        </div>
        <div className="card">
          <div className="chd"><h2>Open findings by category</h2><span className="sub">all severities</span></div>
          <div className="cbody"><HBars rows={cats} /></div>
        </div>
        <div className="card">
          <div className="chd"><h2>Issuer verification outcomes</h2><span className="sub">{total} checks</span></div>
          <table><tbody>
            {outcomes.map((o) => {
              const n = data.verification_outcomes[o] || 0;
              const pct = total ? (n / total) * 100 : 0;
              return (
                <tr key={o} className="clickable" onClick={() => navigate(`/verification?status=${o}`)}>
                  <td><StatusChip status={o} xs /></td><td className="r num">{n}</td><td className="r num muted">{pct.toFixed(1)}%</td>
                  <td style={{ width: 90 }}><Meter value={pct} /></td>
                </tr>
              );
            })}
          </tbody></table>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 12 }}>
        <div className="card">
          <div className="chd"><h2>Alerts</h2><span className="sub">{data.alerts.length} open</span></div>
          {data.alerts.length === 0 ? <Empty>No open alerts.</Empty> : data.alerts.map((a) => (
            <div key={a.id} className="alert-item" style={{ cursor: a.application_id ? "pointer" : undefined }}
              onClick={() => a.application_id && navigate(`/applications/${a.application_id}`)}>
              <span className={`chip xs ${SEV[a.severity] || "slate"}`} style={{ textTransform: "capitalize" }}>{a.severity}</span>
              <span className="grow">{a.message}<span className="faint small" style={{ display: "block" }}>{ago(a.created_at)}</span></span>
            </div>
          ))}
        </div>
        <div className="card">
          <div className="chd"><h2>Highest risk open applications</h2></div>
          <table><thead><tr><th>Risk</th><th>Application</th><th>Institution</th><th>Status</th></tr></thead>
            <tbody>{data.top_risk.map((a) => (
              <tr key={a.id} className="clickable" onClick={() => navigate(`/applications/${a.id}`)}>
                <td><RiskBadge risk={a.risk_score} /></td><td className="mono">{a.id}</td><td>{a.institution}</td><td><OverallChip status={a.overall_status} /></td>
              </tr>))}</tbody></table>
        </div>
      </div>
      <div className="card">
        <div className="chd"><h2>By state</h2></div>
        <div className="tablewrap"><table>
          <thead><tr><th>State</th><th className="r">Received</th><th className="r">Pre-checked</th><th className="r">Critical open</th><th className="r">Median risk</th><th>Progress</th></tr></thead>
          <tbody>{data.states.map((s) => (
            <tr key={s.state}><td>{s.state}</td><td className="r num">{s.received}</td><td className="r num">{s.prechecked}</td>
              <td className="r num">{s.critical_open}</td><td className="r num">{s.median_risk}</td>
              <td style={{ width: 140 }}><Meter value={s.prechecked} max={s.received || 1} /></td></tr>))}</tbody>
        </table></div>
      </div>
    </>
  );
}

const FILTERS: [string, string][] = [
  ["", "All"], ["UNDER_SCRUTINY,RESPONDED", "Under scrutiny"], ["DEFICIENCY_ISSUED", "Letter issued"], ["DECIDED", "Decided"],
];

export function Queue() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") || "";
  const q = params.get("q") || "";
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data, error, loading } = useLoad(() => api<AppSummary[]>(`/api/applications?sort=risk${status ? `&status=${status}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`), [status, q]);
  return (
    <>
      <div className="pagehead">
        <div><h1>Scrutiny queue</h1><div className="crumb">Sorted by risk · {user?.full_name}</div></div>
        <div className="actions">
          <input className="input" style={{ width: 260 }} placeholder="Filter by institution, city or ID" defaultValue={q}
            onKeyDown={(e) => { if (e.key === "Enter") setParams({ ...(status ? { status } : {}), q: (e.target as HTMLInputElement).value }); }} aria-label="Filter" />
        </div>
      </div>
      <div className="tabs">
        {FILTERS.map(([v, l]) => <button key={l} className={status === v ? "on" : ""} onClick={() => setParams({ ...(v ? { status: v } : {}), ...(q ? { q } : {}) })}>{l}</button>)}
      </div>
      {error && <ErrorBox error={error} />}
      <div className="card">
        {loading && !data ? <Empty><Spinner label="Loading…" /></Empty> : !data?.length ? <Empty>No applications match.</Empty> : (
          <div className="tablewrap"><table>
            <thead><tr><th>Risk</th><th>Application</th><th>Institution</th><th>Type</th><th>Findings</th><th>Pre-check</th><th>Status</th><th>Submitted</th></tr></thead>
            <tbody>{data.map((a) => (
              <tr key={a.id} className="clickable" onClick={() => navigate(`/applications/${a.id}`)}>
                <td><RiskBadge risk={a.risk_score} /></td>
                <td className="mono">{a.id}</td>
                <td><b style={{ fontWeight: 550 }}>{a.institution}</b><div className="small muted">{a.city}, {a.state}</div></td>
                <td>{a.app_type_label}</td>
                <td><span className="row">
                  {a.counts.critical > 0 && <span className="chip xs solidred">{a.counts.critical} critical</span>}
                  {a.counts.high > 0 && <span className="chip xs red">{a.counts.high} high</span>}
                  {a.counts.warning > 0 && <span className="chip xs amber">{a.counts.warning} warn</span>}
                  {a.counts.open === 0 && <span className="chip xs green">reviewed</span>}
                </span></td>
                <td><OverallChip status={a.overall_status} /></td>
                <td><AppStatusChip status={a.status} /></td>
                <td className="small muted">{fmtDate(a.submitted_at)}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
    </>
  );
}
