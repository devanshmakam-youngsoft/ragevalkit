import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, authEvents } from "./api";

interface AuthCtx {
  /** null = signed out; undefined = still checking the session. */
  user: string | null | undefined;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    api.me()
      .then((u) => setUser(u.username))
      .catch(() => setUser(null));
    const onUnauthorized = () => setUser(null);
    authEvents.addEventListener("unauthorized", onUnauthorized);
    return () => authEvents.removeEventListener("unauthorized", onUnauthorized);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setUser((await api.login(username, password)).username);
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setUser(null);
  }, []);

  return (
    <Ctx.Provider value={{ user, login, logout }}>
      {children}
    </Ctx.Provider>
  );
}
