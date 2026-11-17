import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, date, fcfa } from "../api";
import { Badge, Btn, Card, ErrorBox, Loading, Page, Prompt, useAction } from "../components/ui";

const ROLE = { producer: "Producteur", farm: "Ferme", breeder: "Éleveur", collector: "Collecteur", admin: "Admin" };

export function AccountsPage() {
  const [status, setStatus] = useState("pending");
  const q = useQuery({ queryKey: ["users", status], queryFn: () => api(`/admin/users${status ? `?status=${status}` : ""}`) });
  const act = useAction(({ id, verb }) => api(`/admin/users/${id}/${verb}`, { method: "POST" }), { invalidate: ["users"] });
  return (
    <Page title="Comptes" subtitle="Les fermes et les collecteurs sont validés ici.">
      <div className="tabs-inline">
        {[["pending", "À valider"], ["active", "Actifs"], ["disabled", "Désactivés"], ["", "Tous"]].map(([k, l]) => (
          <button key={k} className={status === k ? "on" : ""} onClick={() => setStatus(k)}>{l}</button>))}
      </div>
      <Loading q={q} empty="Aucun compte.">{(items) => items.map((u) => (
        <Card key={u.id}>
          <div className="row space"><b>{u.name}</b><Badge status={u.status} /></div>
          <div className="muted small">{ROLE[u.role]} · {u.phone} · {u.commune || ""}</div>
          {u.role !== "admin" && (
            <div className="row">
              {u.status !== "active" && <Btn action={act} onClick={() => act.mutate({ id: u.id, verb: "validate" })}>Valider</Btn>}
              {u.status === "active" && <Btn kind="ghost" action={act} onClick={() => act.mutate({ id: u.id, verb: "disable" })}>Désactiver</Btn>}
            </div>
          )}
        </Card>
      ))}</Loading>
      <ErrorBox error={act.error} />
    </Page>
  );
}

export function AdminDisputesPage() {
  const q = useQuery({ queryKey: ["admin-disputes"], queryFn: () => api("/admin/disputes") });
  const resolve = useAction(({ id, resolution }) => api(`/admin/disputes/${id}/resolve`, { method: "POST", body: { resolution } }),
                            { invalidate: ["admin-disputes"] });
  return (
    <Page title="Litiges">
      <Loading q={q} empty="Aucun litige.">{(items) => items.map((d) => (
        <Card key={d.id}>
          <div className="row space"><b>{d.subject}</b><Badge status={d.status} /></div>
          <div className="muted small">{d.author_name} · {date(d.created_at)} {d.ref_code && `· ${d.ref_code}`}</div>
          <p className="small">{d.body}</p>
          {d.resolution ? <p className="notice small">Réponse : {d.resolution}</p> :
            <Prompt label="Répondre et clore" placeholder="Réponse" action={resolve}
                    onSubmit={(resolution) => resolve.mutate({ id: d.id, resolution })} />}
        </Card>
      ))}</Loading>
      <ErrorBox error={resolve.error} />
    </Page>
  );
}

export function AdminPaymentsPage() {
  const q = useQuery({ queryKey: ["admin-payments"], queryFn: () => api("/admin/payments") });
  return (
    <Page title="Paiements" subtitle="Tous les paiements enregistrés.">
      <Loading q={q} empty="Aucun paiement.">{(items) => (
        <table className="table">
          <thead><tr><th>Type</th><th>De → à</th><th>Montant</th><th>État</th></tr></thead>
          <tbody>{items.map((p) => (
            <tr key={p.id}><td>{p.kind}<div className="muted small">{p.ref_code}</div></td>
              <td className="small">{p.payer_name} → {p.payee_name}</td><td>{fcfa(p.amount_fcfa)}</td>
              <td><Badge status={p.status} /></td></tr>
          ))}</tbody>
        </table>
      )}</Loading>
    </Page>
  );
}

export function JournalPage() {
  const [since, setSince] = useState(null);
  const q = useQuery({ queryKey: ["changes", since], queryFn: () => api(`/changes${since ? `?since=${since}` : ""}`) });
  return (
    <Page title="Journal des changements" subtitle="Lecture incrémentale : seuls les changements depuis le dernier jeton sont renvoyés.">
      <Loading q={q}>{(d) => (
        <>
          <p className="small">{d.changes.length} changement(s), les 50 plus récents affichés · jeton suivant <code>{d.next}</code></p>
          <Btn kind="secondary" onClick={() => setSince(d.next)}>Voir seulement les nouveaux</Btn>
          {since && <Btn kind="ghost" onClick={() => setSince(null)}>Tout revoir</Btn>}
          <table className="table">
            <thead><tr><th>#</th><th>Table</th><th>Opération</th><th>Quand</th></tr></thead>
            <tbody>{[...d.changes].reverse().slice(0, 50).map((c) => (
              <tr key={c.seq}><td>{c.seq}</td><td>{c.table_name}</td>
                <td>{c.op}{c.new_data?.status && <> → <Badge status={c.new_data.status} /></>}</td>
                <td className="small">{date(c.at)}</td></tr>
            ))}</tbody>
          </table>
        </>
      )}</Loading>
    </Page>
  );
}
