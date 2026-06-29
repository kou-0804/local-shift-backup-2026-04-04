import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConflictDialog } from './ConflictDialog';

describe('ConflictDialog', () => {
  it('shows the server version and rebases on confirm', async () => {
    const onRebase = vi.fn();
    render(<ConflictDialog version={9} onRebase={onRebase} onCancel={() => {}} />);
    expect(screen.getByText(/version 9/i)).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('rebase'));
    expect(onRebase).toHaveBeenCalled();
  });
});
