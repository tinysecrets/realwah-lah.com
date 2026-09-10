import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import axios from 'axios';
import Concierge from '../components/Concierge';

vi.mock('axios');

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe('Concierge Genie cycle', () => {
  it('asks the Genie and renders the reply (escalation included)', async () => {
    axios.post.mockResolvedValueOnce({
      data: {
        session_id: 'sess-1', reply: 'Allow up to **24 hours** for review.',
        provider: 'cerebras', model: 'llama', escalated: false, ticket_id: null,
      },
    });
    axios.post.mockResolvedValueOnce({
      data: {
        session_id: 'sess-1', reply: 'A human will take it from here.',
        provider: 'cerebras', model: 'llama', escalated: true, ticket_id: 'tick-abc-123',
      },
    });
    axios.get.mockResolvedValue({ data: [] });
    render(<Concierge />);

    // Quick ask sends immediately.
    fireEvent.click(screen.getAllByTestId('genie-quick')[0]);
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/genie/chat'),
      expect.objectContaining({ message: "Where's my deposit?" }),
    ));
    await screen.findByText(/Allow up to/);
    expect(localStorage.getItem('wl_genie_session')).toBe('sess-1');

    // Typed follow-up in the same session, escalated to a human.
    fireEvent.change(screen.getByTestId('genie-input'), { target: { value: 'Still missing!' } });
    fireEvent.click(screen.getByTestId('genie-send'));
    await screen.findByTestId('genie-escalated');
    expect(axios.post).toHaveBeenLastCalledWith(
      expect.stringContaining('/genie/chat'),
      expect.objectContaining({ session_id: 'sess-1', message: 'Still missing!' }),
    );
  });

  it('shows the offline fallback when the Genie backend is down', async () => {
    axios.post.mockRejectedValueOnce({ response: { status: 503 } });
    render(<Concierge />);
    fireEvent.click(screen.getAllByTestId('genie-quick')[1]);
    await screen.findByText(/Genie is offline/);
  });

  it('lists tickets and opens the operator thread', async () => {
    axios.get.mockImplementation((url) => {
      if (String(url).endsWith('/user/support/tickets')) {
        return Promise.resolve({ data: [{
          ticket_id: 't1', subject: 'Missing credits', status: 'pending',
          priority: 'normal', created_at: new Date().toISOString(),
        }] });
      }
      return Promise.resolve({ data: {
        ticket_id: 't1', subject: 'Missing credits', message: 'my credits?',
        status: 'pending', responses: [{ by: 'boss@x.com', message: 'Credited!', at: new Date().toISOString() }],
      } });
    });
    render(<Concierge />);
    fireEvent.click(screen.getByTestId('concierge-view-tickets'));
    await screen.findByText('Missing credits');
    fireEvent.click(screen.getByTestId('ticket-toggle'));
    await screen.findByTestId('ticket-thread');
    expect(screen.getByText('Credited!')).toBeInTheDocument();
    expect(screen.getByText(/boss@x.com/)).toBeInTheDocument();
  });
});
