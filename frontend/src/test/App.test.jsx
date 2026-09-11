/**
 * App shell smoke tests — prove the root App component (restored route table)
 * mounts the intended page per route and enforces the auth gates.
 *
 * Auth is mocked at the axios layer: /auth/me resolves or 401s per test,
 * every other GET resolves empty so data-fetching pages render their shells.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import axios from 'axios';
import App from '../App';

vi.mock('axios');

// jsdom gaps touched by the shell (toaster/lazy/modal libs) — stub once.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((q) => ({
    matches: false,
    media: q,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}
if (!window.ResizeObserver) {
  window.ResizeObserver = vi.fn().mockImplementation(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  }));
}

const PLAYER = { id: 'u1', email: 'qa@example.com', role: 'user', credits: 0 };
const ADMIN = { id: 'a1', email: 'admin@example.com', role: 'admin', credits: 0 };

function mockAuth(user) {
  // LandingPage uses native fetch (not axios): never hit real network in tests.
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network disabled in tests')));
  axios.get.mockImplementation((url) => {
    const u = String(url);
    if (u.includes('/auth/me')) {
      return user ? Promise.resolve({ data: user }) : Promise.reject({ response: { status: 401 } });
    }
    if (u.includes('feature-flags')) {
      return Promise.resolve({ data: { redeem_tab_visible: true, withdraw_tab_visible: false } });
    }
    return Promise.resolve({ data: [] });
  });
  axios.post.mockResolvedValue({ data: {} });
}

function go(path) {
  window.history.pushState({}, '', path);
}

describe('App shell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    go('/');
  });

  it('redirects anonymous / to the landing page', async () => {
    mockAuth(null);
    render(<App />);
    expect(await screen.findByTestId('landing-page', {}, { timeout: 9000 })).toBeInTheDocument();
  }, 10000);

  it('renders the login page at /login for anonymous visitors', async () => {
    mockAuth(null);
    go('/login');
    render(<App />);
    expect(await screen.findByText('Welcome Back!', {}, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.getByText('Sign in to your account')).toBeInTheDocument();
  });

  it('renders the register page at /register', async () => {
    mockAuth(null);
    go('/register');
    render(<App />);
    expect(await screen.findByText('Create Account', {}, { timeout: 8000 })).toBeInTheDocument();
  });

  it('renders the player dashboard at / when authenticated', async () => {
    mockAuth(PLAYER);
    render(<App />);
    expect(await screen.findByTestId('tab-games', {}, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.getByTestId('tab-redeem')).toBeInTheDocument();
    expect(screen.getByTestId('tab-transactions')).toBeInTheDocument();
    expect(screen.getByTestId('tab-support')).toBeInTheDocument();
  });

  it('bounces non-admin players away from /admin', async () => {
    mockAuth(PLAYER);
    go('/admin');
    render(<App />);
    // Bounced to / (dashboard), never the admin panel.
    expect(await screen.findByTestId('tab-games', {}, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.queryByTestId('admin-tab-dailyops')).not.toBeInTheDocument();
  });

  it('renders the admin panel at /admin for admins', async () => {
    mockAuth(ADMIN);
    go('/admin');
    render(<App />);
    expect(await screen.findByTestId('admin-tab-dailyops', {}, { timeout: 8000 })).toBeInTheDocument();
  });
});
