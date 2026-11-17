import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, date, fcfa, kg } from "../api";
import { useAuth } from "../auth";
import { MapPicker } from "../components/Maps";
import { Badge, Btn, Card, ErrorBox, Field, Loading, Page, useAction } from "../components/ui";

const TYPES = { manioc: "Épluchures de manioc", cajou: "Pommes de cajou", cacao: "Cabosses de cacao", marche: "Déchets de marché" };

export function OffersPage() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["offers"], queryFn: () => api("/offers/mine") });
  const [open, setOpen] = useState(false);
  const cancel = useAction((id) => api(`/offers/${id}/cancel`, { method: "POST" }), { invalidate: ["offers"] });
  return (
    <Page title="Mes offres" subtitle="Publiez vos déchets : une ferme à larves les réserve, un collecteur passe."
          action={!open && <Btn onClick={() => setOpen(true)}>+ Publier</Btn>}>
      {open && <NewOffer user={user} onDone={() => setOpen(false)} />}
      <Loading q={q} empty="Aucune offre. Publiez votre premier lot de déchets.">{(items) => items.map((o) => (
        <Card key={o.id}>
          <div className="row space"><b>{o.waste_type} · {kg(o.quantity_kg)}</b>
            <Badge status={o.lot_status || o.status} /></div>
          <div className="muted small">{o.frequency} · {fcfa(o.price_per_kg)}/kg · {o.commune || ""} · {date(o.created_at)}</div>
          {o.description && <p className="small">{o.description}</p>}
          {o.lot_code && <p className="small">Lot <b>{o.lot_code}</b></p>}
          {o.status === "published" && <Btn kind="ghost" action={cancel} onClick={() => cancel.mutate(o.id)}>Annuler l'offre</Btn>}
        </Card>
      ))}</Loading>
      <ErrorBox error={cancel.error} />
    </Page>
  );
}

function NewOffer({ user, onDone }) {
  const [text, setText] = useState("");
  const [f, setF] = useState({ waste_type_id: "manioc", quantity_kg: "", frequency: "ponctuelle", description: "",
                               pos: user.lat ? { lat: user.lat, lng: user.lng } : null });
  const parse = useAction((t) => api("/offers/parse", { method: "POST", body: { text: t } }), {
    onSuccess: (r) => setF((x) => ({ ...x, waste_type_id: r.waste_type_id || x.waste_type_id,
                                      quantity_kg: r.quantity_kg ?? x.quantity_kg, frequency: r.frequency, description: text })),
  });
  const create = useAction((b) => api("/offers", { method: "POST", body: b }), { invalidate: ["offers"], onSuccess: onDone });
  return (
    <Card className="highlight">
      <Field label="Décrivez votre offre avec vos mots" hint="Exemple : « 300 kg de manioc par semaine »">
        <div className="inline-form">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="300 kg de manioc par semaine" />
          <Btn kind="secondary" action={parse} onClick={() => parse.mutate(text)} type="button">Remplir</Btn>
        </div>
      </Field>
      <form onSubmit={(e) => {
        e.preventDefault();
        create.mutate({ waste_type_id: f.waste_type_id, quantity_kg: Number(f.quantity_kg), frequency: f.frequency,
                        description: f.description || null, lat: f.pos?.lat, lng: f.pos?.lng });
      }}>
        <div className="grid2">
          <Field label="Type de déchet">
            <select value={f.waste_type_id} onChange={(e) => setF({ ...f, waste_type_id: e.target.value })}>
              {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Quantité (kg)">
            <input inputMode="decimal" value={f.quantity_kg} required
                   onChange={(e) => setF({ ...f, quantity_kg: e.target.value.replace(",", ".") })} />
          </Field>
        </div>
        <Field label="Fréquence">
          <select value={f.frequency} onChange={(e) => setF({ ...f, frequency: e.target.value })}>
            {["ponctuelle", "quotidienne", "hebdomadaire", "mensuelle"].map((x) => <option key={x}>{x}</option>)}
          </select>
        </Field>
        <Field label="Lieu du gisement"><MapPicker value={f.pos} onChange={(pos) => setF({ ...f, pos })} /></Field>
        <div className="row">
          <Btn action={create} type="submit">Publier</Btn>
          <Btn kind="ghost" type="button" onClick={onDone}>Fermer</Btn>
        </div>
        <ErrorBox error={create.error || parse.error} />
      </form>
    </Card>
  );
}
