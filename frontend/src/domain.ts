export type Role =
  "patient" | "partner" | "clinician" | "helper" | "reviewer" | "operations";
export type Capability =
  | "records"
  | "questions"
  | "prepare"
  | "approve"
  | "share"
  | "clinical"
  | "tasks"
  | "evaluate"
  | "operate";
export function visitDateParts(value: string) {
  const date = new Date(`${value}T12:00:00Z`);
  return {
    month: date.toLocaleDateString("en-US", {
      month: "short",
      timeZone: "UTC",
    }),
    day: date.toLocaleDateString("en-US", { day: "numeric", timeZone: "UTC" }),
    weekday: date.toLocaleDateString("en-US", {
      weekday: "long",
      timeZone: "UTC",
    }),
    full: date.toLocaleDateString("en-US", {
      month: "long",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    }),
  };
}
export interface Persona {
  role: Role;
  name: string;
  initials: string;
  label: string;
  description: string;
  home: string;
  capabilities: Capability[];
}
export const personas: Persona[] = [
  {
    role: "patient",
    name: "Patient User",
    initials: "MP",
    label: "Patient",
    description: "Your records, questions, and next steps.",
    home: "/app/home",
    capabilities: ["records", "questions", "prepare", "share"],
  },
  {
    role: "partner",
    name: "Arjun Patel",
    initials: "AP",
    label: "Care partner",
    description: "Support an authorized patient within shared permissions.",
    home: "/app/home",
    capabilities: ["records", "questions", "prepare"],
  },
  {
    role: "clinician",
    name: "Clinician User",
    initials: "ME",
    label: "Treating clinician",
    description: "Review and publish for assigned patients.",
    home: "/app/clinician",
    capabilities: ["records", "clinical", "evaluate"],
  },
];
export interface Question {
  id: string;
  text: string;
  status: "Open" | "Discussed" | "Follow-up needed" | "Resolved";
  source: string;
  original: string;
  clinicianResponse?: string;
}
export interface Task {
  id: string;
  title: string;
  description: string;
  origin: string;
  complete: boolean;
  blocked?: string;
}
export interface Reminder {
  text: string;
  date: string;
  time: string;
  timezone: string;
  channel: "In-app" | "Email" | "SMS";
  status:
    | "Awaiting approval"
    | "Scheduled · simulated"
    | "Paused · needs reapproval"
    | "Cancelled";
  version: number;
  approvedVersion: number | null;
}
export interface CareState {
  questions: Question[];
  tasks: Task[];
  reminder: Reminder;
  booking: "Not requested" | "Confirmed · simulated";
  published: boolean;
  publicationType: string;
  fieldDate: string;
  fieldNote: string;
  partnerAccess: boolean;
  partnerApproval: boolean;
  events: { id: string; title: string; detail: string }[];
}
export const initialState = (): CareState => ({
  questions: [],
  tasks: [],
  reminder: {
    text: "",
    date: "",
    time: "09:00",
    timezone: "America/New_York",
    channel: "In-app",
    status: "Awaiting approval",
    version: 1,
    approvedVersion: null,
  },
  booking: "Not requested",
  published: false,
  publicationType: "",
  fieldDate: "",
  fieldNote: "",
  partnerAccess: false,
  partnerApproval: false,
  events: [],
});
