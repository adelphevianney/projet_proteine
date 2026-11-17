import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, date, fcfa, kg } from "../api";
import { useAuth } from "../auth";
import { MapPicker } from "../components/Maps";
import { Badge, Btn, Card, Empty, ErrorBox, Field, Loading, Page, Prompt, Stat, useAction } from "../components/ui";

export function PaymentsPage() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["payments"], queryFn: () => api("/payments") });
  const confirm = useAction(({ id, reference }) => api(`/payments/${id}/confirm`, { method: "POST", body: { reference } }),
                            { invalidate: ["payments"] });
  const KIND = { waste: "Déchets", collection: "Collecte", flour: "Farine", commission: "Commission 5 %" };
  return (
    <Page title="Paiements" subtitle="Réglés hors plateforme (mobile money, espèces). Celui qui paie saisit la référence.">
      <Loading q={q}>{(d) => (
        <>
          <div className="stats">
            <Stat label="À recevoir" value={fcfa(d.to_receive)} />
            <Stat label="À payer" value={fcfa(d.to_pay)} />
            <Stat label="Déjà reçu" value={fcfa(d.received)} />
          </div>
          {d.items.length === 0 && <Empty>Aucun paiement pour l'instant.</Empty>}
          {d.items.map((p) => {
            const iPay = p.payer_id === user.id;
            return (
              <Card key={p.id}>
                <div className="row space">
                  <b>{KIND[p.kind]} · {fcfa(p.amount_fcfa)}</b><Badge status={p.status} />
                </div>
                <div className="muted small">
                  {iPay ? `Vous payez ${p.payee_name}` : `${p.payer_name} vous paie`} · {p.ref_code} · {date(p.created_at)}
                </div>
                {p.reference && <div className="small">Référence : {p.reference}</div>}
                {iPay && p.status === "due" && (
                  <Prompt label="J'ai payé" placeholder="Référence mobile money" action={confirm}
                          onSubmit={(reference) => confirm.mutate({ id: p.id, reference })} />
                )}
              </Card>
            );
          })}
          <ErrorBox error={confirm.error} />
        </>
      )}</Loading>
    </Page>
  );
}

export function ImpactPage() {
  const q = useQuery({ queryKey: ["impact"], queryFn: () => api("/impact") });
  return (
    <Page title="Impact" subtitle="Calculé à partir des seuls changements depuis la dernière lecture.">
      <Loading q={q}>{(d) => (
        <>
          <div className="stats">
            <Stat label="Déchets valorisés" value={`${d.waste_tonnes} t`} />
            <Stat label="Soja importé évité" value={kg(d.soy_avoided_kg)} />
            <Stat label="CO₂ évité" value={kg(d.co2_avoided_kg)} />
            <Stat label="Revenus versés" value={fcfa(d.revenue_paid_fcfa)} sub="producteurs et collecteurs" />
            <Stat label="Part des femmes" value={d.women_share_pct == null ? "—" : `${d.women_share_pct} %`} sub="des revenus versés" />
            <Stat label="Farine livrée" value={kg(d.flour_delivered_kg)} />
          </div>
          {d.mine && (
            <Card>
              <h3>Mon activité</h3>
              <p>Déchets traités : <b>{kg(d.mine.waste_kg)}</b></p>
              <p>Reçu : <b>{fcfa(d.mine.received)}</b> · en attente : <b>{fcfa(d.mine.pending)}</b></p>
            </Card>
          )}
          <p className="muted small">{d.note}</p>
        </>
      )}</Loading>
    </Page>
  );
}

