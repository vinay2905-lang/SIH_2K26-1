import { Check, FileChartColumn, FilePenLine, Gavel, Info, RefreshCw, RotateCcw, Send, UserCheck, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, AppSummary, AuditEvent, Detail, Evidence, Finding, Letter } from "../api";
import { useAuth } from "../auth";
import { Meter } from "../components/Charts";
import DocViewer, { Highlight } from "../components/DocViewer";
import {
  AppStatusChip, CategoryChip, Empty, ErrorBox, fmtDate, fmtDateTime, fmtTime, Modal, OverallChip, RiskBadge, SeverityChip,
  Spinner, StatusChip, useLoad, useToast,
} from "../components/ui";

const SHORT: Record<string, string> = {
  LAND_DEED: "Land deed", BUILDING_COMPLETION: "Completion cert.", FIRE_NOC: "Fire NOC", STRUCTURAL_STABILITY: "Structural",
  AFFILIATION_LETTER: "Affiliation", NBA_ACCREDITATION: "NBA", TER_RECEIPT: "TER receipt", AFFIDAVIT: "Affidavit",
  FACULTY_LIST: "Faculty list", LAB_PHOTO: "Lab photo",
};

function shortLabel(d: Detail["documents"][number], all: Detail["documents"]) {
  const base = SHORT[d.slot] || d.slot_label;
  const same = all.filter((x) => x.slot === d.slot);
  return same.length > 1 ? `${base} ${same.indexOf(d) + 1}` : base;
}

