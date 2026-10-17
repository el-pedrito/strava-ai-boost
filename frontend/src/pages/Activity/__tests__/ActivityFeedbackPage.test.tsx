import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ApiError } from '@/api/client';
import type { ActivityFeedbackStatus, ActivityFeedbackBody } from '@/api/client';
import { ActivityFeedbackPage, SUMMARY_MAX_LENGTH } from '../ActivityFeedbackPage';

const getFeedbackMock = vi.hoisted(() => vi.fn<(id: string) => Promise<ActivityFeedbackStatus>>());
const submitFeedbackMock = vi.hoisted(() =>
  vi.fn<(id: string, body: ActivityFeedbackBody) => Promise<unknown>>(),
);

vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client');
  return {
    ...actual,
    getActivityFeedback: (id: string) => getFeedbackMock(id),
    submitActivityFeedback: (id: string, body: ActivityFeedbackBody) => submitFeedbackMock(id, body),
  };
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/activities/:id/feedback" element={<ActivityFeedbackPage />} />
        <Route path="/activities/:id" element={<p>activity detail</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function openForm() {
  getFeedbackMock.mockResolvedValue({ state: 'awaiting', deadline_at: '2026-10-17T19:00:00Z' });
  renderAt('/activities/123/feedback');
  return screen.findByRole('button', { name: 'Send' });
}

describe('ActivityFeedbackPage', () => {
  beforeEach(() => {
    getFeedbackMock.mockReset();
    submitFeedbackMock.mockReset();
  });

  it('reads the window state for the activity in the URL', async () => {
    await openForm();
    expect(getFeedbackMock).toHaveBeenCalledWith('123');
  });

  it('shows ten RPE buttons with aria-pressed and a labelled summary field', async () => {
    await openForm();
    for (let value = 1; value <= 10; value += 1) {
      const button = screen.getByRole('button', { name: `RPE ${value} out of 10` });
      expect(button).toHaveAttribute('aria-pressed', 'false');
    }
    const textarea = screen.getByLabelText('Summary (optional)');
    expect(textarea.tagName).toBe('TEXTAREA');
    expect(textarea).toHaveAttribute('maxLength', String(SUMMARY_MAX_LENGTH));
  });

  it('keeps Send disabled until an RPE is picked, then marks it pressed', async () => {
    const send = await openForm();
    expect(send).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'RPE 7 out of 10' }));
    expect(screen.getByRole('button', { name: 'RPE 7 out of 10' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'RPE 6 out of 10' })).toHaveAttribute('aria-pressed', 'false');
    expect(send).toBeEnabled();
  });

  it('posts the RPE and trimmed summary, then confirms on 202', async () => {
    submitFeedbackMock.mockResolvedValue({ accepted: true });
    const send = await openForm();
    await userEvent.click(screen.getByRole('button', { name: 'RPE 8 out of 10' }));
    await userEvent.type(screen.getByLabelText('Summary (optional)'), '  legs heavy  ');
    await userEvent.click(send);
    expect(submitFeedbackMock).toHaveBeenCalledWith('123', { rpe: 8, summary: 'legs heavy' });
    expect(await screen.findByText("Thanks, it's sent.")).toBeInTheDocument();
  });

  it('omits an empty summary from the body', async () => {
    submitFeedbackMock.mockResolvedValue({});
    const send = await openForm();
    await userEvent.click(screen.getByRole('button', { name: 'RPE 3 out of 10' }));
    await userEvent.type(screen.getByLabelText('Summary (optional)'), '   ');
    await userEvent.click(send);
    expect(submitFeedbackMock).toHaveBeenCalledWith('123', { rpe: 3 });
  });

  it('caps the summary at 2000 characters', async () => {
    await openForm();
    const textarea = screen.getByLabelText('Summary (optional)') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'a'.repeat(2500) } });
    expect(textarea.value).toHaveLength(SUMMARY_MAX_LENGTH);
    expect(screen.getByText('2000 / 2000')).toBeInTheDocument();
  });

  it('shows "already processed" when the window is not awaiting', async () => {
    getFeedbackMock.mockResolvedValue({ state: 'closed' });
    renderAt('/activities/123/feedback');
    expect(await screen.findByText(/Already processed/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeInTheDocument();
  });

  it('shows "already processed" for a submitted input too', async () => {
    getFeedbackMock.mockResolvedValue({ state: 'submitted' });
    renderAt('/activities/123/feedback');
    expect(await screen.findByText(/Already processed/)).toBeInTheDocument();
  });

  it('shows "already processed" for an activity without a window', async () => {
    getFeedbackMock.mockResolvedValue({ state: 'none' });
    renderAt('/activities/123/feedback');
    expect(await screen.findByText(/Already processed/)).toBeInTheDocument();
  });

  it('switches to "already processed" on a 409', async () => {
    submitFeedbackMock.mockRejectedValue(new ApiError('closed', 409));
    const send = await openForm();
    await userEvent.click(screen.getByRole('button', { name: 'RPE 5 out of 10' }));
    await userEvent.click(send);
    expect(await screen.findByText(/Already processed/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeInTheDocument();
  });

  it('keeps the form with an error on a 400', async () => {
    submitFeedbackMock.mockRejectedValue(new ApiError('bad', 400));
    const send = await openForm();
    await userEvent.click(screen.getByRole('button', { name: 'RPE 5 out of 10' }));
    await userEvent.click(send);
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid input');
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
  });

  it('shows a retryable error on a network failure', async () => {
    submitFeedbackMock.mockRejectedValue(new Error('offline'));
    const send = await openForm();
    await userEvent.click(screen.getByRole('button', { name: 'RPE 5 out of 10' }));
    await userEvent.click(send);
    expect(await screen.findByRole('alert')).toHaveTextContent('Sending failed');
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });

  it('shows the unavailable message when the GET fails', async () => {
    getFeedbackMock.mockRejectedValue(new ApiError('forbidden', 403));
    renderAt('/activities/123/feedback');
    expect(await screen.findByText(/Could not open the feedback/)).toBeInTheDocument();
  });

  it('never calls the API for a non-numeric activity id', async () => {
    renderAt('/activities/abc/feedback');
    expect(await screen.findByText(/Could not open the feedback/)).toBeInTheDocument();
    await waitFor(() => expect(getFeedbackMock).not.toHaveBeenCalled());
  });

  it('links back to the activity after sending', async () => {
    submitFeedbackMock.mockResolvedValue({});
    const send = await openForm();
    await userEvent.click(screen.getByRole('button', { name: 'RPE 9 out of 10' }));
    await userEvent.click(send);
    await userEvent.click(await screen.findByRole('button', { name: 'View activity' }));
    expect(await screen.findByText('activity detail')).toBeInTheDocument();
  });
});