export function DisputesPage() {
  const q = useQuery({ queryKey: ["disputes"], queryFn: () => api("/disputes/mine") });
  const [form, setForm] = useState({ subject: "", body: "", ref_code: "" });
  const create = useAction((b) => api("/disputes", { method: "POST", body: b }),
                           { invalidate: ["disputes"], onSuccess: () => setForm({ subject: "", body: "", ref_code: "" }) });
  return (
    <Page title="Litiges" subtitle="Signalez un problème, l'équipe vous répond.">
      <Card>
        <form onSubmit={(e) => { e.preventDefault(); create.mutate({ ...form, ref_code: form.ref_code || null }); }}>
          <Field label="Sujet"><input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} required /></Field>
          <Field label="Code du lot (facultatif)"><input value={form.ref_code} placeholder="DL-2026-000001"
                 onChange={(e) => setForm({ ...form, ref_code: e.target.value })} /></Field>
          <Field label="Description"><textarea rows={3} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} required /></Field>
          <Btn action={create} type="submit">Envoyer</Btn>
          <ErrorBox error={create.error} />
        </form>
      </Card>
      <Loading q={q} empty="Aucun litige.">{(items) => items.map((d) => (
        <Card key={d.id}>
          <div className="row space"><b>{d.subject}</b><Badge status={d.status} /></div>
          <p className="small">{d.body}</p>
          {d.resolution && <p className="notice small">Réponse : {d.resolution}</p>}
        </Card>
      ))}</Loading>
    </Page>
  );
}

export function NotificationsPage() {
  const q = useQuery({ queryKey: ["notifications"], queryFn: () => api("/notifications") });
  const read = useAction(() => api("/notifications/read", { method: "POST" }), { invalidate: ["notifications"] });
  return (
    <Page title="Notifications" action={<Btn kind="ghost" action={read} onClick={() => read.mutate()}>Tout lu</Btn>}>
      <Loading q={q} empty="Aucune notification.">{(items) => items.map((n) => (
        <Card key={n.id} className={n.read_at ? "" : "unread"}>
          <div className={n.kind === "retrait" ? "alert-text" : ""}>{n.message}</div>
          <div className="muted small">{date(n.created_at)} {n.ref_code && `· ${n.ref_code}`}</div>
        </Card>
      ))}</Loading>
    </Page>
  );
}

export function TracePage() {
  const [code, setCode] = useState("");
  const [submitted, setSubmitted] = useState(null);
  const q = useQuery({ queryKey: ["trace", submitted], queryFn: () => api(`/trace/${submitted}`), enabled: !!submitted });
  return (
    <Page title="Traçabilité" subtitle="Saisissez un code de farine (FB-…) ou de déchets (DL-…).">
      <form className="inline-form" onSubmit={(e) => { e.preventDefault(); setSubmitted(code.trim().toUpperCase()); }}>
        <input value={code} placeholder="FB-2026-000001" onChange={(e) => setCode(e.target.value)} />
        <button className="btn primary">Tracer</button>
      </form>
      {submitted && <Loading q={q}>{(d) => d.kind === "flour" ? (
        <>
          <Card>
            <div className="row space"><b>Farine {d.flour.code}</b><Badge status={d.flour.status} /></div>
            <p className="small">{kg(d.flour.quantity_kg)} produits le {date(d.flour.created_at)} à {d.flour.farm_commune}</p>
          </Card>
          <h3>Déchets d'origine</h3>
          {d.sources.map((s) => (
            <Card key={s.code}>
              <div className="row space"><b>{s.code}</b><Badge status={s.quality} /></div>
              <p className="small">{s.waste_type} · {kg(s.weight_kg)} · {s.origin_commune}</p>
              <p className="muted small">Collecté {date(s.collected_at)} · réceptionné {date(s.received_at)}</p>
              {s.risk && <p className="small">Point de vigilance : {s.risk}</p>}
            </Card>
          ))}
        </>
      ) : (
        <>
          <Card>
            <div className="row space"><b>Lot {d.lot.code}</b><Badge status={d.lot.status} /></div>
            <p className="small">{d.lot.waste_type} · {kg(d.lot.weight_kg)} · {d.lot.origin_commune}</p>
          </Card>
          <h3>Historique</h3>
          {d.events.map((e, i) => <p key={i} className="small">{date(e.at)} : <Badge status={e.to_status} /></p>)}
          <h3>Farine produite</h3>
          {d.flour_batches.length === 0 ? <Empty>Pas encore transformé.</Empty> :
            d.flour_batches.map((b) => <p key={b.code}>{b.code} <Badge status={b.status} /></p>)}
        </>
      )}</Loading>}
    </Page>
  );
}

