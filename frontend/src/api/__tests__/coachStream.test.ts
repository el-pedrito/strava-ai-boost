import { describe, it, expect } from 'vitest';
import { parseSseBuffer } from '../coachStream';

describe('parseSseBuffer', () => {
  it('parses complete AG-UI frames and keeps the remainder', () => {
    const buffer =
      'data: {"type":"RUN_STARTED","runId":"r1"}\n\n' +
      'data: {"type":"TEXT_MESSAGE_CONTENT","delta":"Salut"}\n\n' +
      'data: {"type":"TEXT_MESSAGE_CONTENT","delta":" champion"}';

    const [events, remainder] = parseSseBuffer(buffer);

    expect(events).toHaveLength(2);
    expect(events[0].type).toBe('RUN_STARTED');
    expect(events[1].delta).toBe('Salut');
    // The last (incomplete) frame is returned as remainder.
    expect(remainder).toContain('champion');
  });

  it('returns no events when buffer has no complete frame', () => {
    const [events, remainder] = parseSseBuffer('data: {"type":"RUN_ST');
    expect(events).toHaveLength(0);
    expect(remainder).toBe('data: {"type":"RUN_ST');
  });

  it('ignores malformed frames without throwing', () => {
    const buffer = 'data: not-json\n\ndata: {"type":"RUN_FINISHED","runId":"r1"}\n\n';
    const [events] = parseSseBuffer(buffer);
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe('RUN_FINISHED');
  });

  it('joins multi-line data fields', () => {
    const buffer = 'data: {"type":"TEXT_MESSAGE_CONTENT",\ndata: "delta":"x"}\n\n';
    const [events] = parseSseBuffer(buffer);
    expect(events[0].delta).toBe('x');
  });
});
