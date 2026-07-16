import { useState, useRef, useEffect } from 'react';
import { SendHorizonal, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Input } from '@/ui';
import { cn } from '@/lib/cn';
import { api, getIdToken } from '../../api/client.ts';
import {
  isRuntimeStreamingEnabled,
  isStreamingEnabled,
  streamCoachAnswer,
  streamCoachAnswerRuntime,
  type CoachStreamRequest,
} from '../../api/coachStream.ts';
import { getConfig } from '../../config.ts';

/** Known agent tools → i18n key suffix for the "coach is working" indicator. */
const TOOL_ACTIVITY_KEYS = new Set([
  'query_activities',
  'get_campus_plan',
  'get_pace_zones',
  'get_intervals_metrics',
]);

function toolActivityKey(toolName?: string): string {
  if (toolName && TOOL_ACTIVITY_KEYS.has(toolName)) {
    return `coach.chat.toolActivity.${toolName}`;
  }
  return 'coach.chat.toolActivity.default';
}

interface Message {
  role: 'user' | 'coach';
  text: string;
  timestamp: string;
}

const SUGGESTION_KEYS: string[] = [
  'coach.chat.suggestion1',
  'coach.chat.suggestion2',
  'coach.chat.suggestion3',
  'coach.chat.suggestion4',
];

interface ChatHistoryEntry {
  role: 'user' | 'assistant';
  content: string;
}

interface AskResponse {
  answer: string;
  session_id?: string;
}

function getInitialMessages(): Message[] {
  try {
    const saved = localStorage.getItem('coach_chat_messages');
    return saved ? (JSON.parse(saved) as Message[]) : [];
  } catch {
    return [];
  }
}

function getOrCreateSessionId(): string {
  const existing = localStorage.getItem('coach_chat_session');
  // AgentCore Runtime requires runtimeSessionId >= 33 chars: regenerate legacy
  // short ids stored before this format (the buffered API tolerated them).
  if (existing && existing.length >= 33) return existing;
  const id = `coach-chat-session-${crypto.randomUUID()}`;
  localStorage.setItem('coach_chat_session', id);
  return id;
}

