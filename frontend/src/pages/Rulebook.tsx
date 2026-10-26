import { Check, FlaskConical, Play, Plus, Save, Send, Trash2, Undo2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ApiError, api, Condition, Meta, Rule, RuleRow, RulebookContent, RulebookVersion } from "../api";
import { useAuth } from "../auth";
import { Empty, ErrorBox, fmtDate, fmtDateTime, SeverityChip, Spinner, useLoad, useToast } from "../components/ui";

const FACTS = [
  "application.as_of_date", "application.cycle", "application.type", "institution.name", "institution.state_code",
  "form.fire_noc_valid_till", "form.computer_count", "form.built_up_area_m2", "form.total_intake", "form.land_area_acres",
  "doc.FIRE_NOC.valid_till", "doc.FIRE_NOC.premises_name", "doc.FIRE_NOC.built_up_area", "doc.STRUCTURAL_STABILITY.valid_till",
  "doc.BUILDING_COMPLETION.built_up_area", "doc.AFFILIATION_LETTER.academic_year", "doc.NBA_ACCREDITATION.valid_till",
  "doc.TER_RECEIPT.amount", "doc.LAND_DEED.area_acres", "derived.intake_over_affiliation", "derived.programmes_missing_in_affiliation",
  "derived.intake_over_records", "derived.faculty_not_in_records", "derived.faculty_count", "derived.student_faculty_ratio",
  "derived.student_estimate", "derived.required_computers", "derived.lab_photo_count", "derived.photos_far_from_campus",
  "derived.photos_without_location", "derived.photos_outside_window", "this.verify_status", "this.verify_external",
  "this.ocr_confidence", "this.misfiled_as", "this.unreadable", "this.detected_type",
];
const STATUS_CLASS: Record<string, string> = { PUBLISHED: "green", DRAFT: "blue", PENDING_APPROVAL: "amber", RETIRED: "slate", REJECTED: "red" };

