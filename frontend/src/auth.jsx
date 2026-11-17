import { createContext, useContext, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getToken, setToken } from "./api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const qc = useQueryClient();
  const [token, setTok] = useState(getToken());
  useEffect(() => {
    const onExpired = () => { qc.clear(); setTok(null); };
    window.addEventListener("pc-logout", onExpired);
    return () => window.removeEventListener("pc-logout", onExpired);
  }, [qc]);
  const me = useQuery({ queryKey: ["me", token], queryFn: () => api("/me"), enabled: !!token, retry: false });
  const value = {
    user: token && !me.error ? me.data : null,
    loading: !!token && me.isLoading,
    login: (t) => { setToken(t); qc.clear(); setTok(t); },
    logout: () => { setToken(null); qc.clear(); setTok(null); window.location.assign("/"); },
  };
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