export function CoachChat() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<Message[]>(getInitialMessages);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [toolActivity, setToolActivity] = useState<string | null>(null);
  const [sessionId] = useState<string>(getOrCreateSessionId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    localStorage.setItem('coach_chat_messages', JSON.stringify(messages.slice(-20)));
  }, [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Buffered fallback: the original one-shot POST to /coach/ask.
  const sendBuffered = async (
    trimmed: string,
    userId: string,
    history: ChatHistoryEntry[],
  ) => {
    const res = await api.post<AskResponse>('/coach/ask', {
      question: trimmed,
      user_id: userId,
      session_id: sessionId,
      history,
    });
    setMessages((prev) => [
      ...prev,
      { role: 'coach', text: res.answer, timestamp: new Date().toLocaleTimeString() },
    ]);
  };

  const sendQuestion = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    setInput('');
    setMessages((prev) => [
      ...prev,
      { role: 'user', text: trimmed, timestamp: new Date().toLocaleTimeString() },
    ]);
    setLoading(true);

    const userId = getConfig().defaultUserId;
    const history: ChatHistoryEntry[] = messages.slice(-10).map((m) => ({
      role: m.role === 'user' ? 'user' : 'assistant',
      content: m.text,
    }));

    try {
      const idToken = getIdToken();
      const runtimeOn = isRuntimeStreamingEnabled();
      const legacyOn = isStreamingEnabled();
      if (idToken && (runtimeOn || legacyOn)) {
        // Streaming path: append a coach placeholder, fill it token-by-token.
        // Runtime path (coachRuntimeArn) takes precedence; legacy SigV4 otherwise.
        const startedAt = new Date().toLocaleTimeString();
        let streamed = '';
        setMessages((prev) => [...prev, { role: 'coach', text: '', timestamp: startedAt }]);
        const appendDelta = (delta: string) => {
          // First token arrived: hide the "coach is thinking / working" indicators.
          setStreaming(true);
          setToolActivity(null);
          streamed += delta;
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = { role: 'coach', text: streamed, timestamp: startedAt };
            return next;
          });
        };
        const streamRequest: CoachStreamRequest = {
          question: trimmed,
          user_id: userId,
          session_id: sessionId,
          history,
        };
        const streamFn = runtimeOn ? streamCoachAnswerRuntime : streamCoachAnswer;
        try {
          await streamFn(streamRequest, idToken, {
            onDelta: appendDelta,
            // Surface agent tool loops (Runtime path) so the UI shows progress
            // during the 3-8 s before the first token.
            onToolCallStart: (toolName) => setToolActivity(toolActivityKey(toolName)),
            onToolCallEnd: () => setToolActivity(null),
          });
          if (streamed) return;
          // Empty stream: drop the placeholder and fall through to buffered.
          setMessages((prev) => prev.slice(0, -1));
        } catch (streamErr) {
          // Streaming failed: surface the real cause, then fall back to buffered POST.
          console.error('[coach stream] failed, falling back to /coach/ask:', streamErr);
          setMessages((prev) => prev.slice(0, -1));
        } finally {
          setStreaming(false);
          setToolActivity(null);
        }
      }

      await sendBuffered(trimmed, userId, history);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'coach',
          text: t('coach.chat.error'),
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSuggestion = (suggestion: string) => {
    setInput(suggestion);
    void sendQuestion(suggestion);
  };

  return (
    <div className="flex flex-col h-[70vh]">
      <div className="mb-4 flex flex-col gap-1">
        <h2 className="text-xl font-semibold tracking-tight">
          {t('coach.chat.headerTitle')}
        </h2>
        <p className="text-sm text-muted-foreground">
          {t('coach.chat.headerSubtitle')}
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-1">
        {messages.length === 0 && !loading ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
              <span>{t('coach.chat.suggestionsHint')}</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {SUGGESTION_KEYS.map((key) => {
                const text = t(key);
                return (
                  <Card
                    key={key}
                    variant="flat"
                    padding="sm"
                    onClick={() => handleSuggestion(text)}
                    className="cursor-pointer hover:bg-muted transition-colors text-sm"
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handleSuggestion(text);
                      }
                    }}
                  >
                    {text}
                  </Card>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3 pb-2">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={cn(
                  'flex',
                  msg.role === 'user' ? 'justify-end' : 'justify-start'
                )}
              >
                <div
                  className={cn(
                    'max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed border',
                    msg.role === 'user'
                      ? 'bg-primary/10 border-primary/20 text-foreground'
                      : 'bg-surface border-border'
                  )}
                >
                  {msg.role === 'coach' ? (
                    <div className="text-xs text-muted-foreground mb-1 font-medium">
                      {t('coach.chat.coachLabel')}
                    </div>
                  ) : null}
                  <div className="whitespace-pre-wrap">{msg.text}</div>
                </div>
              </div>
            ))}
            {loading && !streaming ? (
              <div className="flex justify-start">
                <div className="rounded-2xl px-4 py-3 bg-surface border border-border">
                  <div className="text-xs text-muted-foreground mb-1 font-medium">
                    {t('coach.chat.coachLabel')}
                  </div>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <span>{toolActivity ? t(toolActivity) : t('coach.chat.thinkingShort')}</span>
                    <span className="inline-flex gap-1">
                      <span
                        className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse"
                        style={{ animationDelay: '0ms' }}
                      />
                      <span
                        className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse"
                        style={{ animationDelay: '150ms' }}
                      />
                      <span
                        className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse"
                        style={{ animationDelay: '300ms' }}
                      />
                    </span>
                  </div>
                </div>
              </div>
            ) : null}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="sticky bottom-0 mt-4 flex items-center gap-2 border-t border-border pt-3 bg-background">
        <Input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void sendQuestion(input);
            }
          }}
          placeholder={t('coach.chat.inputPlaceholder')}
          disabled={loading}
          className="flex-1"
        />
        <Button
          variant="primary"
          size="icon"
          onClick={() => void sendQuestion(input)}
          disabled={!input.trim() || loading}
          aria-label={t('coach.chat.send')}
        >
          <SendHorizonal className="h-5 w-5" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
