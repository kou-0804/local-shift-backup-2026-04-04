import { getJson, apiUrl } from './http';
import type { WireRosterResponse, WireRosterSummary } from '../domain/wire';

export const listRosters = () => getJson<WireRosterSummary[]>('/rosters');
export const getRoster = (rid: string) => getJson<WireRosterResponse>(`/rosters/${rid}`);
export const getExcelUrl = (rid: string) => apiUrl(`/rosters/${rid}/excel`);
