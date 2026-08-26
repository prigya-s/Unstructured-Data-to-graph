import { FormEvent, useEffect, useRef, useState } from "react";

import { ChatStreamDone, createChatThread, sendChatMessageStream } from "../api/client";
import MarkdownText from "../components/MarkdownText";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: ChatStreamDone;
}

// Persists across page reloads and SPA navigation away-and-back, so the
// conversation survives a page revisit. The server only keeps thread state
// in-memory (see api/routers/chat.py), so a backend restart invalidates a
// stored thread_id - handleSubmit recovers from that by starting a fresh
// thread rather than losing the typed message.
const STORAGE_KEY = "kg-local-chat";

interface StoredChat {
  threadId: string;
  messages: ChatMessage[];
}

function loadStoredChat(): StoredChat | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredChat) : null;
  } catch {
    return null;
  }
}

function saveStoredChat(data: StoredChat) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    // Ignore storage errors (quota exceeded, private browsing, etc.) -
    // the conversation still works for the current page view.
  }
}

export default function Chat() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stored = loadStoredChat();
    if (stored) {
      setThreadId(stored.threadId);
      setMessages(stored.messages);
      return;
    }
    createChatThread()
      .then((res) => setThreadId(res.thread_id))
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (threadId) {
      saveStoredChat({ threadId, messages });
    }
  }, [threadId, messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const message = input.trim();
    if (!message || !threadId || pending) return;

    setMessages((prev) => [...prev, { role: "user", content: message }, { role: "assistant", content: "" }]);
    setInput("");
    setPending(true);
    setError(null);

    const appendDelta = (text: string) => {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, content: last.content + text };
        return next;
      });
    };
    const attachSources = (sources: ChatStreamDone) => {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { ...next[next.length - 1], sources };
        return next;
      });
    };
    const replaceWithError = (detail: string) => {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: "assistant", content: detail };
        return next;
      });
    };

    try {
      let activeThreadId = threadId;
      let done: ChatStreamDone;
      try {
        done = await sendChatMessageStream(activeThreadId, message, appendDelta);
      } catch (err) {
        if (err instanceof Error && err.message.includes("Unknown thread_id")) {
          const fresh = await createChatThread();
          activeThreadId = fresh.thread_id;
          setThreadId(activeThreadId);
          done = await sendChatMessageStream(activeThreadId, message, appendDelta);
        } else {
          throw err;
        }
      }
      attachSources(done);
    } catch (err) {
      replaceWithError(err instanceof Error ? err.message : String(err));
    } finally {
      setPending(false);
    }
  }

  async function handleNewConversation() {
    localStorage.removeItem(STORAGE_KEY);
    setMessages([]);
    setError(null);
    try {
      const res = await createChatThread();
      setThreadId(res.thread_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="page chat-page">
      <div className="page__header">
        <h1>Ask the Knowledge Graph</h1>
        <button type="button" onClick={handleNewConversation} disabled={pending}>
          New conversation
        </button>
      </div>
      <p className="muted">Answers are grounded only in the approved Production Graph.</p>

      <div className="chat-log">
        {messages.map((message, index) => {
          const isPendingPlaceholder = pending && index === messages.length - 1 && message.content === "";
          return (
            <div key={index} className={`chat-bubble chat-bubble--${message.role}`}>
              <div className="chat-bubble__content">
                {isPendingPlaceholder ? (
                  "Thinking..."
                ) : message.role === "assistant" ? (
                  <MarkdownText text={message.content} />
                ) : (
                  message.content
                )}
              </div>
              {message.sources && <SourcesExpander sources={message.sources} />}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      {error && <p className="error">{error}</p>}

      <form className="chat-input" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask a question about the knowledge graph..."
          disabled={!threadId || pending}
        />
        <button type="submit" disabled={!threadId || pending || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}

function SourcesExpander({ sources }: { sources: ChatStreamDone }) {
  const [open, setOpen] = useState(false);
  const hasSources =
    sources.citations.length > 0 || sources.entities.length > 0 || sources.graph_paths.length > 0;
  if (!hasSources) return null;

  return (
    <div className="sources">
      <button type="button" className="sources__toggle" onClick={() => setOpen((prev) => !prev)}>
        {open ? "Hide sources" : "Show sources"}
      </button>
      {open && (
        <div className="sources__content">
          {sources.entities.length > 0 && (
            <>
              <h4>Related entities</h4>
              <ul>
                {sources.entities.map((entity) => (
                  <li key={entity.entity_id}>
                    {entity.name} ({entity.entity_type})
                  </li>
                ))}
              </ul>
            </>
          )}
          {sources.graph_paths.length > 0 && (
            <>
              <h4>Relationships</h4>
              <ul>
                {sources.graph_paths.map((path, index) => (
                  <li key={index}>{path}</li>
                ))}
              </ul>
            </>
          )}
          {sources.next_steps.length > 0 && (
            <>
              <h4>Next steps</h4>
              <ul>
                {sources.next_steps.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ul>
            </>
          )}
          {sources.citations.length > 0 && (
            <>
              <h4>Source documents</h4>
              <ul>
                {[...new Set(sources.citations.map((citation) => citation.document_name))].map(
                  (name) => (
                    <li key={name}>{name}</li>
                  ),
                )}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
