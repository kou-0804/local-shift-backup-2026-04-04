import { useQuery } from '@tanstack/react-query';
import * as api from '../api/mastersApi';
import { masterKey, masterSetsKey } from './masterKeys';

// Thin useQuery wrappers keyed via masterKey(setId, master[, scope]).
export const useMasterSets = () =>
  useQuery({ queryKey: masterSetsKey, queryFn: api.listMasterSets });

export const useStaff = (set: number) =>
  useQuery({ queryKey: masterKey(set, 'staff'), queryFn: () => api.listStaff(set) });

export const useSkillMatrix = (set: number) =>
  useQuery({ queryKey: masterKey(set, 'skill'), queryFn: () => api.getSkillMatrix(set) });

export const useLocation = (set: number) =>
  useQuery({ queryKey: masterKey(set, 'location_set', 'location'), queryFn: () => api.getLocation(set) });

export const usePowerBalance = (set: number) =>
  useQuery({ queryKey: masterKey(set, 'location_set', 'pb'), queryFn: () => api.getPowerBalance(set) });

export const useSpecialRules = (set: number) =>
  useQuery({ queryKey: masterKey(set, 'special_rules'), queryFn: () => api.getSpecialRules(set) });

export const useTraining = (set: number) =>
  useQuery({ queryKey: masterKey(set, 'training'), queryFn: () => api.getTraining(set) });

export const useNightQuota = (set: number, ym: string) =>
  useQuery({ queryKey: masterKey(set, 'night_quota', ym), queryFn: () => api.getNightQuota(set, ym) });

export const useNightOverrides = (set: number) =>
  useQuery({ queryKey: masterKey(set, 'night_overrides'), queryFn: () => api.getNightOverrides(set) });

export const useHolidayTargets = (set: number) =>
  useQuery({ queryKey: masterKey(set, 'holiday_targets'), queryFn: () => api.getHolidayTargets(set) });
