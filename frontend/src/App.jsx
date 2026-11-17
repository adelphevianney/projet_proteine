import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { useAuth } from "./auth";
import Login from "./pages/Login";
import { DisputesPage, ImpactPage, NotificationsPage, PaymentsPage, PricesPage, ProfilePage, TracePage } from "./pages/Shared";
import { OffersPage } from "./roles/Producer";
import { FlourPage, IncomingOrdersPage, LotsPage, NearbyPage } from "./roles/Farm";
import { FormulatorPage, HerdsPage, MarketPage, MyOrdersPage } from "./roles/Breeder";
import { TourPage } from "./roles/Collector";
import { AccountsPage, AdminDisputesPage, AdminPaymentsPage, JournalPage } from "./roles/Admin";

// Onglets de chaque rôle, repris de la fiche de présentation.
const TABS = {
  producer: [["offres", "Mes offres", OffersPage], ["paiements", "Paiements", PaymentsPage],
             ["litiges", "Litiges", DisputesPage], ["impact", "Impact", ImpactPage]],
  farm: [["offres", "Offres proches", NearbyPage], ["lots", "Mes lots", LotsPage], ["farine", "Farine", FlourPage],
         ["commandes", "Commandes", IncomingOrdersPage], ["paiements", "Paiements", PaymentsPage],
         ["litiges", "Litiges", DisputesPage], ["impact", "Impact", ImpactPage]],
  breeder: [["elevages", "Mes élevages", HerdsPage], ["formulateur", "Formulateur", FormulatorPage],
            ["farine", "Farine", MarketPage], ["commandes", "Commandes", MyOrdersPage], ["prix", "Prix", PricesPage],
            ["paiements", "Paiements", PaymentsPage], ["impact", "Impact", ImpactPage]],
  collector: [["tournee", "Ma tournée", TourPage], ["paiements", "Paiements", PaymentsPage], ["impact", "Impact", ImpactPage]],
  admin: [["comptes", "Comptes", AccountsPage], ["litiges", "Litiges", AdminDisputesPage],
          ["paiements", "Paiements", AdminPaymentsPage], ["impact", "Impact", ImpactPage], ["journal", "Journal", JournalPage]],
};

const Icon = ({ d }) => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
);

function Header({ user }) {
  const navigate = useNavigate();
  const notes = useQuery({ queryKey: ["notifications"], queryFn: () => api("/notifications"), refetchInterval: 30_000 });
  const unread = (notes.data || []).filter((n) => !n.read_at).length;
  return (
    <header className="topbar">
      <button className="brand-mini" onClick={() => navigate("/")}><img src="/icon.svg" alt="" width="28" height="28" /> Protéine</button>
      <div className="row">
        <button className="icon-btn" onClick={() => navigate("/tracer")} title="Traçabilité" aria-label="Traçabilité"><Icon d="M11 4a7 7 0 1 0 4.4 12.4L20 21M11 4a7 7 0 0 1 0 14" /></button>
        <button className="icon-btn" onClick={() => navigate("/notifications")} title="Notifications" aria-label="Notifications">
          <Icon d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0" />{unread > 0 && <span className="dot">{unread}</span>}
        </button>
        <button className="avatar" onClick={() => navigate("/profil")} title={user.name}>{user.name.slice(0, 1)}</button>
      </div>
    </header>
  );
}

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <p className="muted center pad">Chargement…</p>;
  if (!user) return <Login />;
  const tabs = TABS[user.role] || [];
  return (
    <div className="shell">
      <Header user={user} />
      {user.status === "pending" && <p className="banner">Compte en attente de validation : vous pourrez agir une fois validé.</p>}
      <Routes>
        {tabs.map(([path, , Comp]) => <Route key={path} path={`/${path}`} element={<Comp />} />)}
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/tracer" element={<TracePage />} />
        <Route path="/profil" element={<ProfilePage />} />
        <Route path="/prix" element={<PricesPage />} />
        <Route path="*" element={<Navigate to={`/${tabs[0]?.[0] || "profil"}`} replace />} />
      </Routes>
      <nav className="tabbar">
        {tabs.map(([path, label]) => <NavLink key={path} to={`/${path}`}>{label}</NavLink>)}
      </nav>
    </div>
  );
}
