import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export const STATUS = {
  published: ["Publiée", "info"], reserved: ["Réservé", "warn"], cancelled: ["Annulé", "muted"],
  collected: ["Collecté", "info"], received: ["Réceptionné", "good"], rejected: ["Rejeté", "bad"],
  used: ["Transformé", "good"], recalled: ["Retiré", "bad"], available: ["Disponible", "good"],
  sold_out: ["Épuisé", "muted"], ordered: ["Commandée", "warn"], delivered: ["Livrée", "good"],
  due: ["À régler", "warn"], settled: ["Réglé", "good"], open: ["Ouvert", "warn"], resolved: ["Résolu", "good"],
  active: ["Actif", "good"], pending: ["En attente", "warn"], disabled: ["Désactivé", "bad"],
  conforme: ["Conforme", "good"], degrade: ["Dégradé", "warn"], rejete: ["Rejeté", "bad"],
};

export function Badge({ status }) {
  const [label, tone] = STATUS[status] || [status, "muted"];
  return <span className={`badge ${tone}`}>{label}</span>;
}

export const Card = ({ children, className = "" }) => <div className={`card ${className}`}>{children}</div>;

export function Page({ title, subtitle, children, action }) {
  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>{title}</h1>
          {subtitle && <p className="muted">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </main>
  );
}

export const Empty = ({ children }) => <p className="empty">{children}</p>;
export const ErrorBox = ({ error }) => error ? <p className="error">{error.message}</p> : null;

export function Loading({ q, children, empty }) {
  if (q.isLoading) return <p className="muted">Chargement…</p>;
  if (q.error) return <ErrorBox error={q.error} />;
  if (empty && (!q.data || q.data.length === 0)) return <Empty>{empty}</Empty>;
  return children(q.data);
}

// Action qui modifie des données : affiche l'erreur de l'API et rafraîchit les listes.
export function useAction(fn, { invalidate = [], onSuccess } = {}) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (data, vars) => {
      invalidate.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      qc.invalidateQueries({ queryKey: ["notifications"] });
      onSuccess?.(data, vars);
    },
  });
}

export function Btn({ action, children, onClick, kind = "primary", disabled, ...rest }) {
  return (
    <button className={`btn ${kind}`} disabled={disabled || action?.isPending} onClick={onClick} {...rest}>
      {action?.isPending ? "…" : children}
    </button>
  );
}

export function Field({ label, hint, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small className="muted">{hint}</small>}
    </label>
  );
}

export function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="muted small">{sub}</div>}
    </div>
  );
}

export function Prompt({ label, placeholder, onSubmit, action, kind = "secondary", inputMode = "text" }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  if (!open) return <Btn kind={kind} onClick={() => setOpen(true)}>{label}</Btn>;
  return (
    <form className="inline-form" onSubmit={(e) => { e.preventDefault(); onSubmit(value); }}>
      <input autoFocus value={value} inputMode={inputMode} placeholder={placeholder}
             onChange={(e) => setValue(e.target.value)} />
      <Btn action={action} type="submit">OK</Btn>
      <Btn kind="ghost" type="button" onClick={() => setOpen(false)}>Annuler</Btn>
    </form>
  );
}
