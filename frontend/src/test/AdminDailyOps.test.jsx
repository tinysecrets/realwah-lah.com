import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import axios from 'axios';
import AdminDailyOps from '../components/AdminDailyOps';

vi.mock('axios');

beforeEach(() => { vi.clearAllMocks(); });

describe('AdminDailyOps', () => {
  it('reconciles a Cash App deposit and shows the split', async () => {
    axios.post.mockResolvedValueOnce({ data: {
      ok: true, duplicate: false, gross_usd: 25, fee_usd: 3, net_usd: 22,
      pool_transfer_status: 'queued_manual',
    } });
    render(<AdminDailyOps />);
    fireEvent.change(screen.getByTestId('reconcile-email'), { target: { value: 'p@x.com' } });
    fireEvent.change(screen.getByTestId('reconcile-amount'), { target: { value: '25' } });
    fireEvent.change(screen.getByTestId('reconcile-receipt'), { target: { value: 'CA-9' } });
    fireEvent.click(screen.getByTestId('reconcile-submit'));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/admin/cashtag/reconcile'),
      expect.objectContaining({ user_email: 'p@x.com', amount_usd: 25, receipt: 'CA-9', apply_fee: true }),
    ));
    await screen.findByTestId('reconcile-result');
    expect(screen.getByTestId('reconcile-result')).toHaveTextContent('$22.00');
  });

  it('works the distributor queue: confirm-sent with a note', async () => {
    axios.get.mockImplementation((url) => {
      if (String(url).includes('/summary')) return Promise.resolve({ data: { awaiting: 1, overdue: { count: 0 }, today: { tasks_done: 2 } } });
      if (String(url).includes('/settings')) return Promise.resolve({ data: { mode: 'manual' } });
      return Promise.resolve({ data: [{
        id: 'task-1', send_instruction: "Send $22.00 to 'sugarab123' on Fire Kirin",
        platform_amount: 22, user_email: 'p@x.com', created_at: new Date().toISOString(),
      }] });
    });
    axios.post.mockResolvedValueOnce({ data: { ok: true, message: 'confirmed' } });
    render(<AdminDailyOps />);
    fireEvent.click(screen.getByTestId('ops-view-distributor'));
    await screen.findByTestId('dist-task');
    fireEvent.change(screen.getByTestId('dist-note'), { target: { value: 'sent 21:05' } });
    fireEvent.click(screen.getByTestId('dist-confirm'));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/ext/distributor/queue/task-1/confirm-sent'),
      { note: 'sent 21:05' },
    ));
  });

  it('replies to a ticket thread', async () => {
    axios.get.mockResolvedValue({ data: [{
      ticket_id: 't1', subject: 'Missing credits', message: 'help', status: 'open',
      priority: 'high', user_email: 'p@x.com', source: 'genie',
      genie_reply: 'auto answer', responses: [], created_at: new Date().toISOString(),
    }] });
    axios.post.mockResolvedValue({ data: { ok: true } });
    render(<AdminDailyOps />);
    fireEvent.click(screen.getByTestId('ops-view-tickets'));
    await screen.findByTestId('ops-ticket');
    fireEvent.click(screen.getByTestId('ops-ticket-toggle'));
    fireEvent.change(screen.getByTestId('ops-ticket-reply'), { target: { value: 'Fixed!' } });
    fireEvent.click(screen.getByTestId('ops-ticket-send'));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/admin/analytics/support-tickets/t1/respond'),
      { message: 'Fixed!' },
    ));
  });
});