function CondEditor({ c, ops, editable, onChange, onRemove }: { c: Condition; ops: Record<string, string>; editable: boolean;
  onChange: (c: Condition) => void; onRemove: () => void }) {
  const usesRef = c.ref !== undefined;
  const noValue = ["exists", "missing", "not_empty", "empty"].includes(c.op);
  return (
    <div className="cond">
      <input className="input mono" list="facts" value={c.fact} disabled={!editable} onChange={(e) => onChange({ ...c, fact: e.target.value })} aria-label="Fact" />
      <select className="input" value={c.op} disabled={!editable} onChange={(e) => onChange({ ...c, op: e.target.value })} aria-label="Operator">
        {Object.entries(ops).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      {noValue ? <span className="muted small">—</span> : (
        <span className="row">
          <select className="input" style={{ width: 82 }} value={usesRef ? "ref" : "value"} disabled={!editable} aria-label="Compare with"
            onChange={(e) => { const { ref: _r, value: _v, ...rest } = c; onChange(e.target.value === "ref" ? { ...rest, ref: "" } : { ...rest, value: "" }); }}>
            <option value="value">value</option><option value="ref">fact</option>
          </select>
          <input className={`input${usesRef ? " mono" : ""}`} list={usesRef ? "facts" : undefined} disabled={!editable}
            value={usesRef ? c.ref ?? "" : Array.isArray(c.value) ? (c.value as string[]).join(", ") : String(c.value ?? "")}
            onChange={(e) => {
              const raw = e.target.value;
              if (usesRef) onChange({ ...c, ref: raw });
              else if (c.op === "in" || c.op === "not_in") onChange({ ...c, value: raw.split(",").map((x) => x.trim()) });
              else onChange({ ...c, value: raw !== "" && !isNaN(Number(raw)) ? Number(raw) : raw });
            }} aria-label="Value" />
        </span>
      )}
      {c.op === "within_days" || c.op === "before" || c.op === "after" ? (
        <input className="input num" disabled={!editable} value={c.days ?? ""} placeholder="days" onChange={(e) => onChange({ ...c, days: e.target.value === "" ? undefined : Number(e.target.value) })} aria-label="Days" />
      ) : <span />}
      {editable ? <button className="btn link" onClick={onRemove} aria-label="Remove condition"><Trash2 size={14} /></button> : <span />}
    </div>
  );
}

function RowEditor({ row, meta, editable, onChange, onRemove, index }: { row: RuleRow; meta: Meta; editable: boolean; index: number;
  onChange: (r: RuleRow) => void; onRemove: () => void }) {
  return (
    <div className="rule-row">
      <div className="row"><b>Row {index + 1}</b><SeverityChip severity={row.severity} />
        {editable && <button className="btn link right" onClick={onRemove}><Trash2 size={14} /> Remove row</button>}</div>
      <div className="lbl">When all of these hold</div>
      {row.when.map((c, i) => (
        <CondEditor key={i} c={c} ops={meta.operators} editable={editable}
          onChange={(nc) => onChange({ ...row, when: row.when.map((x, j) => (j === i ? nc : x)) })}
          onRemove={() => onChange({ ...row, when: row.when.filter((_, j) => j !== i) })} />
      ))}
      {editable && <div><button className="btn sm" onClick={() => onChange({ ...row, when: [...row.when, { fact: "", op: "exists" }] })}><Plus />Condition</button></div>}
      <div style={{ display: "grid", gridTemplateColumns: "140px 190px 1fr", gap: 8 }}>
        <select className="input" value={row.severity} disabled={!editable} onChange={(e) => onChange({ ...row, severity: e.target.value })} aria-label="Severity">
          {meta.severities.map((s) => <option key={s}>{s}</option>)}
        </select>
        <select className="input" value={row.category} disabled={!editable} onChange={(e) => onChange({ ...row, category: e.target.value })} aria-label="Category">
          {meta.categories.map((s) => <option key={s}>{s}</option>)}
        </select>
        <input className="input" value={row.title} disabled={!editable} onChange={(e) => onChange({ ...row, title: e.target.value })} placeholder="Finding shown to the scrutinizer" aria-label="Finding title" />
      </div>
      <input className="input" value={row.message || ""} disabled={!editable} onChange={(e) => onChange({ ...row, message: e.target.value })}
        placeholder="Explanation; {fact} inserts a value" aria-label="Finding message" />
    </div>
  );
}

export default function Rulebook() {
  const { user } = useAuth();
  const toast = useToast();
  const meta = useLoad(() => api<Meta>("/api/meta"), []);
  const versions = useLoad(() => api<RulebookVersion[]>("/api/rulebook"), []);
  const [vid, setVid] = useState<number | null>(null);
  const [version, setVersion] = useState<RulebookVersion | null>(null);
  const [content, setContent] = useState<RulebookContent | null>(null);
  const [note, setNote] = useState("");
  const [ruleId, setRuleId] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [tryId, setTryId] = useState("APP-2026-00112");
  const [tryResult, setTryResult] = useState<{ institution: string; matches: { rule_id: string; row: number; severity: string; title: string; message: string }[] } | null>(null);
  const [reviewNote, setReviewNote] = useState("");

  const loadVersion = async (id: number) => {
    const v = await api<RulebookVersion>(`/api/rulebook/${id}`);
    setVersion(v);
    setContent(v.content!);
    setNote(v.change_note);
    setDirty(false);
    setProblems([]);
    setRuleId((r) => r ?? v.content!.rules[0]?.rule_id ?? null);
    return v;
  };
  useEffect(() => {
    if (!vid && versions.data?.length) {
      const pick = versions.data.find((v) => v.status === "DRAFT" || v.status === "PENDING_APPROVAL") || versions.data.find((v) => v.status === "PUBLISHED");
      if (pick) setVid(pick.id);
    }
  }, [versions.data, vid]);
  useEffect(() => { if (vid) loadVersion(vid).catch((e) => toast(e.message, true)); }, [vid]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (version?.dry_run?.status !== "running") return;
    const t = window.setInterval(() => vid && api<RulebookVersion>(`/api/rulebook/${vid}`).then((v) => { if (v.dry_run?.status !== "running") { setVersion(v); } }), 1200);
    return () => window.clearInterval(t);
  }, [version?.dry_run?.status, vid]);

  const groups = useMemo(() => {
    const g: Record<string, Rule[]> = {};
    for (const r of content?.rules || []) (g[r.group || "Other"] ||= []).push(r);
    return g;
  }, [content]);

  if (meta.error || versions.error) return <ErrorBox error={(meta.error || versions.error)!} />;
  if (!meta.data || !versions.data) return <Empty><Spinner label="Loading rulebook…" /></Empty>;
  const editable = version?.status === "DRAFT" && user?.role === "rule_admin";
  const rule = content?.rules.find((r) => r.rule_id === ruleId);
  const published = versions.data.find((v) => v.status === "PUBLISHED");
  const openDraft = versions.data.find((v) => v.status === "DRAFT" || v.status === "PENDING_APPROVAL");

  const updateRule = (r: Rule) => {
    if (!content) return;
    setContent({ ...content, rules: content.rules.map((x) => (x.rule_id === ruleId ? r : x)) });
    setRuleId(r.rule_id);
    setDirty(true);
  };
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try {
      await fn();
      toast(ok);
      setProblems([]);
      await versions.reload(true);
      if (vid) await loadVersion(vid);
    } catch (e) {
      if (e instanceof ApiError && e.problems.length) setProblems(e.problems);
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const save = () => act(() => api(`/api/rulebook/${vid}`, { method: "PUT", body: { content, change_note: note } }), "Draft saved");
  const newDraft = async () => {
    setBusy(true);
    try {
      const v = await api<RulebookVersion>("/api/rulebook", { body: { base_id: published!.id, change_note: "" } });
      await versions.reload(true);
      setVid(v.id);
      toast("New draft created from the published version");
    } catch (e) {
      toast((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const addRule = () => {
    if (!content) return;
    const id = `NEW-${content.rules.length + 1}`;
    const r: Rule = { rule_id: id, title: "New rule", group: rule?.group || "Other", source: "APH 2026-27", scope: "application", enabled: true,
      applies_to: { app_types: [], states: [] }, rows: [{ when: [{ fact: "", op: "exists" }], severity: "warning", category: "COMPLIANCE_GAP", title: "Describe the finding" }] };
    setContent({ ...content, rules: [...content.rules, r] });
    setRuleId(id);
    setDirty(true);
  };
  const runTry = async () => {
    try {
      if (dirty) await api(`/api/rulebook/${vid}`, { method: "PUT", body: { content, change_note: note } });
      setDirty(false);
      setTryResult(await api(`/api/rulebook/${vid}/test`, { body: { application_id: tryId } }));
    } catch (e) {
      if (e instanceof ApiError && e.problems.length) setProblems(e.problems);
      toast((e as Error).message, true);
    }
  };

  return (
    <>
      <div className="pagehead">
        <div><h1>Rulebook</h1><div className="crumb">Checks derived from the Approval Process Handbook. Edited as data, approved by a second officer, versioned per cycle.</div></div>
        <div className="actions">
          {user?.role === "rule_admin" && !openDraft && published && <button className="btn primary" onClick={newDraft} disabled={busy}><Plus />New draft from {published.label}</button>}
        </div>
      </div>
      <datalist id="facts">{FACTS.map((f) => <option key={f} value={f} />)}</datalist>
      <div style={{ display: "grid", gridTemplateColumns: "250px minmax(0,1fr)", gap: 14, alignItems: "start" }}>
        <div className="card">
          <div className="chd"><h2>Versions</h2></div>
          <div className="col" style={{ padding: 8, gap: 4 }}>
            {versions.data.map((v) => (
              <button key={v.id} className={`qi${v.id === vid ? " on" : ""}`} style={{ all: "unset", padding: "8px 10px", borderRadius: 8, cursor: "pointer", background: v.id === vid ? "var(--blue-bg)" : undefined }}
                onClick={() => { setVid(v.id); setRuleId(null); setTryResult(null); }}>
                <span className="row"><b>{v.label}</b><span className={`chip xs right ${STATUS_CLASS[v.status]}`}>{v.status.replace("_", " ").toLowerCase()}</span></span>
                <span className="small muted" style={{ display: "block" }}>{v.change_note || "—"}</span>
                <span className="small faint" style={{ display: "block" }}>{v.created_by || "system"} · {fmtDate(v.created_at)}</span>
              </button>
            ))}
          </div>
        </div>
        {!version || !content ? <Empty><Spinner /></Empty> : (
          <div className="col" style={{ gap: 14 }}>
            <div className="card">
              <div className="chd">
                <h2>{version.label}</h2><span className={`chip ${STATUS_CLASS[version.status]}`}>{version.status.replace("_", " ").toLowerCase()}</span>
                <span className="sub">{content.rules.length} rules · made by {version.created_by || "system"}{version.reviewed_by ? ` · reviewed by ${version.reviewed_by} ${fmtDateTime(version.reviewed_at)}` : ""}{version.effective_from ? ` · effective ${fmtDate(version.effective_from)}` : ""}</span>
                <span className="right">
                  {editable && <>
                    <button className="btn sm" onClick={save} disabled={busy || !dirty}><Save />Save</button>
                    <button className="btn sm" onClick={() => act(async () => { if (dirty) await api(`/api/rulebook/${vid}`, { method: "PUT", body: { content, change_note: note } }); await api(`/api/rulebook/${vid}/dry-run`, { method: "POST" }); }, "Dry run started")} disabled={busy}><FlaskConical />Dry run</button>
                    <button className="btn sm primary" onClick={() => act(async () => { if (dirty) await api(`/api/rulebook/${vid}`, { method: "PUT", body: { content, change_note: note } }); await api(`/api/rulebook/${vid}/submit`, { method: "POST" }); }, "Sent for checker approval")} disabled={busy}><Send />Submit for approval</button>
                  </>}
                  {version.status === "PENDING_APPROVAL" && user?.role === "senior_officer" && <>
                    <input className="input" style={{ width: 200, height: 28 }} placeholder="Review note" value={reviewNote} onChange={(e) => setReviewNote(e.target.value)} aria-label="Review note" />
                    <button className="btn sm" onClick={() => act(() => api(`/api/rulebook/${vid}/review`, { body: { approve: false, note: reviewNote } }), "Returned to the maker")} disabled={busy}><Undo2 />Return</button>
                    <button className="btn sm primary" onClick={() => act(() => api(`/api/rulebook/${vid}/review`, { body: { approve: true, note: reviewNote } }), "Published. Open applications are being re-checked.")} disabled={busy}><Check />Approve and publish</button>
                  </>}
                </span>
              </div>
              <div className="cbody col">
                <div className="field"><label htmlFor="cn">What changed</label>
                  <input id="cn" className="input" value={note} disabled={!editable} onChange={(e) => { setNote(e.target.value); setDirty(true); }} placeholder="Required before sending for approval" /></div>
                {version.status === "PENDING_APPROVAL" && user?.role !== "senior_officer" && <div className="banner info small"><span className="grow">Waiting for a senior officer. The maker cannot approve their own change.</span></div>}
                {version.review_note && <div className="small muted">Review note: {version.review_note}</div>}
                {problems.length > 0 && <div className="banner bad small"><span className="grow"><b>Fix these before saving</b>{problems.map((p) => <span key={p}>{p}</span>)}</span></div>}
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "260px minmax(0,1fr)", gap: 14, alignItems: "start" }}>
              <div className="card">
                <div className="chd"><h2>Rules</h2>{editable && <button className="btn sm right" onClick={addRule}><Plus />Rule</button>}</div>
                <div style={{ maxHeight: "60vh", overflow: "auto" }}>
                  {Object.entries(groups).map(([g, rules]) => (
                    <div key={g}>
                      <div className="navlabel">{g}</div>
                      {rules.map((r) => (
                        <button key={r.rule_id} onClick={() => setRuleId(r.rule_id)}
                          style={{ all: "unset", display: "block", padding: "6px 14px", cursor: "pointer", width: "100%", boxSizing: "border-box", background: r.rule_id === ruleId ? "var(--blue-bg)" : undefined }}>
                          <span className="mono" style={{ fontWeight: 600, fontSize: 11 }}>{r.rule_id}</span>{r.enabled === false && <span className="chip xs slate" style={{ marginLeft: 6 }}>off</span>}
                          <span className="small muted" style={{ display: "block" }}>{r.title}</span>
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
              {!rule ? <div className="card"><Empty>Pick a rule.</Empty></div> : (
                <div className="card">
                  <div className="chd">
                    <input className="input mono" style={{ width: 160 }} value={rule.rule_id} disabled={!editable} onChange={(e) => updateRule({ ...rule, rule_id: e.target.value.toUpperCase() })} aria-label="Rule ID" />
                    <input className="input grow" value={rule.title} disabled={!editable} onChange={(e) => updateRule({ ...rule, title: e.target.value })} aria-label="Rule title" />
                    <label className="row small"><input type="checkbox" checked={rule.enabled !== false} disabled={!editable} onChange={(e) => updateRule({ ...rule, enabled: e.target.checked })} />on</label>
                  </div>
                  <div className="cbody col" style={{ gap: 12 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                      <div className="field"><label>Handbook source</label><input className="input" value={rule.source || ""} disabled={!editable} onChange={(e) => updateRule({ ...rule, source: e.target.value })} /></div>
                      <div className="field"><label>Group</label><input className="input" value={rule.group || ""} disabled={!editable} onChange={(e) => updateRule({ ...rule, group: e.target.value })} /></div>
                      <div className="field"><label>Scope</label>
                        <select className="input" value={rule.scope || "application"} disabled={!editable} onChange={(e) => updateRule({ ...rule, scope: e.target.value })}>
                          <option value="application">Whole application</option><option value="each_document">Each document (facts start with this.)</option>
                        </select></div>
                      <div className="field"><label>Applies to</label>
                        <div className="row" style={{ flexWrap: "wrap" }}>{Object.entries(meta.data.app_types).map(([k, v]) => {
                          const on = (rule.applies_to?.app_types || []).includes(k);
                          return <label key={k} className="row small"><input type="checkbox" checked={on} disabled={!editable}
                            onChange={() => { const cur = rule.applies_to?.app_types || []; updateRule({ ...rule, applies_to: { ...rule.applies_to, app_types: on ? cur.filter((x) => x !== k) : [...cur, k] } }); }} />{v}</label>;
                        })}<span className="small muted">(none ticked = all)</span></div></div>
                    </div>
                    <div className="lbl">Decision table · every matching row becomes a finding</div>
                    {rule.rows.map((row, i) => (
                      <RowEditor key={i} index={i} row={row} meta={meta.data!} editable={editable}
                        onChange={(nr) => updateRule({ ...rule, rows: rule.rows.map((x, j) => (j === i ? nr : x)) })}
                        onRemove={() => updateRule({ ...rule, rows: rule.rows.filter((_, j) => j !== i) })} />
                    ))}
                    {editable && <div className="row">
                      <button className="btn sm" onClick={() => updateRule({ ...rule, rows: [...rule.rows, { when: [{ fact: "", op: "exists" }], severity: "warning", category: rule.rows[0]?.category || "COMPLIANCE_GAP", title: "" }] })}><Plus />Row</button>
                      <button className="btn sm danger right" onClick={() => { setContent({ ...content, rules: content.rules.filter((r) => r.rule_id !== ruleId) }); setRuleId(null); setDirty(true); }}><Trash2 />Delete rule</button>
                    </div>}
                  </div>
                </div>
              )}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 14, alignItems: "start" }}>
              <div className="card">
                <div className="chd"><h2>Try on an application</h2><span className="sub">which rows match, and why</span></div>
                <div className="cbody col">
                  <div className="row"><input className="input mono" style={{ width: 200 }} value={tryId} onChange={(e) => setTryId(e.target.value)} aria-label="Application ID" />
                    <button className="btn sm" onClick={runTry}><Play />Evaluate</button></div>
                  {tryResult && <>
                    <div className="small muted">{tryResult.institution}: {tryResult.matches.length} row(s) matched</div>
                    {tryResult.matches.map((m, i) => (
                      <div key={i} className="row small" style={{ alignItems: "flex-start" }}>
                        <span className="mono muted" style={{ width: 110 }}>{m.rule_id} r{m.row}</span><SeverityChip severity={m.severity} />
                        <span className="grow"><b style={{ fontWeight: 550 }}>{m.title}</b><span className="muted" style={{ display: "block" }}>{m.message}</span></span>
                      </div>
                    ))}
                  </>}
                </div>
              </div>
              <div className="card">
                <div className="chd"><h2>Dry run</h2><span className="sub">this version vs the published one, on every application this cycle</span></div>
                <div className="cbody col">
                  {!version.dry_run && <span className="muted small">{editable ? "Run a dry run before sending for approval." : "No dry run for this version."}</span>}
                  {version.dry_run?.status === "running" && <Spinner label="Running…" />}
                  {version.dry_run?.findings && <>
                    <div className="row"><b style={{ fontSize: 22 }}>{version.dry_run.findings.draft}</b><span className="muted small">findings with this version vs {version.dry_run.findings.published} published, across {version.dry_run.applications} applications · {fmtDateTime(version.dry_run.ran_at)}</span></div>
                    <table><thead><tr><th>Rule</th><th className="r">Published</th><th className="r">This version</th></tr></thead>
                      <tbody>{Object.entries(version.dry_run.by_rule || {}).filter(([, v]) => v.draft !== v.published).map(([k, v]) => (
                        <tr key={k}><td className="mono small">{k}</td><td className="r num">{v.published}</td><td className="r num"><b>{v.draft}</b></td></tr>))}</tbody></table>
                    {(version.dry_run.changed || []).map((c) => (
                      <div key={c.application_id} className="small"><span className="mono">{c.application_id}</span> {c.institution}:
                        {c.added.map((a) => <span key={a} className="chip xs red" style={{ marginLeft: 4 }}>+ {a}</span>)}
                        {c.removed.map((a) => <span key={a} className="chip xs green" style={{ marginLeft: 4 }}>− {a}</span>)}</div>
                    ))}
                    {!Object.values(version.dry_run.by_rule || {}).some((v) => v.draft !== v.published) && <span className="small muted">No difference from the published version.</span>}
                  </>}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
