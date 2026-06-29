// Request payloads use `staff_id` per the authoritative P2a edit contract.
// (The plan's draft used `sid`; the live API keys staff by `staff_id`.)

// move endpoints are nested {date, location} objects, not bare ISO strings.
export interface MoveEndpoint {
  date: string; // ISO "2026-06-16"
  location: string;
}

export type EditOp =
  | { op: 'assign'; staff_id: string; date: string; location: string }
  | { op: 'unassign'; staff_id: string; date: string; location?: string }
  | { op: 'move'; staff_id: string; from: MoveEndpoint; to: MoveEndpoint }
  | { op: 'toggle_lock'; staff_id: string; date: string; location?: string; locked: boolean }
  // set_symbol is a frontend convenience beyond the 4 documented core ops; the
  // backend may reject it until wired. Kept so the popover can offer 申請 symbols.
  | { op: 'set_symbol'; staff_id: string; date: string; symbol: string | null };

export type EditRequest = EditOp & { expected_version: number };
