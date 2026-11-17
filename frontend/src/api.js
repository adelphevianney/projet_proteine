// Client HTTP : jeton de session, messages d'erreur lisibles, clé d'idempotence pour les actions sensibles.
const TOKEN_KEY = "pc_token";

export const getToken = () => {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
};
export const setToken = (t) => {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* navigation privée */ }
};

// crypto.randomUUID n'existe qu'en contexte sécurisé (https ou localhost) : repli pour un test sur le réseau local en http.
const newKey = () =>
  globalThis.crypto?.randomUUID?.() ??
  `${Date.now().toString(36)}-${Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("")}`;

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export async function api(path, { method = "GET", body, idempotent = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (idempotent) headers["Idempotency-Key"] = newKey();
  const res = await fetch(`/api/v1${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    let msg = data.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join(" ; ");
    if (res.status === 401 && token && path !== "/auth/otp/verify") {
      setToken(null);
      window.dispatchEvent(new Event("pc-logout")); // session expirée : l'application revient à la connexion
    }
    throw new ApiError(res.status, msg || "Erreur réseau, réessayez");
  }
  return data;
}

export const fcfa = (n) => `${Math.round(Number(n || 0)).toLocaleString("fr-FR")} FCFA`;
export const kg = (n) => `${Number(n || 0).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} kg`;
export const date = (d) => d ? new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
