import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, date, fcfa, kg } from "../api";
import { useAuth } from "../auth";
import { MapView } from "../components/Maps";
import { Badge, Btn, Card, Empty, ErrorBox, Field, Loading, Page, Prompt, useAction } from "../components/ui";

export function NearbyPage() {
  const { user } = useAuth();
  const [km, setKm] = useState(50);
  const q = useQuery({ queryKey: ["nearby", km], queryFn: () => api(`/offers/nearby?km=${km}`) });
  const reserve = useAction((id) => api(`/offers/${id}/reserve`, { method: "POST" }), { invalidate: ["nearby", "lots"] });
  return (
    <Page title="Offres proches" subtitle="Triées de la plus proche à la plus lointaine.">
      <Field label={`Rayon : ${km} km`}>
        <input type="range" min="5" max="300" step="5" value={km} onChange={(e) => setKm(Number(e.target.value))} />
      </Field>
      <Loading q={q}>{(items) => (
        <>
          <MapView center={{ lat: user.lat, lng: user.lng }}
                   points={items.map((o) => ({ id: o.id, lat: o.lat, lng: o.lng, label: `${o.waste_type} · ${kg(o.quantity_kg)}` }))} />
          {items.length === 0 && <Empty>Aucune offre dans ce rayon.</Empty>}
          {items.map((o) => (
            <Card key={o.id}>
              <div className="row space"><b>{o.waste_type} · {kg(o.quantity_kg)}</b><span className="pill">{o.distance_km} km</span></div>
              <div className="muted small">{o.producer_name} · {o.commune} · {o.frequency} · {fcfa(o.price_per_kg)}/kg</div>
              {o.risk && <p className="small">Vigilance : {o.risk}</p>}
              <Btn action={reserve} onClick={() => reserve.mutate(o.id)}>Réserver</Btn>
            </Card>
          ))}
        </>
      )}</Loading>
      <ErrorBox error={reserve.error} />
      {reserve.data && <p className="notice">Lot {reserve.data.lot_code} réservé{reserve.data.collector_id ? ", un collecteur est prévenu." : " (aucun collecteur disponible pour l'instant)."}</p>}
    </Page>
  );
}

export function LotsPage() {
  const q = useQuery({ queryKey: ["lots"], queryFn: () => api("/lots") });
  const receive = useAction(({ id, quality }) => api(`/lots/${id}/receive`, { method: "POST", body: { quality } }),
                            { invalidate: ["lots", "payments"] });
  const recall = useAction(({ id, reason }) => api(`/lots/${id}/recall`, { method: "POST", body: { reason } }),
                           { invalidate: ["lots", "flour"] });
  return (
    <Page title="Mes lots de déchets" subtitle="Contrôlez la qualité à la réception.">
      <Loading q={q} empty="Aucun lot. Réservez une offre proche.">{(items) => items.map((l) => (
        <Card key={l.id}>
          <div className="row space"><b>{l.code}</b><Badge status={l.status} /></div>
          <div className="small">{l.waste_type} · annoncé {kg(l.announced_kg)}{l.weight_kg ? ` · pesé ${kg(l.weight_kg)}` : ""}</div>
          <div className="muted small">{l.producer_name} · collecteur : {l.collector_name || "à affecter"} · {date(l.created_at)}</div>
          {l.quality && <div className="small">Qualité : <Badge status={l.quality} /></div>}
          {l.status === "collected" && (
            <div className="row wrap">
              <Btn action={receive} onClick={() => receive.mutate({ id: l.id, quality: "conforme" })}>Conforme</Btn>
              <Btn kind="secondary" action={receive} onClick={() => receive.mutate({ id: l.id, quality: "degrade" })}>Dégradé (−30 %)</Btn>
              <Btn kind="danger" action={receive} onClick={() => receive.mutate({ id: l.id, quality: "rejete" })}>Rejeter</Btn>
            </div>
          )}
          {["reserved", "collected", "received", "used"].includes(l.status) && (
            <Prompt label="Retirer ce lot" kind="ghost" placeholder="Motif du retrait" action={recall}
                    onSubmit={(reason) => { if (confirm("Retirer ce lot ? La farine produite et les commandes seront retirées.")) recall.mutate({ id: l.id, reason }); }} />
          )}
        </Card>
      ))}</Loading>
      <ErrorBox error={receive.error || recall.error} />
      {recall.data && <p className="notice">Retrait effectué : {recall.data.flour_batches} lot(s) de farine, {recall.data.orders_cancelled} commande(s) annulée(s), {recall.data.breeders_alerted} éleveur(s) alerté(s).</p>}
    </Page>
  );
}

