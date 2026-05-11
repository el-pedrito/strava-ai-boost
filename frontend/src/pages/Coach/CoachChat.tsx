import { useState, useRef, useEffect } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Input from '@cloudscape-design/components/input';
import Button from '@cloudscape-design/components/button';
import Box from '@cloudscape-design/components/box';
import Spinner from '@cloudscape-design/components/spinner';
import { useTranslation } from 'react-i18next';
import { api } from '../../api/client.ts';
import { getConfig } from '../../config.ts';

interface Message {
  role: 'user' | 'coach';
  text: string;
  timestamp: string;
}

export function CoachChat() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<Message[]>(() => {
    try {
      const saved = localStorage.getItem('coach_chat_messages');
      return saved ? JSON.parse(saved) : [];
    } catch { return []; }
  });
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId] = useState(() => localStorage.getItem('coach_chat_session') || (() => { const id = `coach-chat-session-${crypto.randomUUID()}`; localStorage.setItem('coach_chat_session', id); return id; })());
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    localStorage.setItem('coach_chat_messages', JSON.stringify(messages.slice(-20)));
  }, [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const question = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text: question, timestamp: new Date().toLocaleTimeString() }]);
    setLoading(true);

    try {
      const userId = getConfig().defaultUserId;
      const res = await api.post<{ answer: string; session_id?: string }>('/coach/ask', { question, user_id: userId, session_id: sessionId });
      setMessages(prev => [...prev, { role: 'coach', text: res.answer, timestamp: new Date().toLocaleTimeString() }]);
    } catch {
      setMessages(prev => [...prev, { role: 'coach', text: t('coach.chat.error'), timestamp: new Date().toLocaleTimeString() }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container header={<Header variant="h2">{t('coach.chat.title')}</Header>}>
      <div style={{ maxHeight: '400px', overflowY: 'auto', marginBottom: '12px' }}>
        <SpaceBetween size="s">
          {messages.length === 0 && (
            <Box variant="p" color="text-body-secondary" textAlign="center">
              {t('coach.chat.placeholder')}
            </Box>
          )}
          {messages.map((msg, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <Box
                padding="s"
                variant="div"
              >
                <div style={{
                  background: msg.role === 'user' ? 'var(--color-background-status-info)' : 'var(--color-background-layout-toggle-default)',
                  padding: '8px 12px',
                  borderRadius: '8px',
                  maxWidth: '80%',
                }}>
                  <Box variant="small" color="text-body-secondary">{msg.role === 'user' ? 'Toi' : '🏃 Coach'} • {msg.timestamp}</Box>
                  <Box variant="p">{msg.text}</Box>
                </div>
              </Box>
            </div>
          ))}
          {loading && <Box textAlign="center"><Spinner /> {t('coach.chat.thinking')}</Box>}
          <div ref={bottomRef} />
        </SpaceBetween>
      </div>
      <div style={{ display: 'flex', gap: '8px' }}>
        <div style={{ flex: 1 }}>
          <Input
            value={input}
            onChange={({ detail }) => setInput(detail.value)}
            placeholder={t('coach.chat.inputPlaceholder')}
            onKeyDown={({ detail }) => { if (detail.key === 'Enter') sendMessage(); }}
            disabled={loading}
          />
        </div>
        <Button variant="primary" onClick={sendMessage} loading={loading} disabled={!input.trim()}>
          {t('coach.chat.send')}
        </Button>
      </div>
    </Container>
  );
}
