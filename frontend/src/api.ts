// Thin client for the PRAMAAN API. The session token lives in localStorage (per-browser convenience only).

const TOKEN_KEY = "pramaan.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: session lasts for this tab only */
  }
}

export class ApiError extends Error {
  status: number;
  problems: string[];
  constructor(status: number, message: string, problems: string[] = []) {
    super(message);
    this.status = status;
    this.problems = problems;
  }
}

function headers(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...(extra || {}) };
  const t = getToken();
  if (t) h.Authorization = `Bearer ${t}`;
  return h;
}

async function fail(res: Response): Promise<never> {
  let message = `Request failed (${res.status})`;
  let problems: string[] = [];
  try {
    const body = await res.json();
    const d = body.detail;
    if (typeof d === "string") message = d;
    else if (d && typeof d === "object" && !Array.isArray(d)) {
      message = d.message || message;
      problems = d.problems || [];
    } else if (Array.isArray(d)) message = d.map((x: { msg?: string }) => x.msg).filter(Boolean).join("; ") || message;
  } catch {
    /* not JSON */
  }
  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event("pramaan:logout"));
  }
  throw new ApiError(res.status, message, problems);
}

export async function api<T>(path: string, opts: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const init: RequestInit = { method: opts.method || (opts.body || opts.form ? "POST" : "GET") };
  if (opts.form) {
    init.body = opts.form;
    init.headers = headers();
  } else if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
    init.headers = headers({ "Content-Type": "application/json" });
  } else {
    init.headers = headers();
  }
  const res = await fetch(path, init);
  if (!res.ok) await fail(res);
  return (await res.json()) as T;
}

export async function apiBlob(path: string): Promise<Blob> {
  const res = await fetch(path, { headers: headers() });
  if (!res.ok) await fail(res);
  return res.blob();
}

