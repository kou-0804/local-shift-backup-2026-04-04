import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Legend } from './Legend';

describe('Legend', () => {
  it('renders the colour key with the fill meanings', () => {
    render(<Legend />);
    expect(screen.getByText('凡例')).toBeInTheDocument();
    expect(screen.getByText('夜勤')).toBeInTheDocument();
    expect(screen.getByText('公休（休）')).toBeInTheDocument();
    expect(screen.getByText(/警告該当/)).toBeInTheDocument();
  });
});
