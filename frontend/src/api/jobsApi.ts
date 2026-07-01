import { getJson, postJson } from './http';

/** POST /jobs response + GET /jobs/{id} shape (spec §: generate → poll → freeze). */
export interface JobStatus {
  id: string;
  year?: number;
  month?: number;
  status: 'queued' | 'running' | 'done' | 'failed';
  error?: string | null;
}

export interface FreezeResult {
  roster_id: number;
}

/** GET /masters/requests/{year}/{month} — 予定申請 import status for a month. */
export interface RequestsStatus {
  year: number;
  month: number;
  imported: boolean;
  import_id: number | null;
  row_count: number;
  imported_at: string | null;
  source_filename: string | null;
}

export const createJob = (year: number, month: number) =>
  postJson<JobStatus>('/jobs', { year, month });

export const getJob = (id: string) => getJson<JobStatus>(`/jobs/${id}`);

export const freezeJob = (id: string) => postJson<FreezeResult>(`/jobs/${id}/freeze`, {});

export const getRequestsStatus = (year: number, month: number) =>
  getJson<RequestsStatus>(`/masters/requests/${year}/${month}`);