export function FlourPage() {
  const lots = useQuery({ queryKey: ["lots"], queryFn: () => api("/lots") });
  const q = useQuery({ queryKey: ["flour"], queryFn: () => api("/flour-batches/mine") });
  const [sel, setSel] = useState([]);
  const [f, setF] = useState({ quantity_kg: "", price_per_kg: "350" });
  const declare = useAction((b) => api("/flour-batches", { method: "POST", body: b }),
                            { invalidate: ["flour", "lots"], onSuccess: () => { setSel([]); setF({ ...f, quantity_kg: "" }); } });
  const recall = useAction(({ id, reason }) => api(`/flour-batches/${id}/recall`, { method: "POST", body: { reason } }),
                           { invalidate: ["flour"] });
  const ready = (lots.data || []).filter((l) => l.status === "received");
  return (
    <Page title="Farine" subtitle="Chaque lot de farine est relié à ses déchets d'origine (environ 14 jours de transformation).">
      <Card className="highlight">
        <h3>Déclarer un lot de farine</h3>
        {ready.length === 0 ? <Empty>Aucun lot de déchets réceptionné disponible.</Empty> : ready.map((l) => (
          <label key={l.id} className="check">
            <input type="checkbox" checked={sel.includes(l.id)}
                   onChange={(e) => setSel(e.target.checked ? [...sel, l.id] : sel.filter((x) => x !== l.id))} />
            {l.code} · {l.waste_type} · {kg(l.weight_kg)}
          </label>
        ))}
        <div className="grid2">
          <Field label="Farine produite (kg)"><input inputMode="decimal" value={f.quantity_kg}
                 onChange={(e) => setF({ ...f, quantity_kg: e.target.value.replace(",", ".") })} /></Field>
          <Field label="Prix (FCFA/kg)"><input inputMode="numeric" value={f.price_per_kg}
                 onChange={(e) => setF({ ...f, price_per_kg: e.target.value.replace(/\D/g, "") })} /></Field>
        </div>
        <Btn action={declare} disabled={!sel.length || !f.quantity_kg}
             onClick={() => declare.mutate({ source_lot_ids: sel, quantity_kg: Number(f.quantity_kg), price_per_kg: Number(f.price_per_kg) })}>
          Déclarer la farine
        </Btn>
        <ErrorBox error={declare.error} />
      </Card>
      <h3>Mon stock</h3>
      <Loading q={q} empty="Aucun lot de farine.">{(items) => items.map((b) => (
        <Card key={b.id}>
          <div className="row space"><b>{b.code}</b><Badge status={b.status} /></div>
          <div className="small">Stock {kg(b.stock_kg)} / {kg(b.quantity_kg)} · {fcfa(b.price_per_kg)}/kg</div>
          <div className="muted small">Origine : {(b.source_codes || []).join(", ")}</div>
          {b.status !== "recalled" && <Prompt label="Retirer" kind="ghost" placeholder="Motif" action={recall}
                                              onSubmit={(reason) => recall.mutate({ id: b.id, reason })} />}
        </Card>
      ))}</Loading>
      <ErrorBox error={recall.error} />
    </Page>
  );
}

export function IncomingOrdersPage() {
  const q = useQuery({ queryKey: ["incoming"], queryFn: () => api("/orders/incoming") });
  const deliver = useAction((id) => api(`/orders/${id}/deliver`, { method: "POST" }), { invalidate: ["incoming"] });
  return (
    <Page title="Commandes" subtitle="Livrez la farine ; le transport se convient avec l'éleveur.">
      <Loading q={q} empty="Aucune commande.">{(items) => items.map((o) => (
        <Card key={o.id}>
          <div className="row space"><b>{o.breeder_name} · {kg(o.quantity_kg)}</b><Badge status={o.status} /></div>
          <div className="muted small">{o.flour_code} · {fcfa(o.total_fcfa)} · {o.breeder_commune} · {o.breeder_phone}</div>
          {o.status === "ordered" && <Btn action={deliver} onClick={() => deliver.mutate(o.id)}>Marquer livrée</Btn>}
        </Card>
      ))}</Loading>
      <ErrorBox error={deliver.error} />
    </Page>
  );
}
