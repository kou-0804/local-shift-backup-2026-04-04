import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SafetyGateBanner } from './SafetyGateBanner';
import * as api from '../api/mastersApi';

function renderBanner(onChange?: (ok: boolean) => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SafetyGateBanner setId={2} onResult={onChange} />
    </QueryClientProvider>,
  );
}

describe('SafetyGateBanner', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders nothing blocking when the gate passes', async () => {
    vi.spyOn(api, 'safetyCheck').mockResolvedValue({ ok: true, missing: [] });
    const cb = vi.fn();
    renderBanner(cb);
    await waitFor(() => expect(cb).toHaveBeenCalledWith(true));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows a blocking alert naming every missing id', async () => {
    vi.spyOn(api, 'safetyCheck').mockResolvedValue({ ok: false, missing: ['T072', 'T013'] });
    const cb = vi.fn();
    renderBanner(cb);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByText(/T072/)).toBeInTheDocument();
    expect(screen.getByText(/T013/)).toBeInTheDocument();
    expect(cb).toHaveBeenCalledWith(false);
  });
});