function QueueMini({ current }: { current: string }) {
  const { data } = useLoad(() => api<AppSummary[]>("/api/applications?sort=risk&status=UNDER_SCRUTINY,RESPONDED,DEFICIENCY_ISSUED"), []);
  return (
    <div className="card">
      <div className="chd"><h2>Queue</h2><span className="sub">{data ? `${data.length} open · by risk` : ""}</span></div>
      <div className="qlist">
        {!data && <Spinner />}
        {data?.map((a) => (
          <Link key={a.id} to={`/applications/${a.id}`} className={`qi${a.id === current ? " on" : ""}`}>
            <span className="row"><span className="mono" style={{ fontWeight: 600, color: "var(--ink)" }}>{a.id}</span><span className="right"><RiskBadge risk={a.risk_score} /></span></span>
            <span className="qi-name">{a.institution}, {a.city}</span>
            <span className="row">
              <span className="tag" style={{ height: 19, fontSize: 10.5 }}>{a.app_type === "EOA" ? "EoA" : a.app_type_label}</span>
              {a.counts.critical > 0 && <span className="chip xs red">{a.counts.critical} critical</span>}
              {!a.counts.critical && a.counts.high > 0 && <span className="chip xs red">{a.counts.high} high</span>}
              {!a.counts.critical && !a.counts.high && <span className="chip xs green">{a.counts.open ? `${a.counts.open} to review` : "reviewed"}</span>}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function EvidenceLine({ e, onShow }: { e: Evidence; onShow: (e: Evidence) => void }) {
  const isDoc = !!e.document_id;
  const what = [e.field, e.value && `“${e.value}”`].filter(Boolean).join(" · ");
  const where = isDoc ? `${e.filename}${e.page != null ? ` · p. ${(e.page || 0) + 1}` : ""}` : e.kind === "form" ? "Application form" :
    e.kind === "aicte_record" ? "AICTE records" : e.kind === "application" ? "Application" : e.kind === "checklist" ? "Checklist" : e.kind;
  return (
    <div className="ev">
      <span className={`etag${isDoc ? "" : e.kind === "form" ? " blue" : " slate"}`}>{e.label}</span>
      <span className="grow">
        {isDoc ? <button onClick={() => onShow(e)} title="Show on the document" style={{ color: "var(--blue)", fontWeight: 500 }}>{where}</button> : <b style={{ fontWeight: 500 }}>{where}</b>}
        {what && <span> · {what}</span>}
        {e.note && <span className="muted"> · {e.note}</span>}
      </span>
      {e.confidence != null && <span className="muted num small">{(e.confidence * 100).toFixed(0)}%</span>}
    </div>
  );
}

function FindingCard({ f, open, onOpen, onShow, canReview, onDecide, verification }: {
  f: Finding; open: boolean; onOpen: () => void; onShow: (e: Evidence) => void; canReview: boolean;
  onDecide: (f: Finding, action: "accept" | "override" | "reopen") => void; verification?: Detail["verifications"][number];
}) {
  return (
    <div className={`fcard sev-${f.severity}${open ? " open" : ""}`} onClick={open ? undefined : onOpen}>
      <div className="row" style={{ flexWrap: "wrap" }}>
        <CategoryChip category={f.category} /><SeverityChip severity={f.severity} />
        {f.status !== "OPEN" && <span className={`chip xs ${f.status === "ACCEPTED" ? "blue" : "slate"}`}>{f.status === "ACCEPTED" ? "Accepted" : "Overridden"}</span>}
        <span className="mono right muted">{f.ref}</span>
      </div>
      <div className="ftitle" style={open ? undefined : { fontSize: 12.5, fontWeight: 550 }}>{f.title}</div>
      {open && (
        <>
          <p className="small" style={{ color: "var(--ink-2)", fontSize: 12.5 }}>{f.message}</p>
          {f.evidence.length > 0 && <><div className="lbl">Evidence</div>{f.evidence.map((e) => <EvidenceLine key={e.label} e={e} onShow={onShow} />)}</>}
          {f.rule_id && (
            <><div className="lbl">Rule applied</div>
              <div className="small"><span className="mono" style={{ fontWeight: 600 }}>{f.rule_id}</span> · {f.rule_version} · <span className="muted">{f.source_ref}</span></div></>
          )}
          {verification && verification.status !== "PENDING" && (
            <><div className="lbl">Issuer verification</div>
              <div className="iv">
                <div className="grow col" style={{ gap: 2 }}>
                  <b>{verification.source}</b>
                  <span className="muted small">{verification.method}{verification.reference ? ` · ${verification.reference}` : ""}</span>
                  <span className="small">{verification.note}</span>
                </div>
                <div className="col" style={{ alignItems: "flex-end" }}>
                  <StatusChip status={verification.status} xs />
                  <span className="mono muted small">{fmtTime(verification.checked_at)} IST</span>
                </div>
              </div></>
          )}
          {f.preliminary && <div className="row small muted"><Info size={14} />Preliminary indicator only. Confirm before acting; it is not proof of tampering.</div>}
          <div className="row small muted"><Info size={14} />AI-assisted finding. Check the evidence before you decide.</div>
          {f.decision_by && <div className="small">{f.status === "ACCEPTED" ? "Accepted" : f.status === "OVERRIDDEN" ? "Overridden" : "Updated"} by <b>{f.decision_by}</b> {fmtDateTime(f.decided_at)}{f.decision_note ? ` · “${f.decision_note}”` : ""}</div>}
          {canReview && (
            <div className="row" style={{ flexWrap: "wrap" }}>
              {f.status === "OPEN" ? (
                <>
                  <button className="btn primary sm" onClick={() => onDecide(f, "accept")}><Check />Accept finding</button>
                  <button className="btn sm" onClick={() => onDecide(f, "override")}><X />Override…</button>
                </>
              ) : <button className="btn sm" onClick={() => onDecide(f, "reopen")}><RotateCcw />Reopen</button>}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function LetterPanel({ detail, letter, onChanged }: { detail: Detail; letter: Letter; onChanged: () => void }) {
  const { user } = useAuth();
  const toast = useToast();
  const [items, setItems] = useState(letter.items);
  const [note, setNote] = useState(letter.note);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setItems(letter.items); setNote(letter.note); }, [letter]);
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try { await fn(); toast(ok); onChanged(); } catch (e) { toast((e as Error).message, true); } finally { setBusy(false); }
  };
  const editable = letter.status === "DRAFT" && user?.role === "scrutinizer";
  return (
    <div className="card">
      <div className="chd"><h2>Deficiency letter {letter.id}</h2>
        <span className={`chip xs ${letter.status === "ISSUED" ? "amber" : letter.status === "RESPONDED" ? "green" : "blue"}`}>{letter.status.replace("_", " ").toLowerCase()}</span>
        <span className="sub">drafted by {letter.drafted_by}{letter.approved_by ? ` · approved by ${letter.approved_by}` : ""}</span></div>
      <div className="cbody col">
        {items.map((it, i) => (
          <div key={i} className="col" style={{ gap: 4 }}>
            <b>{i + 1}. {it.title}</b>
            {editable ? <textarea className="input" value={it.text} onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} aria-label={`Item ${i + 1}`} />
              : <span className="small muted">{it.text}</span>}
          </div>
        ))}
        {editable ? <textarea className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Covering note" aria-label="Covering note" /> : note && <span className="small">{note}</span>}
        {letter.response && <div className="banner ok small"><span className="grow"><b>Institution replied</b> {fmtDateTime(letter.response.at)}<span>{letter.response.message}</span></span></div>}
        <div className="row">
          {editable && <>
            <button className="btn" disabled={busy} onClick={() => act(() => api(`/api/letters/${letter.id}`, { method: "PUT", body: { items, note } }), "Letter saved")}>Save</button>
            <button className="btn primary" disabled={busy} onClick={() => act(async () => {
              await api(`/api/letters/${letter.id}`, { method: "PUT", body: { items, note } });
              await api(`/api/letters/${letter.id}/submit`, { method: "POST" });
            }, "Sent to the senior officer for approval")}><Send />Send for approval</button>
          </>}
          {letter.status === "PENDING_APPROVAL" && user?.role === "senior_officer" && <>
            <button className="btn primary" disabled={busy} onClick={() => act(() => api(`/api/letters/${letter.id}/review`, { body: { approve: true } }), "Letter issued to the institution")}><Check />Approve and issue</button>
            <button className="btn" disabled={busy} onClick={() => act(() => api(`/api/letters/${letter.id}/review`, { body: { approve: false, note: "Please revise" } }), "Returned to the scrutinizer")}>Return</button>
          </>}
          {letter.status === "PENDING_APPROVAL" && user?.role !== "senior_officer" && <span className="small muted">Waiting for a senior officer to approve.</span>}
          <span className="right small muted">{detail.application.institution}</span>
        </div>
      </div>
    </div>
  );
}

function Activity({ appId }: { appId: string }) {
  const { data } = useLoad(() => api<AuditEvent[]>(`/api/audit?application_id=${appId}&limit=300`), [appId]);
  if (!data) return <Empty><Spinner /></Empty>;
  return (
    <div className="tablewrap"><table>
      <thead><tr><th>Time (IST)</th><th>Actor</th><th>Event</th><th>Details</th><th>Hash</th></tr></thead>
      <tbody>{data.map((e) => (
        <tr key={e.id}><td className="mono small">{fmtDate(e.ts)} {fmtTime(e.ts)}</td><td className="small">{e.actor}</td><td><b style={{ fontWeight: 550 }}>{e.action}</b></td>
          <td className="small muted">{Object.entries(e.details).slice(0, 3).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ")}</td>
          <td className="mono small faint">{e.hash.slice(0, 4)}…{e.hash.slice(-4)}</td></tr>))}</tbody>
    </table></div>
  );
}

export default function Workspace() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const { data, error, loading, reload } = useLoad(() => api<Detail>(`/api/applications/${id}`), [id]);
  const [openId, setOpenId] = useState<number | null>(null);
  const [docId, setDocId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [focus, setFocus] = useState<Evidence | null>(null);
  const [filter, setFilter] = useState<"open" | "all">("all");
  const [override, setOverride] = useState<Finding | null>(null);
  const [reason, setReason] = useState("");
  const [letterOpen, setLetterOpen] = useState(false);
  const [picked, setPicked] = useState<number[]>([]);
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [decision, setDecision] = useState("APPROVED");
  const [decisionNote, setDecisionNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [tab, setTab] = useState<"verify" | "record" | "letters" | "activity">("verify");
  const [busy, setBusy] = useState(false);

  useEffect(() => { setOpenId(null); setDocId(null); setFocus(null); setPage(0); }, [id]);
  useEffect(() => {
    if (!data || data.application.id !== id) return;
    if (openId == null && data.findings.length) {
      const withPage = (f: Finding) => f.evidence.some((e) => e.document_id && e.bbox);
      const first = data.findings.find((f) => f.status === "OPEN" && withPage(f)) || data.findings.find((f) => f.status === "OPEN") || data.findings[0];
      setOpenId(first.id);
      const ev = first.evidence.find((e) => e.document_id && e.bbox) || first.evidence.find((e) => e.document_id);
      if (ev && !docId) {
        setDocId(ev.document_id!);
        setPage(ev.page || 0);
        setFocus(ev);
        return;
      }
    }
    if (!docId && data.documents.length) setDocId(data.documents[0].id);
  }, [data, openId, docId, id]);
  useEffect(() => {
    if (!data?.processing) return;
    const timer = window.setInterval(() => reload(true), 2000);
    return () => window.clearInterval(timer);
  }, [data?.processing, reload]);

  const verifByDoc = useMemo(() => Object.fromEntries((data?.verifications || []).map((v) => [v.document_id, v])), [data]);
  if (error) return <ErrorBox error={error} />;
  if (loading || !data) return <Empty><Spinner label="Loading application…" /></Empty>;
  const app = data.application;
  const doc = data.documents.find((d) => d.id === docId) || data.documents[0];
  const open = data.findings.find((f) => f.id === openId);
  const findings = filter === "open" ? data.findings.filter((f) => f.status === "OPEN") : data.findings;
  const highlights: Highlight[] = [];
  if (open && doc) {
    for (const e of open.evidence) {
      if (e.document_id === doc.id && e.bbox) {
        highlights.push({ page: e.page || 0, bbox: e.bbox, label: `${e.label}${e.confidence ? ` · ${(e.confidence * 100).toFixed(0)}%` : ""}`,
          tone: open.severity === "info" ? "ok" : "bad", focus: focus?.label === e.label });
      }
    }
  }
  const showEvidence = (e: Evidence) => {
    if (!e.document_id) return;
    setDocId(e.document_id);
    setPage(e.page || 0);
    setFocus(e);
  };
  const decide = async (f: Finding, action: "accept" | "override" | "reopen", note = "") => {
    if (action === "override" && !note) { setOverride(f); setReason(""); return; }
    setBusy(true);
    try {
      await api(`/api/findings/${f.id}/decision`, { body: { action, note } });
      toast(action === "accept" ? "Finding accepted" : action === "override" ? "Finding overridden" : "Finding reopened");
      setOverride(null);
      await reload(true);
      const next = data.findings.find((x) => x.status === "OPEN" && x.id !== f.id);
      if (next && action !== "reopen") setOpenId(next.id);
    } catch (e) { toast((e as Error).message, true); } finally { setBusy(false); }
  };
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try { await fn(); toast(ok); await reload(true); return true; } catch (e) { toast((e as Error).message, true); return false; } finally { setBusy(false); }
  };
  const draftLetter = async () => {
    if (await act(() => api(`/api/applications/${id}/letters`, { body: { finding_ids: picked, note: "Reply within 15 days with corrected documents." } }), "Letter drafted")) {
      setLetterOpen(false);
      setTab("letters");
    }
  };
  const recordDecision = async () => {
    if (await act(() => api(`/api/applications/${id}/decision`, { body: { decision, note: decisionNote, confirm: confirmed } }), "Decision recorded")) setDecisionOpen(false);
  };
  const accepted = data.findings.filter((f) => f.status === "ACCEPTED");
  const live = data.letters.find((l) => ["DRAFT", "PENDING_APPROVAL"].includes(l.status));

  return (
    <>
      <div className="pagehead">
        <div className="col" style={{ gap: 5 }}>
          <div className="crumb"><Link to="/queue">Scrutiny queue</Link> › <span className="mono">{app.id}</span></div>
          <div className="row" style={{ flexWrap: "wrap" }}>
            <h1>{app.institution}, {app.city}</h1>
            <span className="tag">{app.app_type_label}</span><span className="tag">{app.cycle}</span><span className="tag">{app.state}</span>
            <AppStatusChip status={app.status} />
          </div>
          <div className="crumb">
            Submitted {fmtDateTime(app.submitted_at)} · pre-checked in {app.precheck_seconds ?? "—"} s · {app.rulebook_version} · {data.documents.length} documents
            {data.assigned_to_name && ` · assigned to ${data.assigned_to_name}`}
            {data.processing && <Spinner label="re-checking…" />}
          </div>
        </div>
        <div className="actions">
          <div className="col" style={{ gap: 4, minWidth: 150 }}>
            <span className="row small"><span className="lbl">Risk score</span><b className="right" style={{ fontSize: 17, color: app.risk_score >= 60 ? "var(--red)" : "var(--ink)" }}>{app.risk_score}<span className="muted small">/100</span></b></span>
            <Meter value={app.risk_score} tone={app.risk_score >= 60 ? "red" : undefined} />
          </div>
          <OverallChip status={app.overall_status} />
          {user?.role === "scrutinizer" && !data.assigned_to_name && app.status !== "DECIDED" && (
            <button className="btn" onClick={() => act(() => api(`/api/applications/${id}/assign`, { method: "POST" }), "Assigned to you")}><UserCheck />Assign to me</button>
          )}
          {(user?.role === "scrutinizer" || user?.role === "senior_officer") && app.status !== "DECIDED" && (
            <button className="btn" disabled={busy || data.processing} onClick={() => act(() => api(`/api/applications/${id}/precheck`, { method: "POST" }), "Pre-check queued")}><RefreshCw />Re-run pre-check</button>
          )}
          <button className="btn" onClick={() => navigate(`/applications/${id}/report`)}><FileChartColumn />Validation report</button>
          {data.permissions.draft_letter && !live && (
            <button className="btn primary" onClick={() => { setPicked(accepted.map((f) => f.id)); setLetterOpen(true); }}><FilePenLine />Draft deficiency letter</button>
          )}
          {data.permissions.decide && <button className="btn primary" onClick={() => setDecisionOpen(true)}><Gavel />Record decision</button>}
        </div>
      </div>

      {app.decision && <div className="banner ok"><span className="grow"><b>Decision: {app.decision.label}</b> by {app.decision.by} on {fmtDate(app.decision.at)}<span>{app.decision.note}</span></span></div>}

      <div className="ws">
        <QueueMini current={id} />
        <div className="card viewer">
          <div className="vbar">
            {data.documents.map((d) => {
              const v = verifByDoc[d.id];
              const flagged = data.findings.some((f) => f.status === "OPEN" && f.evidence.some((e) => e.document_id === d.id) && f.severity !== "info");
              return (
                <button key={d.id} className={`dtab${doc?.id === d.id ? " on" : ""}`} onClick={() => { setDocId(d.id); setPage(0); setFocus(null); }}
                  title={`${d.slot_label}${v ? ` · ${v.status}` : ""}`}>
                  {flagged && <span style={{ width: 6, height: 6, borderRadius: 3, background: "var(--red)", display: "inline-block" }} />}
                  {shortLabel(d, data.documents)}
                </button>
              );
            })}
          </div>
          {doc ? <DocViewer doc={doc} highlights={highlights} page={page} onPage={setPage} /> : <Empty>No documents.</Empty>}
          {doc && (doc.forensics?.length || doc.signature?.present || doc.photo) ? (
            <div className="vfoot">
              {doc.signature?.present && <span>Signature: {doc.signature.summary}</span>}
              {doc.photo?.gps_lat != null && <span>GPS {doc.photo.gps_lat?.toFixed(4)}, {doc.photo.gps_lon?.toFixed(4)} · taken {fmtDate(doc.photo.taken_at)}</span>}
              {doc.forensics?.map((s, i) => <span key={i} className="chip xs purple" title={s.message}>{s.title}</span>)}
            </div>
          ) : null}
        </div>
        <div className="card fpane">
          <div className="chd">
            <h2>Findings</h2>
            {app.counts.critical > 0 && <span className="chip xs solidred">{app.counts.critical} critical</span>}
            {app.counts.high > 0 && <span className="chip xs red">{app.counts.high} high</span>}
            {app.counts.warning > 0 && <span className="chip xs amber">{app.counts.warning} warning</span>}
            <span className="right row small">
              <button className={`btn sm${filter === "all" ? " primary" : ""}`} onClick={() => setFilter("all")}>All {data.findings.length}</button>
              <button className={`btn sm${filter === "open" ? " primary" : ""}`} onClick={() => setFilter("open")}>Open {app.counts.open}</button>
            </span>
          </div>
          <div className="col" style={{ padding: 12, gap: 8, maxHeight: "calc(100vh - 230px)", overflow: "auto" }}>
            {findings.length === 0 && <Empty>{data.processing ? <Spinner label="Pre-check running…" /> : "No findings."}</Empty>}
            {findings.map((f) => {
              const docEv = f.evidence.find((e) => e.document_id);
              return (
                <FindingCard key={f.id} f={f} open={f.id === openId} canReview={data.permissions.review}
                  verification={docEv ? verifByDoc[docEv.document_id!] : undefined}
                  onOpen={() => { setOpenId(f.id); if (docEv) showEvidence(docEv); }} onShow={showEvidence} onDecide={(x, a) => decide(x, a)} />
              );
            })}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="tabs" style={{ padding: "0 8px" }}>
          <button className={tab === "verify" ? "on" : ""} onClick={() => setTab("verify")}>Issuer verification ({data.verifications.length})</button>
          <button className={tab === "record" ? "on" : ""} onClick={() => setTab("record")}>AICTE record vs application</button>
          <button className={tab === "letters" ? "on" : ""} onClick={() => setTab("letters")}>Deficiency letters ({data.letters.length})</button>
          <button className={tab === "activity" ? "on" : ""} onClick={() => setTab("activity")}>Activity</button>
        </div>
        {tab === "verify" && (
          <div className="tablewrap"><table>
            <thead><tr><th>Document</th><th>Source</th><th>Method</th><th>Result</th><th>Compared</th><th>Checked (IST)</th></tr></thead>
            <tbody>{data.verifications.map((v) => (
              <tr key={v.id}>
                <td><b style={{ fontWeight: 550 }}>{v.doc_label}</b></td><td>{v.source}</td><td className="muted small">{v.method}{v.reference ? ` · ${v.reference}` : ""}</td>
                <td><StatusChip status={v.status} xs /></td>
                <td className="small">{v.compared.length ? v.compared.map((c, i) => (
                  <div key={i} style={{ color: c.match === false ? "var(--red)" : undefined }}>{c.field}: {String(c.registry ?? "—")} {c.match === false ? `≠ ${String(c.submitted ?? "—")}` : c.match ? "✓" : ""}</div>
                )) : <span className="muted">{v.note}</span>}</td>
                <td className="mono small">{fmtTime(v.checked_at)}</td>
              </tr>))}</tbody>
          </table></div>
        )}
        {tab === "record" && data.record && (
          <div className="cbody" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div>
              <div className="lbl">AICTE record · last approval {data.record.last_approved_cycle}</div>
              <table><thead><tr><th>Programme</th><th className="r">Approved intake</th></tr></thead>
                <tbody>{data.record.programmes.map((p) => <tr key={p.programme}><td>{p.programme}</td><td className="r num">{p.approved_intake}</td></tr>)}</tbody></table>
              <p className="small muted" style={{ marginTop: 8 }}>{data.record.faculty_on_record} faculty on record · {data.record.approval_status.toLowerCase()} · accreditation {data.record.accreditation_no || "none"}</p>
            </div>
            <div>
              <div className="lbl">This application</div>
              <table><thead><tr><th>Programme</th><th className="r">Requested</th></tr></thead>
                <tbody>{data.form.programmes.map((p) => {
                  const rec = data.record?.programmes.find((r) => r.programme === p.name);
                  const up = rec && Number(p.intake_requested) > rec.approved_intake;
                  return <tr key={p.name}><td>{p.name}{!rec && <span className="chip xs blue" style={{ marginLeft: 6 }}>new</span>}</td>
                    <td className="r num" style={{ color: up ? "var(--red)" : undefined, fontWeight: up ? 600 : undefined }}>{p.intake_requested}</td></tr>;
                })}</tbody></table>
              <p className="small muted" style={{ marginTop: 8 }}>Fire NOC declared valid till {fmtDate(String(data.form.fire_noc_valid_till || ""))} · {String(data.form.computer_count || "—")} computers · {String(data.form.built_up_area_m2 || "—")} m² built-up</p>
            </div>
          </div>
        )}
        {tab === "letters" && (
          <div className="cbody col">
            {data.letters.length === 0 && <span className="muted">No letters yet. Accept findings, then use “Draft deficiency letter”.</span>}
            {data.letters.map((l) => <LetterPanel key={l.id} detail={data} letter={l} onChanged={() => reload(true)} />)}
          </div>
        )}
        {tab === "activity" && <Activity appId={id} />}
      </div>

      {override && (
        <Modal title={`Override ${override.ref}`} onClose={() => setOverride(null)}
          footer={<><button className="btn" onClick={() => setOverride(null)}>Cancel</button>
            <button className="btn primary" disabled={busy || reason.trim().length < 10} onClick={() => decide(override, "override", reason)}>Override</button></>}>
          <p>{override.title}</p>
          <div className="field"><label htmlFor="why">Why is this finding not a problem?</label>
            <textarea id="why" className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Confirmed with the issuing office by phone on …" />
            <span className="hint">At least 10 characters. Your reason is stored in the audit trail.</span></div>
        </Modal>
      )}
      {letterOpen && (
        <Modal title="Draft deficiency letter" onClose={() => setLetterOpen(false)}
          footer={<><button className="btn" onClick={() => setLetterOpen(false)}>Cancel</button><button className="btn primary" disabled={busy || !picked.length} onClick={draftLetter}>Create draft</button></>}>
          <p className="small muted">Pick the findings to include. Preliminary forensic flags are worded as a request for the original document, never as an accusation.</p>
          {data.findings.filter((f) => f.status !== "OVERRIDDEN").map((f) => (
            <label key={f.id} className="row small" style={{ alignItems: "flex-start" }}>
              <input type="checkbox" checked={picked.includes(f.id)} onChange={(e) => setPicked(e.target.checked ? [...picked, f.id] : picked.filter((x) => x !== f.id))} />
              <span><SeverityChip severity={f.severity} /> {f.title} {f.status === "ACCEPTED" && <span className="chip xs blue">accepted</span>}</span>
            </label>
          ))}
        </Modal>
      )}
      {decisionOpen && (
        <Modal title="Record the decision" onClose={() => setDecisionOpen(false)}
          footer={<><button className="btn" onClick={() => setDecisionOpen(false)}>Cancel</button><button className="btn primary" disabled={busy || !confirmed} onClick={recordDecision}>Record decision</button></>}>
          {data.unreviewed_blocking > 0 && <div className="banner warn small"><span className="grow"><b>{data.unreviewed_blocking} critical/high finding(s) are not reviewed yet.</b><span>Approval is blocked until each is accepted or overridden.</span></span></div>}
          <div className="field"><label htmlFor="dec">Decision</label>
            <select id="dec" className="input" value={decision} onChange={(e) => setDecision(e.target.value)}>
              {Object.entries(data.decisions).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></div>
          <div className="field"><label htmlFor="dn">Reasons and conditions</label>
            <textarea id="dn" className="input" value={decisionNote} onChange={(e) => setDecisionNote(e.target.value)} />
            {decision === "NOT_APPROVED" && <span className="hint">An adverse decision needs a written reason of at least 20 characters.</span>}</div>
          <label className="row small"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
            I have reviewed the evidence myself. PRAMAAN's findings are advisory.</label>
        </Modal>
      )}
    </>
  );
}
