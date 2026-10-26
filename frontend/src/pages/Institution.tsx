import { Eye, FilePlus2, FileText, Send, Trash2, Upload } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, AppSummary, ChecklistItem, Detail, Doc, Programme } from "../api";
import DocViewer from "../components/DocViewer";
import {
  AppStatusChip, bytes, Empty, ErrorBox, fmtDate, fmtDateTime, Modal, SeverityChip, Spinner, StatusChip, useLoad, useToast,
} from "../components/ui";
import { useT } from "../i18n";

const APP_TYPES: Record<string, string> = { EOA: "Extension of Approval", INTAKE_INCREASE: "Increase in intake", NEW_PROGRAMME: "New programme" };

export function MyApplications() {
  const toast = useToast();
  const t = useT();
  const [params] = useSearchParams();
  const q = params.get("q") || "";
  const { data, error, loading, reload } = useLoad(() => api<AppSummary[]>(`/api/applications?sort=recent${q ? `&q=${encodeURIComponent(q)}` : ""}`), [q]);
  const [creating, setCreating] = useState(false);
  const [type, setType] = useState("EOA");
  const create = async () => {
    try {
      const app = await api<AppSummary>("/api/applications", { body: { app_type: type } });
      toast(`Draft ${app.id} created`);
      setCreating(false);
      reload();
    } catch (e) {
      toast((e as Error).message, true);
    }
  };
  return (
    <>
      <div className="pagehead">
        <div><div className="crumb">Institution portal</div><h1>{t("My applications")}</h1></div>
        <div className="actions"><button className="btn primary" onClick={() => setCreating(true)}><FilePlus2 />{t("Start a new application")}</button></div>
      </div>
      <div className="banner info"><span className="grow">{t("The pre-check is advisory. AICTE officials take the final decision on every application.")}
        <span>Documents are checked as soon as you upload them, so you can fix problems before you submit.</span></span></div>
      {error && <ErrorBox error={error} />}
      <div className="card">
        {loading && !data ? <Empty><Spinner label="Loading…" /></Empty> : !data?.length ? <Empty>No applications yet.</Empty> : (
          <div className="tablewrap"><table>
            <thead><tr><th>Application</th><th>Type</th><th>Cycle</th><th>Status</th><th>Pre-check</th><th>Submitted</th><th /></tr></thead>
            <tbody>
              {data.map((a) => (
                <tr key={a.id}>
                  <td className="mono"><Link to={`/my/${a.id}`}>{a.id}</Link></td>
                  <td>{a.app_type_label}</td><td>{a.cycle}</td><td><AppStatusChip status={a.status} /></td>
                  <td className="row">
                    {a.counts.critical > 0 && <span className="chip xs solidred">{a.counts.critical} critical</span>}
                    {a.counts.high > 0 && <span className="chip xs red">{a.counts.high} high</span>}
                    {a.counts.warning > 0 && <span className="chip xs amber">{a.counts.warning} warnings</span>}
                    {!a.counts.critical && !a.counts.high && !a.counts.warning && <span className="chip xs green">No issues</span>}
                  </td>
                  <td>{fmtDate(a.submitted_at)}</td>
                  <td className="r"><Link className="btn sm" to={`/my/${a.id}`}>{t("Open")}</Link></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </div>
      {creating && (
        <Modal title={t("Start a new application")} onClose={() => setCreating(false)}
          footer={<><button className="btn" onClick={() => setCreating(false)}>Cancel</button><button className="btn primary" onClick={create}>Create draft</button></>}>
          <div className="field">
            <label htmlFor="type">Application type</label>
            <select id="type" className="input" value={type} onChange={(e) => setType(e.target.value)}>
              {Object.entries(APP_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <span className="hint">Programmes and intake are pre-filled from your last AICTE approval. You can change them in the form.</span>
          </div>
        </Modal>
      )}
    </>
  );
}

interface Sample { slot: string; filename: string; size: number }

function DocModal({ doc, onClose }: { doc: Doc; onClose: () => void }) {
  const [page, setPage] = useState(0);
  return (
    <Modal title={doc.filename} onClose={onClose}>
      <div className="card" style={{ overflow: "hidden" }}><DocViewer doc={doc} page={page} onPage={setPage} height="52vh" /></div>
      {doc.fields.length > 0 && (
        <table><thead><tr><th>Field read</th><th>Value</th><th className="r">Confidence</th></tr></thead>
          <tbody>{doc.fields.slice(0, 14).map((f, i) => (
            <tr key={i}><td>{f.name.replace(/_/g, " ").replace("intake::", "intake · ")}</td><td>{f.value}</td>
              <td className="r num">{(f.confidence * 100).toFixed(0)}%</td></tr>))}</tbody></table>
      )}
    </Modal>
  );
}

function ChecklistRow({ item, docs, samples, editable, onUpload, onSample, onView, onRemove }: {
  item: ChecklistItem; docs: Doc[]; samples: Sample[]; editable: boolean;
  onUpload: (slot: string, f: File) => void; onSample: (s: Sample) => void; onView: (d: Doc) => void; onRemove: (d: Doc) => void;
}) {
  const t = useT();
  const input = useRef<HTMLInputElement>(null);
  const mine = docs.filter((d) => item.document_ids.includes(d.id));
  const multi = item.doc_type === "LAB_PHOTO";
  const unused = samples.filter((s) => s.slot === item.doc_type && !mine.some((d) => d.filename === s.filename));
  const latest = mine[mine.length - 1];
  return (
    <tr>
      <td>
        <span className="row"><FileText size={14} className="faint" /><b style={{ fontWeight: 550 }}>{item.label}</b></span>
        <span className="faint small">{item.required ? (multi ? `Required · at least ${item.min_count}` : "Required") : "Optional"}</span>
      </td>
      <td><StatusChip status={item.state} xs /></td>
      <td className="small" style={{ maxWidth: 380 }}>
        {mine.length === 0 ? <span className="muted">—</span> : (
          <>
            {item.note && <div>{item.note}</div>}
            {mine.map((d) => (
              <div key={d.id} className="row faint">
                <button className="btn link small" onClick={() => onView(d)}><Eye size={12} /> {d.filename}</button>
                <span>{bytes(d.size)}</span>
                {editable && multi && <button className="btn link" onClick={() => onRemove(d)} aria-label={`Remove ${d.filename}`}><Trash2 size={12} /></button>}
              </div>
            ))}
          </>
        )}
      </td>
      <td className="small muted num" style={{ whiteSpace: "nowrap" }}>{latest ? fmtDate(latest.uploaded_at) : "—"}</td>
      <td className="r">
        {editable && (
          <span className="row" style={{ justifyContent: "flex-end" }}>
            <input ref={input} type="file" className="hidden" accept={multi ? "image/jpeg,image/png" : "application/pdf,image/jpeg,image/png"}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(item.doc_type, f); e.target.value = ""; }} />
            {unused.length > 0 && (mine.length === 0 || multi) && (
              <button className="btn sm" title={`Upload the synthetic sample ${unused[0].filename}`} onClick={() => onSample(unused[0])}>{t("Use sample")}</button>
            )}
            <button className={`btn sm${item.state === "MISSING" || item.state === "INCOMPLETE" || item.state === "EXPIRED" || item.state === "MISMATCH" ? " primary" : ""}`}
              onClick={() => input.current?.click()}>
              <Upload />{mine.length && !multi ? t("Replace") : t("Upload")}
            </button>
          </span>
        )}
      </td>
    </tr>
  );
}

function FormEditor({ detail, onSaved }: { detail: Detail; onSaved: () => void }) {
  const toast = useToast();
  const t = useT();
  const editable = detail.permissions.edit;
  const [form, setForm] = useState(() => JSON.parse(JSON.stringify(detail.form)) as Detail["form"]);
  const [saving, setSaving] = useState(false);
  const set = (k: string, v: unknown) => setForm({ ...form, [k]: v });
  const setProg = (i: number, k: keyof Programme, v: string) => {
    const programmes = form.programmes.map((p, j) => (j === i ? { ...p, [k]: v } : p));
    setForm({ ...form, programmes });
  };
  const save = async () => {
    setSaving(true);
    try {
      await api(`/api/applications/${detail.application.id}/form`, { method: "PUT", body: { form } });
      toast("Form saved. The pre-check is running again.");
      onSaved();
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setSaving(false);
    }
  };
  const text = (k: string) => (form[k] as string | number | undefined) ?? "";
  return (
    <div className="card">
      <div className="chd"><h2>{t("Application form")}</h2><span className="sub">{editable ? "Changes are checked again as soon as you save" : "Read only after submission"}</span></div>
      <div className="cbody col" style={{ gap: 16 }}>
        <div>
          <div className="lbl" style={{ marginBottom: 6 }}>Programmes and intake requested</div>
          <table>
            <thead><tr><th>Programme</th><th>Level</th><th className="r">Intake</th><th /></tr></thead>
            <tbody>
              {form.programmes.map((p, i) => (
                <tr key={i}>
                  <td><input className="input" value={p.name} disabled={!editable} onChange={(e) => setProg(i, "name", e.target.value)} aria-label="Programme name" /></td>
                  <td style={{ width: 110 }}>
                    <select className="input" value={p.level} disabled={!editable} onChange={(e) => setProg(i, "level", e.target.value)} aria-label="Level">
                      {["Diploma", "UG", "PG"].map((l) => <option key={l}>{l}</option>)}
                    </select>
                  </td>
                  <td style={{ width: 110 }}><input className="input num" inputMode="numeric" value={p.intake_requested} disabled={!editable}
                    onChange={(e) => setProg(i, "intake_requested", e.target.value)} aria-label="Intake" /></td>
                  <td style={{ width: 40 }}>{editable && <button className="btn link" onClick={() => setForm({ ...form, programmes: form.programmes.filter((_, j) => j !== i) })} aria-label="Remove programme"><Trash2 size={14} /></button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {editable && <button className="btn sm" style={{ marginTop: 8 }} onClick={() => set("programmes", [...form.programmes, { name: "", level: "UG", intake_requested: 60 }])}>Add programme</button>}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
          <div className="field"><label htmlFor="fnoc">Fire NOC valid till</label>
            <input id="fnoc" type="date" className="input" value={text("fire_noc_valid_till")} disabled={!editable} onChange={(e) => set("fire_noc_valid_till", e.target.value)} /></div>
          <div className="field"><label htmlFor="area">Built-up area (m²)</label>
            <input id="area" className="input" inputMode="numeric" value={text("built_up_area_m2")} disabled={!editable} onChange={(e) => set("built_up_area_m2", e.target.value)} /></div>
          <div className="field"><label htmlFor="pc">Computers in labs</label>
            <input id="pc" className="input" inputMode="numeric" value={text("computer_count")} disabled={!editable} onChange={(e) => set("computer_count", e.target.value)} /></div>
          <div className="field"><label htmlFor="land">Land area (acres)</label>
            <input id="land" className="input" inputMode="decimal" value={text("land_area_acres")} disabled={!editable} onChange={(e) => set("land_area_acres", e.target.value)} /></div>
          <div className="field"><label htmlFor="pr">Principal</label>
            <input id="pr" className="input" value={text("principal_name")} disabled={!editable} onChange={(e) => set("principal_name", e.target.value)} /></div>
          <div className="field"><label htmlFor="em">Contact email</label>
            <input id="em" type="email" className="input" value={text("contact_email")} disabled={!editable} onChange={(e) => set("contact_email", e.target.value)} /></div>
        </div>
        {editable && <div><button className="btn primary" onClick={save} disabled={saving}>{saving ? "Saving…" : t("Save form")}</button></div>}
      </div>
    </div>
  );
}

export function InstitutionApplication() {
  const { id = "" } = useParams();
  const toast = useToast();
  const t = useT();
  const { data, error, loading, reload } = useLoad(() => api<Detail>(`/api/applications/${id}`), [id]);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [tab, setTab] = useState<"docs" | "form" | "letters">("docs");
  const [viewing, setViewing] = useState<Doc | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api<Sample[]>("/api/samples").then(setSamples).catch(() => setSamples([])); }, []);
  useEffect(() => {
    if (!data?.processing) return;
    const timer = window.setInterval(() => reload(true), 1500);
    return () => window.clearInterval(timer);
  }, [data?.processing, reload]);

  const issues = useMemo(() => (data?.findings || []).filter((f) => f.status !== "OVERRIDDEN"), [data]);
  if (error) return <ErrorBox error={error} />;
  if (loading || !data) return <Empty><Spinner label="Loading application…" /></Empty>;
  const app = data.application;
  const critical = issues.filter((f) => f.severity === "critical");
  const warnings = issues.filter((f) => f.severity !== "critical" && f.severity !== "info");
  const openLetter = data.letters.find((l) => l.status === "ISSUED");

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try {
      await fn();
      toast(ok);
      await reload(true);
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const upload = (slot: string, f: File) => {
    const form = new FormData();
    form.append("slot", slot);
    form.append("file", f);
    run(() => api(`/api/applications/${id}/documents`, { form }), `${f.name} uploaded. Checking it now…`);
  };
  const uploadSample = (s: Sample) => run(() => api(`/api/applications/${id}/documents/sample`, { body: s }), `Sample ${s.filename} uploaded. Checking it now…`);
  const remove = (d: Doc) => run(() => api(`/api/documents/${d.id}`, { method: "DELETE" }), `${d.filename} removed`);
  const submit = () => run(async () => { await api(`/api/applications/${id}/submit`, { method: "POST" }); setConfirm(false); }, "Application submitted to AICTE");
  const respond = () => openLetter && run(async () => { await api(`/api/letters/${openLetter.id}/respond`, { body: { message: reply } }); setReply(""); }, "Reply sent to AICTE");

  return (
    <>
      <div className="pagehead">
        <div>
          <div className="crumb"><Link to="/my">{t("My applications")}</Link> › <span className="mono">{app.id}</span></div>
          <div className="row" style={{ marginTop: 4, flexWrap: "wrap" }}>
            <h1>{app.app_type_label} {app.cycle}</h1><AppStatusChip status={app.status} />
            {data.processing && <Spinner label="Checking…" />}
          </div>
        </div>
        <div className="actions">
          {app.submitted_at && <span className="muted small">Submitted {fmtDateTime(app.submitted_at)}</span>}
          {data.permissions.submit && <button className="btn primary" onClick={() => setConfirm(true)} disabled={busy}><Send />{t("Submit application")}</button>}
        </div>
      </div>

      {app.decision && (
        <div className="banner ok"><span className="grow"><b>Decision: {app.decision.label}</b>{app.decision.note && ` · ${app.decision.note}`}
          <span>Recorded by {app.decision.by} on {fmtDate(app.decision.at)}</span></span></div>
      )}
      {openLetter && (
        <div className="banner warn"><span className="grow"><b>AICTE issued deficiency letter {openLetter.id}.</b> Fix the items, upload corrected documents, then reply.
          <span>Issued {fmtDate(openLetter.issued_at)}</span></span><button className="btn sm" onClick={() => setTab("letters")}>{t("Open")}</button></div>
      )}
      {!app.decision && (
        <div className={`banner ${critical.length ? "warn" : "info"}`}>
          <span className="grow">
            <b>{critical.length || warnings.length ? `The pre-check found ${critical.length} critical issue(s) and ${warnings.length} warning(s).` : "The pre-check found no issues so far."}</b>
            {critical.length > 0 && app.status === "DRAFT" && " Fix them before you submit to avoid a deficiency letter."}
            <span>{t("The pre-check is advisory. AICTE officials take the final decision on every application.")}</span>
          </span>
        </div>
      )}

      <div className="tabs" role="tablist">
        <button className={tab === "docs" ? "on" : ""} onClick={() => setTab("docs")} role="tab">{t("Documents and pre-check")}</button>
        <button className={tab === "form" ? "on" : ""} onClick={() => setTab("form")} role="tab">{t("Application form")}</button>
        <button className={tab === "letters" ? "on" : ""} onClick={() => setTab("letters")} role="tab">{t("Deficiency letters")} {data.letters.length ? `(${data.letters.length})` : ""}</button>
      </div>

      {tab === "docs" && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 340px", gap: 14, alignItems: "start" }}>
          <div className="card">
            <div className="chd"><h2>{t("Required documents")}</h2><span className="sub">{app.app_type_label}</span>
              <span className="right small muted">{data.checklist.filter((c) => c.uploaded > 0).length} of {data.checklist.length} types uploaded</span></div>
            <div className="tablewrap"><table className="checklist">
              <thead><tr><th>Document</th><th>Pre-check</th><th>{t("What we found")}</th><th>Uploaded</th><th /></tr></thead>
              <tbody>{data.checklist.map((c) => (
                <ChecklistRow key={c.doc_type} item={c} docs={data.documents} samples={samples} editable={data.permissions.edit}
                  onUpload={upload} onSample={uploadSample} onView={setViewing} onRemove={remove} />
              ))}</tbody>
            </table></div>
          </div>
          <div className="col" style={{ gap: 14 }}>
            <div className="card">
              <div className="chd"><h2>{app.status === "DRAFT" ? t("Before you submit") : t("Pre-check results")}</h2></div>
              <div className="cbody col">
                {issues.length === 0 && <span className="muted">Nothing to fix right now.</span>}
                {issues.map((f) => (
                  <div key={f.id} className="col" style={{ gap: 2, paddingBottom: 8, borderBottom: "1px solid var(--line)" }}>
                    <span className="row"><SeverityChip severity={f.severity} /><b style={{ fontSize: 12.5 }}>{f.title}</b></span>
                    <span className="small muted">{f.message}</span>
                  </div>
                ))}
                {data.permissions.submit && (
                  <>
                    <button className="btn primary" style={{ justifyContent: "center", height: 36 }} onClick={() => setConfirm(true)} disabled={busy}><Send />{t("Submit application")}</button>
                    <span className="small muted" style={{ textAlign: "center" }}>You can still submit with open issues. The scrutinizer will see them.</span>
                  </>
                )}
              </div>
            </div>
            {data.permissions.edit && samples.length > 0 && (
              <div className="banner info small"><span className="grow"><b>Sandbox samples</b><span>“{t("Use sample")}” uploads a synthetic certificate prepared for this demo institution.</span></span></div>
            )}
          </div>
        </div>
      )}

      {tab === "form" && <FormEditor key={JSON.stringify(data.form)} detail={data} onSaved={() => reload(true)} />}

      {tab === "letters" && (
        <div className="col" style={{ gap: 14 }}>
          {data.letters.length === 0 && <div className="card"><Empty>No deficiency letters.</Empty></div>}
          {data.letters.map((l) => (
            <div key={l.id} className="card">
              <div className="chd"><h2>Deficiency letter {l.id}</h2><span className="sub">Issued {fmtDate(l.issued_at)}</span>
                <span className="right"><span className={`chip ${l.status === "ISSUED" ? "amber" : "green"}`}>{l.status === "ISSUED" ? "Awaiting your reply" : "Replied"}</span></span></div>
              <div className="cbody col">
                <ol style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 8 }}>
                  {l.items.map((it, i) => <li key={i}><b>{it.title}</b><div className="small muted">{it.text}</div></li>)}
                </ol>
                {l.note && <div className="small">{l.note}</div>}
                {l.response && <div className="banner ok small"><span className="grow"><b>Your reply</b><span>{l.response.message}</span></span></div>}
                {l.status === "ISSUED" && data.permissions.respond && (
                  <div className="col">
                    <div className="field"><label htmlFor="reply">{t("Reply")}</label>
                      <textarea id="reply" className="input" value={reply} onChange={(e) => setReply(e.target.value)}
                        placeholder="Describe what you corrected. Upload the corrected documents in the Documents tab first." /></div>
                    <div><button className="btn primary" disabled={busy || reply.trim().length < 5} onClick={respond}><Send />Send reply</button></div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {viewing && <DocModal doc={data.documents.find((d) => d.id === viewing.id) || viewing} onClose={() => setViewing(null)} />}
      {confirm && (
        <Modal title="Submit this application?" onClose={() => setConfirm(false)}
          footer={<><button className="btn" onClick={() => setConfirm(false)}>Cancel</button><button className="btn primary" onClick={submit} disabled={busy}>Submit</button></>}>
          <p>After submission the form and documents are locked until AICTE asks for corrections.</p>
          {critical.length > 0 && <div className="banner warn small"><span className="grow"><b>{critical.length} critical issue(s) are still open.</b><span>They will be visible to the scrutinizer and may lead to a deficiency letter.</span></span></div>}
        </Modal>
      )}
    </>
  );
}
