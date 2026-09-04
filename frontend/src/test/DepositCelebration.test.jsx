import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DepositCelebration from '../components/DepositCelebration';

describe('DepositCelebration', () => {
  it('renders the celebration banner', () => {
    render(<DepositCelebration />);
    const node = screen.getByTestId('deposit-celebration');
    expect(node).toBeInTheDocument();
    expect(node).toHaveTextContent('WAH-LAH!');
  });

  it('calls onDone after the animation completes', () => {
    vi.useFakeTimers();
    const onDone = vi.fn();
    render(<DepositCelebration onDone={onDone} />);
    expect(onDone).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(2300); });
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it('unmounts itself once finished', () => {
    vi.useFakeTimers();
    render(<DepositCelebration onDone={() => {}} />);
    act(() => { vi.advanceTimersByTime(2300); });
    expect(screen.queryByTestId('deposit-celebration')).not.toBeInTheDocument();
  });

  it('responds to the user clicking the overlay area without crashing', async () => {
    const user = userEvent.setup();
    render(<DepositCelebration onDone={() => {}} />);
    await user.click(screen.getByTestId('deposit-celebration'));
    expect(screen.getByTestId('deposit-celebration')).toBeInTheDocument();
  });
});