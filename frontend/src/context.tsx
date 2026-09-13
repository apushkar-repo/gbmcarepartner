import { createContext, useContext, useState, type ReactNode } from "react";
import {
  initialState,
  personas,
  type CareState,
  type Persona,
  type Role,
  type Capability,
} from "./domain";

interface Store {
  persona: Persona | null;
  state: CareState;
  login: (role: Role) => void;
  logout: () => void;
  can: (cap: Capability) => boolean;
  update: (
    change: (s: CareState) => CareState,
    title?: string,
    detail?: string,
  ) => void;
  toast: string;
  notify: (text: string) => void;
}
const Context = createContext<Store | null>(null);
export function CareProvider({ children }: { children: ReactNode }) {
  const [persona, setPersona] = useState<Persona | null>(null);
  const [state, setState] = useState<CareState>(initialState);
  const [toast, setToast] = useState("");
  const login = (role: Role) => {
    setPersona(personas.find((p) => p.role === role)!);
    setToast("");
  };
  const logout = () => {
    sessionStorage.removeItem("carebridge.role");
    sessionStorage.removeItem("carebridge.patientId");
    sessionStorage.removeItem("carebridge.actorId");
    setPersona(null);
    setState(initialState());
    setToast("");
  };
  const can = (cap: Capability) => {
    if (!persona) return false;
    if (persona.role === "partner")
      return (
        !!sessionStorage.getItem("carebridge.patientId") &&
        persona.capabilities.includes(cap)
      );
    return persona.capabilities.includes(cap);
  };
  const update: Store["update"] = (
    change,
    title,
    detail = "Frontend simulation · This session only",
  ) => {
    setState((s) => {
      const next = change(s);
      return title
        ? {
            ...next,
            events: [
              { id: crypto.randomUUID(), title, detail },
              ...next.events,
            ],
          }
        : next;
    });
    if (title) setToast(title);
  };
  return (
    <Context.Provider
      value={{
        persona,
        state,
        login,
        logout,
        can,
        update,
        toast,
        notify: setToast,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useCare() {
  const value = useContext(Context);
  if (!value) throw new Error("CareProvider missing");
  return value;
}
