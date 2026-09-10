import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import LandingPage from '../LandingPage';

const STATS = {
  players: 1284, paid_out_usd: 1070.5, payouts_count: 6,
  platforms: 7, updated_at: new Date().toISOString(),
};
const PAYOUTS = {
  count: 2,
  payouts: [
    { name: 'j***', amount_usd: 320.0, method: 'BTC', paid_at: new Date(Date.now() - 2 * 3600e3).toISOString() },
    { name: 'm***', amount_usd: 25.0, method: 'Amazon', paid_at: new Date(Date.now() - 26 * 3600e3).toISOString() },
  ],
};

const renderPage = () => render(
  <MemoryRouter><LandingPage /></MemoryRouter>,
);

beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('LandingPage proof sections', () => {
  it('renders live stats, ticker, ovations and the payout FAQ', async () => {
    global.fetch = vi.fn((url) => {
      if (String(url).includes('/payouts/recent')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(PAYOUTS) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(STATS) });
    });
    renderPage();

    await waitFor(() => expect(screen.getByTestId('stats-section')).toBeInTheDocument());
    expect(screen.getByText('Paid Out to Players')).toBeInTheDocument();
    expect(screen.getByTestId('ovation-ticker')).toBeInTheDocument();
    expect(screen.getByTestId('ovations-section')).toBeInTheDocument();
    expect(screen.getByTestId('ovation-card-0')).toHaveTextContent('$320.00');
    expect(screen.getByTestId('ovation-card-1')).toHaveTextContent('Amazon');
    expect(screen.getByText('Will I actually get paid?')).toBeInTheDocument();
  });

  it('shows the honest empty state when no payouts exist yet', async () => {
    global.fetch = vi.fn((url) => {
      if (String(url).includes('/payouts/recent')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ payouts: [], count: 0 }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ...STATS, paid_out_usd: 0, payouts_count: 0 }) });
    });
    renderPage();

    await waitFor(() => expect(screen.getByTestId('ovations-empty')).toBeInTheDocument());
    expect(screen.queryByTestId('ovation-ticker')).not.toBeInTheDocument();
    // Stats still show real zeros.
    expect(screen.getByTestId('stats-section')).toBeInTheDocument();
  });

  it('hides proof sections (never fakes them) when the API is down', async () => {
    global.fetch = vi.fn(() => Promise.reject(new Error('down')));
    const { container } = renderPage();

    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    // Give the rejection handlers a tick to flip state.
    await vi.waitFor(() => expect(screen.queryByTestId('stats-loading')).not.toBeInTheDocument());
    expect(screen.queryByTestId('stats-section')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ovations-section')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ovation-ticker')).not.toBeInTheDocument();
    // The rest of the gorgeous page still renders.
    expect(screen.getByTestId('hero-section')).toBeInTheDocument();
    expect(container.querySelector('[data-testid="games-section"]')).toBeInTheDocument();
  });
});
