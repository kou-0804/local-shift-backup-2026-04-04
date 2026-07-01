import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

export const rosterKey = (rid: string) => ['roster', rid] as const;
export const rosterListKey = ['rosters'] as const;
