import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "./api";
import { clearPurposeBinding } from "./purpose";

export type User = { id: string; username: string; display_name: string; role: string; permissions: string[] };

type AuthState = {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (perm: string) => boolean;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();

  const refresh = useCallback(async () => {
    try {
      const r = await api<{ user: User }>("/api/auth/me");
      setUser(r.user);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        if (typeof localStorage !== "undefined") localStorage.removeItem("sm_token");
        setUser(null);
      } else {
        throw e;
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh().catch(() => setLoading(false));
  }, [refresh]);

  const login = async (username: string, password: string) => {
    const r = await api<{ user: User; token?: string }>("/api/auth/login", { body: { username, password, mode: "cookie" } });
    if (r.token && typeof localStorage !== "undefined") {
      localStorage.setItem("sm_token", r.token);
    }
    qc.clear();
    setUser(r.user);
  };

  const logout = async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      if (typeof localStorage !== "undefined") localStorage.removeItem("sm_token");
      clearPurposeBinding();
      qc.clear();
      setUser(null);
    }
  };

  const can = (perm: string) => !!user?.permissions.includes(perm);

  return <Ctx.Provider value={{ user, loading, login, logout, can, refresh }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside provider");
  return v;
}

export function getRoleHome(role?: string): string {
  switch (role) {
    case "support":
      return "/support/overview";
    case "analyst":
      return "/analyst/overview";
    case "compliance":
      return "/admin/overview";
    case "admin":
    default:
      return "/admin/overview";
  }
}

// Official sample users from the B1 dataset (data/users.csv) + Compliance Officer.
// Demo-only passwords (one per role) - local demonstration environment only.
export const DEMO_ACCOUNTS = [
  // Admin Identities
  { username: "admin_anita", password: "Admin@2026!", role: "admin", label: "Anita Rao (Admin)", email: "admin_anita@saffronbank.example" },

  // Support Identities
  { username: "support_ravi", password: "Support@2026!", role: "support", label: "Ravi Kumar (Support)", email: "support_ravi@saffronbank.example" },


  // Analyst Identities
  { username: "analyst_kavya", password: "Analyst@2026!", role: "analyst", label: "Kavya Hegde (Analyst)", email: "analyst_kavya@saffronbank.example" },


  // Compliance Identity
  // { username: "compliance_lata", password: "Compliance@2026!", role: "compliance", label: "Lata Menon (Compliance)", email: "compliance_lata@saffronbank.example", blurb: "Reviews tags, audit chains and data integrity without raw PII access" },
];