export function PricesPage() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["prices"], queryFn: () => api("/prices") });
  const [form, setForm] = useState({ item: "tourteau_soja", price: "" });
  const report = useAction((b) => api("/prices", { method: "POST", body: b }),
                           { invalidate: ["prices"], onSuccess: () => setForm({ ...form, price: "" }) });
  return (
    <Page title="Prix du marché" subtitle="Un prix devient la médiane des déclarations dès que 3 personnes l'ont relevé.">
      <Loading q={q}>{(items) => (
        <>
          <table className="table">
            <thead><tr><th>Produit</th><th>Prix médian</th><th>Relevés</th></tr></thead>
            <tbody>{items.map((p) => (
              <tr key={p.item}><td>{p.label}</td>
                <td>{p.median ? fcfa(p.median) : <span className="muted">encore {p.needed}</span>}</td>
                <td>{p.reporters}</td></tr>
            ))}</tbody>
          </table>
          {user.status === "active" && (
            <Card>
              <h3>Je déclare un prix relevé</h3>
              <form className="inline-form" onSubmit={(e) => { e.preventDefault(); report.mutate({ item: form.item, price_fcfa_kg: Number(form.price) }); }}>
                <select value={form.item} onChange={(e) => setForm({ ...form, item: e.target.value })}>
                  {items.map((p) => <option key={p.item} value={p.item}>{p.label}</option>)}
                </select>
                <input inputMode="numeric" placeholder="FCFA" value={form.price}
                       onChange={(e) => setForm({ ...form, price: e.target.value.replace(/\D/g, "") })} required />
                <Btn action={report} type="submit">Déclarer</Btn>
              </form>
              <ErrorBox error={report.error} />
            </Card>
          )}
        </>
      )}</Loading>
    </Page>
  );
}

export function ProfilePage() {
  const { user, logout } = useAuth();
  const hist = useQuery({ queryKey: ["history"], queryFn: () => api("/me/history") });
  const [pos, setPos] = useState(user.lat ? { lat: user.lat, lng: user.lng } : null);
  const [commune, setCommune] = useState(user.commune || "");
  const save = useAction((b) => api("/me", { method: "PATCH", body: b }), { invalidate: ["me", "history"] });
  const ROLE = { producer: "Producteur de déchets", farm: "Ferme à larves", breeder: "Éleveur", collector: "Collecteur", admin: "Administration" };
  return (
    <Page title={user.name} subtitle={`${ROLE[user.role]} · ${user.phone}`}>
      {user.status === "pending" && <p className="notice">Votre compte attend la validation de l'équipe.</p>}
      <Card>
        <h3>Mon lieu</h3>
        <Field label="Commune"><input value={commune} onChange={(e) => setCommune(e.target.value)} /></Field>
        <MapPicker value={pos} onChange={setPos} />
        <Btn action={save} onClick={() => save.mutate({ commune, lat: pos?.lat, lng: pos?.lng })}>Enregistrer</Btn>
        <ErrorBox error={save.error} />
      </Card>
      <Card>
        <h3>Historique de mon profil</h3>
        <p className="muted small">Chaque changement crée une nouvelle version ; les anciennes sont conservées.</p>
        <Loading q={hist}>{(items) => items.map((v) => (
          <div key={v.version_id} className="hist">
            <b>{v.commune || "—"}</b> {v.is_current && <span className="badge good">actuelle</span>}
            <div className="muted small">du {date(v.valid_from)} {v.valid_to ? `au ${date(v.valid_to)}` : "à aujourd'hui"}</div>
          </div>
        ))}</Loading>
      </Card>
      <button className="btn ghost block" onClick={logout}>Se déconnecter</button>
    </Page>
  );
}
