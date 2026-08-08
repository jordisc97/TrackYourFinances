import { useEffect, useRef, useState, useTransition, type FormEvent } from "react";
import { api, type AdvisorActionResult, type AdvisorChatMessage } from "../api";

type ChatBubble = AdvisorChatMessage & { actions?: AdvisorActionResult[] };

const SUGGESTIONS = [
  "How am I doing this month?",
  "Where can I cut spending?",
  "Any unusual expenses?",
];

export function AdvisorChat({
  year,
  month,
  onMutated,
}: {
  year: number;
  month: number;
  onMutated: () => void;
}) {
  const [messages, setMessages] = useState<ChatBubble[]>([
    { role: "assistant", content: "Ask about your spending, savings goals, or tell me to recategorize transactions." },
  ]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [, startTransition] = useTransition();
  const scrollerRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, sending]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || sending) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const history = messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .slice(1)
      .map(({ role, content }) => ({ role, content }));
    startTransition(() => {
      setMessages((prev) => [...prev, { role: "user", content: message }]);
      setDraft("");
      setError("");
      setSending(true);
    });
    inputRef.current?.focus();
    const result = await api.advisorChat({ message, history, year, month }, controller.signal).catch((err: Error) => {
      if (err.name === "AbortError") return null;
      setError(err.message);
      setSending(false);
      return null;
    });
    if (!result) return;
    setMessages((prev) => [...prev, { role: "assistant", content: result.reply, actions: result.action_results }]);
    setSending(false);
    if (result.mutated) onMutated();
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void send(draft);
  }

  return (
    <div className="panel advisor-panel">
      <div className="advisor-head">
        <h2>Financial Advisor</h2>
        <p className="muted">DeepSeek · month summary + any-month recategorize</p>
      </div>
      <div className="advisor-suggestions">
        {SUGGESTIONS.map((hint) => (
          <button key={hint} type="button" className="secondary advisor-chip" disabled={sending} onClick={() => void send(hint)}>
            {hint}
          </button>
        ))}
      </div>
      <div className="advisor-scroller" ref={scrollerRef}>
        {messages.map((msg, index) => (
          <div key={`${msg.role}-${index}`} className={`advisor-bubble advisor-${msg.role}`}>
            <p>{msg.content}</p>
            {msg.actions?.filter((a) => a.count > 0).map((action, actionIndex) => (
              <span key={`${action.type}-${actionIndex}`} className="advisor-action-chip">
                Updated {action.count} → {action.category_name}
              </span>
            ))}
          </div>
        ))}
        {sending && <div className="advisor-bubble advisor-assistant advisor-pending"><p>Thinking…</p></div>}
      </div>
      {error && <p className="muted advisor-error">{error}</p>}
      <form className="advisor-compose" onSubmit={onSubmit}>
        <input
          ref={inputRef}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="e.g. Move Mercadona to Groceries"
          disabled={sending}
          autoComplete="off"
        />
        <button type="submit" disabled={sending || !draft.trim()}>{sending ? "…" : "Send"}</button>
      </form>
    </div>
  );
}
