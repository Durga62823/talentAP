import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { useAuth } from "./auth";

export type Conn = {
  id: string;
  name: string;
  kind: "sqlite" | "postgresql" | "mysql";
  params: Record<string, any>;
  has_password: boolean;
  allowed_schemas: string[];
  status: string;
  status_detail: string;
  last_tested_at: string | null;
  tables_classified: number;
  last_scan: { id: string; status: string; finished_at: string | null } | null;
};

export const KIND_LABEL: Record<string, string> = { sqlite: "SQLite", postgresql: "PostgreSQL", mysql: "MySQL" };

type Ctx = { connections: Conn[]; selected: Conn | null; select: (id: string) => void; isLoading: boolean };
const C = createContext<Ctx | null>(null);
const KEY = "sm.selectedConnection";

function readKey() {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function ConnectionProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["connections"], queryFn: () => api<Conn[]>("/api/databases"), enabled: !!user });
  const [id, setId] = useState<string | null>(readKey);
  const list = q.data ?? [];
  const selected = list.find((c) => c.id === id) ?? list[0] ?? null;

  useEffect(() => {
    if (selected && selected.id !== id) setId(selected.id);
  }, [selected, id]);

  const select = (v: string) => {
    setId(v);
    try {
      localStorage.setItem(KEY, v);
    } catch {
      /* storage unavailable - selection just won't persist */
    }
  };
  return <C.Provider value={{ connections: list, selected, select, isLoading: q.isLoading }}>{children}</C.Provider>;
}

export function useConnections() {
  const v = useContext(C);
  if (!v) throw new Error("useConnections outside provider");
  return v;
}
