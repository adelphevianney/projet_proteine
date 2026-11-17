import { useQuery } from "@tanstack/react-query";
import { api, kg } from "../api";
import { useAuth } from "../auth";
import { MapView } from "../components/Maps";
import { Card, ErrorBox, Loading, Page, Prompt, useAction } from "../components/ui";

export function TourPage() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["tour"], queryFn: () => api("/tour") });
  const collect = useAction(({ id, w }) => api(`/lots/${id}/collect`, { method: "POST", body: { weight_kg: w } }),
                            { invalidate: ["tour", "payments"] });
  return (
    <Page title="Ma tournée" subtitle="Du plus proche au plus lointain.">
      <Loading q={q}>{(d) => (
        <>
          <p><b>{d.stops.length}</b> enlèvement(s) · <b>{d.total_km} km</b> au total</p>
          <MapView center={{ lat: user.lat, lng: user.lng }}
                   points={d.stops.map((s, i) => ({ id: s.id, lat: s.lat, lng: s.lng, label: `${i + 1}. ${s.waste_type}` }))} />
          {d.stops.map((s, i) => (
            <Card key={s.id}>
              <div className="row space"><b>{i + 1}. {s.waste_type}</b><span className="pill">+{s.leg_km} km</span></div>
              <div className="small">{s.producer_name} · {s.commune} · annoncé {kg(s.announced_kg)}</div>
              <div className="muted small">À livrer à {s.farm_name} · {s.code}</div>
              <Prompt label="Enlevé : saisir le poids" kind="primary" inputMode="decimal" placeholder="Poids pesé (kg)" action={collect}
                      onSubmit={(w) => collect.mutate({ id: s.id, w: Number(String(w).replace(",", ".")) })} />
            </Card>
          ))}
        </>
      )}</Loading>
      <ErrorBox error={collect.error} />
    </Page>
  );
}
