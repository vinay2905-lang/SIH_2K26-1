import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { ROLE_LABEL, useAuth } from "../auth";
import { Mark } from "../components/Layout";
import { useT } from "../i18n";

interface DemoUser { username: string; full_name: string; role: string; institution?: string }

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const t = useT();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState<DemoUser[]>([]);

  useEffect(() => {
    api<DemoUser[]>("/api/auth/demo-users").then(setDemo).catch(() => setDemo([]));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await login(username, password);
      navigate(u.role === "institution" ? "/my" : "/dashboard");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const officials = demo.filter((d) => d.role !== "institution");
  const institutions = demo.filter((d) => d.role === "institution");
  return (
    <div className="login">
      <section className="side">
        <div className="row" style={{ gap: 12 }}>
          <span className="mark" style={{ width: 40, height: 40 }}><Mark /></span>
          <div className="wordmark" style={{ fontSize: 20 }}>PRAMAAN<small>AICTE approval pre-scrutiny</small></div>
        </div>
        <h1>Every application checked before a scrutinizer opens it, and every flag backed by evidence.</h1>
        <p>A decision-support prototype for AICTE approval processing. It reads the documents, checks them against
          AICTE records, the issuing authorities and a versioned rulebook, and hands officials an evidence-linked report.</p>
        <ul>
          <li>Missing, expired and inconsistent documents found at upload</li>
          <li>Issuer verification with six explicit statuses, every response logged</li>
          <li>Tampering indicators, always marked preliminary for human review</li>
          <li>No-code rulebook with maker-checker approval</li>
          <li>Hash-chained audit trail; final decisions stay with AICTE officials</li>
        </ul>
        <p className="small" style={{ marginTop: "auto" }}>Sandbox: every institution, person, certificate and issuer record here is synthetic.</p>
      </section>
      <section className="form">
        <h1>{t("Sign in")}</h1>
        <form className="col" onSubmit={submit} style={{ gap: 12 }}>
          <div className="field">
            <label htmlFor="u">{t("Username")}</label>
            <input id="u" className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
          </div>
          <div className="field">
            <label htmlFor="p">{t("Password")}</label>
            <input id="p" className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </div>
          {error && <div className="error" role="alert">{error}</div>}
          <button className="btn primary" disabled={busy} style={{ height: 38, justifyContent: "center" }}>{busy ? "Signing in…" : t("Sign in")}</button>
        </form>
        {demo.length > 0 && (
          <div className="col">
            <div className="lbl">Demo accounts · password Pramaan@2026</div>
            <div className="demo-users">
              {officials.map((d) => (
                <button key={d.username} type="button" className="demo-user" onClick={() => { setUsername(d.username); setPassword("Pramaan@2026"); }}>
                  <b>{ROLE_LABEL[d.role]}</b><span>{d.full_name} · {d.username}</span>
                </button>
              ))}
            </div>
            <div className="lbl" style={{ marginTop: 6 }}>Institutions</div>
            <select className="input" value="" onChange={(e) => { setUsername(e.target.value); setPassword("Pramaan@2026"); }} aria-label="Choose a demo institution">
              <option value="">Choose a demo institution…</option>
              {institutions.map((d) => <option key={d.username} value={d.username}>{d.institution} ({d.username})</option>)}
            </select>
          </div>
        )}
      </section>
    </div>
  );
}
