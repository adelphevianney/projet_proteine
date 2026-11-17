import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, date, fcfa, kg } from "../api";
import { Badge, Btn, Card, Empty, ErrorBox, Field, Loading, Page, Prompt, useAction } from "../components/ui";

export function HerdsPage() {
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: () => api("/animal-profiles") });
  const q = useQuery({ queryKey: ["herds"], queryFn: () => api("/herds") });
  const [f, setF] = useState({ profile_id: "poulet_croissance", name: "", headcount: "" });
  const add = useAction((b) => api("/herds", { method: "POST", body: b }),
                        { invalidate: ["herds"], onSuccess: () => setF({ ...f, name: "", headcount: "" }) });
  return (
    <Page title="Mes élevages">
      <Card className="highlight">
        <form onSubmit={(e) => { e.preventDefault(); add.mutate({ ...f, headcount: Number(f.headcount) }); }}>
          <Field label="Espèce et stade">
            <select value={f.profile_id} onChange={(e) => setF({ ...f, profile_id: e.target.value })}>
              {(profiles.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <div className="grid2">
            <Field label="Nom"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
            <Field label="Effectif"><input inputMode="numeric" value={f.headcount} required
                   onChange={(e) => setF({ ...f, headcount: e.target.value.replace(/\D/g, "") })} /></Field>
          </div>
          <Btn action={add} type="submit">Ajouter</Btn>
          <ErrorBox error={add.error} />
        </form>
      </Card>
      <Loading q={q} empty="Aucun élevage enregistré.">{(items) => items.map((h) => (
        <Card key={h.id}><b>{h.name}</b><div className="small">{h.profile_name} · {h.headcount.toLocaleString("fr-FR")} têtes</div></Card>
      ))}</Loading>
    </Page>
  );
}

export function FormulatorPage() {
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: () => api("/animal-profiles") });
  const herds = useQuery({ queryKey: ["herds"], queryFn: () => api("/herds") });
  const [f, setF] = useState({ profile_id: "poulet_croissance", soy_price: 450, headcount: 500, days: 30 });
  const compute = useAction((b) => api("/rations/compute", { method: "POST", body: b }));
  const r = compute.data;
  const run = (next = f) => compute.mutate({ ...next, headcount: Number(next.headcount) || null, days: Number(next.days) || null });
  return (
    <Page title="Formulateur de ration" subtitle="La ration la moins chère qui couvre les besoins de l'animal.">
      <Card className="highlight">
        {herds.data?.length > 0 && (
          <Field label="Partir d'un élevage">
            <select onChange={(e) => { const h = herds.data.find((x) => x.id === e.target.value); if (h) setF({ ...f, profile_id: h.profile_id, headcount: h.headcount }); }}>
              <option value="">—</option>
              {herds.data.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
            </select>
          </Field>
        )}
        <Field label="Espèce et stade">
          <select value={f.profile_id} onChange={(e) => setF({ ...f, profile_id: e.target.value })}>
            {(profiles.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label={`Prix du tourteau de soja : ${f.soy_price} FCFA/kg`}>
          <input type="range" min="250" max="800" step="10" value={f.soy_price}
                 onChange={(e) => { const next = { ...f, soy_price: Number(e.target.value) }; setF(next); if (r) run(next); }} />
        </Field>
        <div className="grid2">
          <Field label="Effectif"><input inputMode="numeric" value={f.headcount} onChange={(e) => setF({ ...f, headcount: e.target.value.replace(/\D/g, "") })} /></Field>
          <Field label="Durée (jours)"><input inputMode="numeric" value={f.days} onChange={(e) => setF({ ...f, days: e.target.value.replace(/\D/g, "") })} /></Field>
        </div>
        <Btn action={compute} onClick={() => run()}>Calculer</Btn>
        <ErrorBox error={compute.error} />
      </Card>
      {r && (
        <>
          <div className="stats">
            <div className="stat"><div className="stat-value">{fcfa(r.circular.cost_fcfa_kg)}</div><div className="stat-label">par kg, ration circulaire</div></div>
            {r.classic && <div className="stat"><div className="stat-value">{fcfa(r.classic.cost_fcfa_kg)}</div><div className="stat-label">par kg, ration classique</div></div>}
            {r.saving_pct != null && <div className="stat good"><div className="stat-value">−{r.saving_pct} %</div><div className="stat-label">économie</div></div>}
          </div>
          {r.alerts.map((a) => <p key={a} className="notice small">{a}</p>)}
          <Card>
            <h3>Composition</h3>
            <table className="table">
              <thead><tr><th>Ingrédient</th><th>%</th>{r.quantities && <th>À prévoir</th>}</tr></thead>
              <tbody>{r.circular.lines.map((l) => (
                <tr key={l.ingredient_id} className={l.kind === "larves" ? "hl" : ""}>
                  <td>{l.name}{l.at_cap && <small className="muted"> (plafond)</small>}</td>
                  <td>{l.share_pct.toFixed(1)}</td>
                  {r.quantities && <td>{kg(r.quantities.lines.find((x) => x.name === l.name)?.kg)}</td>}
                </tr>
              ))}</tbody>
            </table>
          </Card>
          {r.quantities && (
            <Card>
              <h3>Pour {r.quantities.headcount.toLocaleString("fr-FR")} animaux sur {r.quantities.days} jours</h3>
              <p>Aliment total : <b>{kg(r.quantities.total_feed_kg)}</b> · coût <b>{fcfa(r.quantities.total_cost_fcfa)}</b></p>
              {r.quantities.flour_to_buy_kg > 0 && <p>Farine de larves à commander : <b>{kg(r.quantities.flour_to_buy_kg)}</b></p>}
              {r.quantities.total_saving_fcfa != null && <p className="good-text">Économie par rapport à la ration classique : <b>{fcfa(r.quantities.total_saving_fcfa)}</b></p>}
            </Card>
          )}
          <Card>
            <h3>Apports</h3>
            <table className="table"><tbody>{Object.entries(r.nutrient_labels).map(([k, label]) => (
              <tr key={k}><td>{label}</td><td>{r.circular.nutrients[k]}</td>
                <td className="muted small">{r.requirements[k] ? `${r.requirements[k].min != null ? "≥ " + r.requirements[k].min : ""} ${r.requirements[k].max != null ? "≤ " + r.requirements[k].max : ""}` : ""}</td></tr>
            ))}</tbody></table>
            <p className="muted small">Valeurs indicatives, à faire valider par un nutritionniste.</p>
          </Card>
        </>
      )}
    </Page>
  );
}

export function MarketPage() {
  const q = useQuery({ queryKey: ["market"], queryFn: () => api("/flour-batches/available") });
  const order = useAction(({ id, q }) => api("/orders", { method: "POST", body: { flour_batch_id: id, quantity_kg: q }, idempotent: true }),
                          { invalidate: ["market", "orders"] });
  return (
    <Page title="Farine disponible" subtitle="Triée par prix puis par distance.">
      <Loading q={q} empty="Aucune farine disponible pour l'instant.">{(items) => items.map((b) => (
        <Card key={b.id}>
          <div className="row space"><b>{fcfa(b.price_per_kg)}/kg</b>{b.distance_km != null && <span className="pill">{b.distance_km} km</span>}</div>
          <div className="small">{b.farm_name} · {b.commune} · stock {kg(b.stock_kg)}</div>
          <div className="muted small">Code {b.code}</div>
          <Prompt label="Commander" kind="primary" inputMode="decimal" placeholder="Quantité (kg)" action={order}
                  onSubmit={(v) => order.mutate({ id: b.id, q: Number(String(v).replace(",", ".")) })} />
        </Card>
      ))}</Loading>
      <ErrorBox error={order.error} />
      {order.data && <p className="notice">Commande enregistrée : {kg(order.data.quantity_kg)} pour {fcfa(order.data.total_fcfa)}.</p>}
    </Page>
  );
}

export function MyOrdersPage() {
  const q = useQuery({ queryKey: ["orders"], queryFn: () => api("/orders/mine") });
  const cancel = useAction((id) => api(`/orders/${id}/cancel`, { method: "POST" }), { invalidate: ["orders", "market"] });
  return (
    <Page title="Mes commandes">
      <Loading q={q} empty="Aucune commande.">{(items) => items.map((o) => (
        <Card key={o.id} className={o.status === "recalled" ? "alert" : ""}>
          <div className="row space"><b>{kg(o.quantity_kg)} · {fcfa(o.total_fcfa)}</b><Badge status={o.status} /></div>
          <div className="muted small">{o.farm_name} · {o.flour_code} · {date(o.created_at)}</div>
          {o.status === "ordered" && <Btn kind="ghost" action={cancel} onClick={() => cancel.mutate(o.id)}>Annuler</Btn>}
        </Card>
      ))}</Loading>
      <ErrorBox error={cancel.error} />
    </Page>
  );
}
