import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { MapPicker } from "../components/Maps";
import { ErrorBox, Field } from "../components/ui";

const ROLES = [
  ["producer", "J'ai des déchets agricoles", "Transformatrice, coopérative, planteur, marché"],
  ["farm", "J'élève des larves", "Ferme à larves (validation par l'équipe)"],
  ["breeder", "J'élève des animaux", "Volaille, porc, poisson, bovin, ovin"],
  ["collector", "Je transporte des déchets", "Tricycle ou moto (validation par l'équipe)"],
];

export default function Login() {
  const { login } = useAuth();
  const [step, setStep] = useState("phone");
  const [phone, setPhone] = useState("+22507");
  const [code, setCode] = useState("");
  const [devCode, setDevCode] = useState(null);
  const [signupToken, setSignupToken] = useState(null);
  const [form, setForm] = useState({ name: "", role: "producer", commune: "", is_woman: false, pos: null });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = (fn) => async (e) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await fn(); } catch (err) { setError(err); } finally { setBusy(false); }
  };

  const sendCode = run(async () => {
    const r = await api("/auth/otp/request", { method: "POST", body: { phone } });
    setDevCode(r.dev_code || null);
    setStep("code");
  });
  const verify = run(async () => {
    const r = await api("/auth/otp/verify", { method: "POST", body: { phone, code } });
    if (r.needs_signup) { setSignupToken(r.signup_token); setStep("signup"); } else login(r.token);
  });
  const signup = run(async () => {
    const r = await api("/auth/signup", {
      method: "POST",
      body: { signup_token: signupToken, name: form.name, role: form.role, commune: form.commune || null,
              is_woman: form.is_woman, lat: form.pos?.lat ?? null, lng: form.pos?.lng ?? null },
    });
    login(r.token);
  });

  return (
    <main className="login">
      <div className="brand">
        <img src="/icon.svg" alt="" width="56" height="56" />
        <h1>Protéine circulaire</h1>
        <p>Les déchets agricoles deviennent l'aliment de nos élevages.</p>
      </div>
      <div className="card">
        {step === "phone" && (
          <form onSubmit={sendCode}>
            <Field label="Numéro de téléphone" hint="Vous recevrez un code par SMS. Pas de mot de passe.">
              <input value={phone} onChange={(e) => setPhone(e.target.value.replace(/[^\d+]/g, ""))}
                     inputMode="tel" autoComplete="tel" />
            </Field>
            <button className="btn primary block" disabled={busy}>Recevoir mon code</button>
          </form>
        )}
        {step === "code" && (
          <form onSubmit={verify}>
            {devCode && <p className="notice">Prototype : le SMS est simulé. Votre code est <b>{devCode}</b></p>}
            <Field label={`Code reçu au ${phone}`}>
              <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                     inputMode="numeric" autoComplete="one-time-code" autoFocus />
            </Field>
            <button className="btn primary block" disabled={busy || code.length !== 6}>Valider</button>
            <button type="button" className="btn ghost block" onClick={() => setStep("phone")}>Changer de numéro</button>
          </form>
        )}
        {step === "signup" && (
          <form onSubmit={signup}>
            <h2>Créer mon compte</h2>
            <Field label="Nom ou nom de la structure">
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            </Field>
            <div className="choices">
              {ROLES.map(([id, title, sub]) => (
                <label key={id} className={`choice ${form.role === id ? "on" : ""}`}>
                  <input type="radio" name="role" checked={form.role === id} onChange={() => setForm({ ...form, role: id })} />
                  <b>{title}</b><small>{sub}</small>
                </label>
              ))}
            </div>
            <Field label="Commune">
              <input value={form.commune} onChange={(e) => setForm({ ...form, commune: e.target.value })} />
            </Field>
            <label className="check">
              <input type="checkbox" checked={form.is_woman} onChange={(e) => setForm({ ...form, is_woman: e.target.checked })} />
              Je suis une femme (pour l'indicateur « part des femmes »)
            </label>
            <Field label="Où êtes-vous ?"><MapPicker value={form.pos} onChange={(pos) => setForm({ ...form, pos })} /></Field>
            <button className="btn primary block" disabled={busy}>Créer mon compte</button>
          </form>
        )}
        <ErrorBox error={error} />
      </div>
      <p className="muted small center">Démo : +2250700000001 (productrice), …11 (ferme), …21 (collecteur), …31 (éleveur), …00 (administration)</p>
    </main>
  );
}