export async function downloadFile(path: string, filename: string) {
  const blob = await apiBlob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

// ---------------------------------------------------------------- types --
export type Role = "institution" | "scrutinizer" | "senior_officer" | "rule_admin" | "auditor";

export interface Institution {
  id: string; aicte_id: string; name: string; kind: string; state: string; state_code: string; city: string;
  address: string; region: string; university: string; established: number;
}

export interface User {
  id: number; username: string; full_name: string; role: Role; institution_id: string | null; region: string | null;
  institution?: Institution;
}

export interface Counts { critical: number; high: number; warning: number; info: number; open: number; total: number }

export interface AppSummary {
  id: string; institution_id: string; institution: string; state: string; city: string; app_type: string;
  app_type_label: string; cycle: string; status: string; created_at: string; submitted_at: string | null;
  risk_score: number; overall_status: string; rulebook_version: string | null; precheck_seconds: number | null;
  assigned_to: number | null; counts: Counts; decision: Decision | null;
}

export interface Decision { decision: string; label: string; note: string; by: string; at: string }

export interface Field { name: string; value: string; normalized: string | null; page: number; bbox: number[] | null; confidence: number }

export interface Doc {
  id: string; application_id: string; slot: string; slot_label: string; detected_type: string | null; detected_label: string | null;
  detected_confidence: number | null; filename: string; mime: string; size: number; sha256: string; page_count: number;
  pages: { w: number; h: number; unit: string }[]; status: string; error: string | null; text_source: string | null;
  ocr_confidence: number | null; uploaded_at: string; processed_at: string | null; fields: Field[]; qr_found: boolean;
  signature: { present?: boolean; valid?: boolean; trusted?: boolean; intact?: boolean; modified_after_signing?: boolean;
    summary?: string; signer?: string } | null;
  forensics?: { code: string; severity: string; title: string; message: string; page: number; bbox: number[] | null }[];
  metadata?: Record<string, string | number>;
  photo?: { phash?: string; taken_at?: string; gps_lat?: number; gps_lon?: number; software?: string; ela?: number } | null;
  classify_hits?: string[];
}

export interface Evidence {
  label: string; kind: string; document_id?: string; doc_type?: string; filename?: string; page?: number;
  bbox?: number[] | null; field?: string | null; value?: string | null; confidence?: number | null; note?: string | null;
}

export interface Finding {
  id: number; ref: string; application_id: string; category: string; severity: string; title: string; message: string;
  doc_type: string | null; doc_label: string | null; rule_id: string | null; rule_version: string | null; source_ref: string | null;
  evidence: Evidence[]; preliminary: boolean; status: string; decision_note: string | null; decision_by: string | null;
  decided_at: string | null; created_at: string;
}

export interface Verification {
  id: number; application_id: string; document_id: string | null; doc_type: string; doc_label: string; source: string;
  method: string; reference: string | null; status: string; compared: { field: string; registry: unknown; submitted: unknown; match: boolean | null }[];
  note: string; attempts: number; latency_ms: number | null; checked_at: string; institution?: string;
}

export interface Letter {
  id: string; application_id: string; status: string; items: { finding_id: number | null; title: string; text: string }[];
  note: string; drafted_by: string | null; approved_by: string | null; created_at: string; issued_at: string | null;
  response: { message: string; at: string; by: string } | null;
}

export interface ChecklistItem {
  doc_type: string; label: string; required: boolean; min_count: number; uploaded: number; document_ids: string[];
  state: string; note: string | null;
}

export interface Programme { name: string; level: string; intake_requested: number | string }

export interface Detail {
  application: AppSummary;
  institution: Institution;
  form: { programmes: Programme[]; [k: string]: unknown };
  checklist: ChecklistItem[];
  documents: Doc[];
  findings: Finding[];
  verifications: Verification[];
  letters: Letter[];
  processing: boolean;
  run: { id: number; trigger: string; started_at: string; finished_at: string | null; stats: Record<string, number>; rulebook: string } | null;
  permissions: { edit: boolean; submit: boolean; respond: boolean; review: boolean; draft_letter: boolean; decide: boolean };
  unreviewed_blocking: number;
  decisions: Record<string, string>;
  record?: { last_approved_cycle: string; approval_status: string; programmes: { programme: string; level: string; approved_intake: number }[];
    faculty_on_record: number; open_deficiencies: number; accreditation_no: string | null } | null;
  assigned_to_name?: string | null;
  timeline?: AuditEvent[];
  generated_at?: string;
  verification_summary?: Record<string, number>;
}

export interface AlertItem { id: number; created_at: string; severity: string; kind: string; message: string; application_id: string | null; resolved: boolean; read: boolean }

export interface AuditEvent {
  id: number; ts: string; actor: string; actor_type: string; action: string; object_type: string; object_id: string;
  application_id: string | null; details: Record<string, unknown>; prev_hash: string; hash: string;
}

export interface Condition { fact: string; op: string; value?: unknown; ref?: string; days?: number }
export interface RuleRow { when: Condition[]; severity: string; category: string; title: string; message?: string; doc_type?: string; evidence?: string[] }
export interface Rule {
  rule_id: string; title: string; group?: string; source?: string; scope?: string; enabled?: boolean;
  applies_to?: { app_types?: string[]; states?: string[] }; rows: RuleRow[];
}
export interface RulebookContent {
  cycle: string; settings: Record<string, number>; checklists: Record<string, { doc_type: string; required: boolean; min_count?: number }[]>;
  rules: Rule[];
}
export interface RulebookVersion {
  id: number; cycle: string; version: number; label: string; status: string; change_note: string; created_by: string | null;
  created_by_id: number | null; created_at: string; submitted_at: string | null; reviewed_by: string | null; reviewed_at: string | null;
  review_note: string | null; effective_from: string | null; rule_count: number; content?: RulebookContent;
  dry_run: null | { status?: string; ran_at?: string; applications?: number; flagged_applications?: number;
    findings?: { draft: number; published: number }; by_rule?: Record<string, { draft: number; published: number }>;
    changed?: { application_id: string; institution: string; added: string[]; removed: string[] }[] };
}

export interface Meta {
  doc_types: Record<string, string>; app_types: Record<string, string>; operators: Record<string, string>;
  severities: string[]; categories: string[]; verification_statuses: string[];
}
