// Client-side capability map. The BACKEND is authoritative (every endpoint is
// role-gated); this table only hides controls the user cannot use. It MUST mirror
// the backend gate matrix in webapp/api/main.py + masters/routes.py + auth/routes.py.

export type Role = 'admin' | 'editor' | 'viewer';

export type Capability =
  | 'generate' // POST /jobs (run the solver)
  | 'editRoster' // /rosters/{id}/edits|undo|redo|resolve, freeze
  | 'editMasters' // /masters write/clone/予定申請 import
  | 'confirm' // POST /rosters/{id}/confirm
  | 'manageUsers' // /auth/users
  | 'viewArchive'; // GET /archives (+ download)

const CAP_MATRIX: Record<Role, Record<Capability, boolean>> = {
  admin: {
    generate: true,
    editRoster: true,
    editMasters: true,
    confirm: true,
    manageUsers: true,
    viewArchive: true,
  },
  editor: {
    generate: false,
    editRoster: true,
    editMasters: false,
    confirm: false,
    manageUsers: false,
    viewArchive: true,
  },
  viewer: {
    generate: false,
    editRoster: false,
    editMasters: false,
    confirm: false,
    manageUsers: false,
    viewArchive: true,
  },
};

export function can(role: Role, cap: Capability): boolean {
  return CAP_MATRIX[role]?.[cap] ?? false;
}
