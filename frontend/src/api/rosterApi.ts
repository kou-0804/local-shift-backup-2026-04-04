import { getJson, apiUrl } from './http';
import type { WireRosterResponse } from '../domain/wire';

export const getRoster = (rid: string) => getJson<WireRosterResponse>(`/rosters/${rid}`);
export const getExcelUrl = (rid: string) => apiUrl(`/rosters/${rid}/excel`);
