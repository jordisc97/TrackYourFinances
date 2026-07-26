import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken, type Household, type User } from "./api";

type AuthState = {
  user: User | null;
  household: Household | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: { email: string; password: string; display_name: string; household_name: string }) => Promise<void>;
  join: (payload: { email: string; password: string; display_name: string; invite_code: string }) => Promise<void>;
  logout: () => void;
  refreshHousehold: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [household, setHousehold] = useState<Household | null>(null);
  const [loading, setLoading] = useState(true);

  async function bootstrap() {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    const me = await api.me();
    const hh = await api.household();
    setUser(me);
    setHousehold(hh);
    setLoading(false);
  }

  useEffect(() => {
    bootstrap().catch(() => {
      setToken(null);
      setLoading(false);
    });
  }, []);

  async function afterAuth(token: string) {
    setToken(token);
    const me = await api.me();
    const hh = await api.household();
    setUser(me);
    setHousehold(hh);
  }

  const value: AuthState = {
    user,
    household,
    loading,
    login: async (email, password) => afterAuth((await api.login({ email, password })).access_token),
    register: async (payload) => afterAuth((await api.register(payload)).access_token),
    join: async (payload) => afterAuth((await api.join(payload)).access_token),
    logout: () => {
      setToken(null);
      setUser(null);
      setHousehold(null);
    },
    refreshHousehold: async () => setHousehold(await api.household()),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("AuthProvider missing");
  return ctx;
}
