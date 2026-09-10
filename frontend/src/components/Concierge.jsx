/**
 * Concierge.jsx — player support: Genie AI chat + ticket threads.
 * Chat talks to the player Genie backend (POST /api/genie/chat, Cerebras ->
 * OpenAI-compatible fallback). Nothing here touches Emergent or legacy paths.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Send, Sparkles, Plus, RefreshCw, ChevronDown, MessageCircle, Ticket,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "https://api.wah-lah.com";
const API = `${BACKEND_URL}/api`;
const SESSION_KEY = "wl_genie_session";

const QUICK_ASKS = [
  "Where's my deposit?",
  "How do cash-outs work?",
  "Why do I need KYC?",
  "What are free credits?",
];

const renderRich = (text) => {
  // Minimal rich text: **bold** + newlines. Escaped first — never raw HTML.
  const safe = String(text || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const html = safe
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br/>");
  return { __html: html };
};

const GenieChat = ({ onTicketCreated }) => {
  const [sessionId, setSessionId] = useState(() => localStorage.getItem(SESSION_KEY) || null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [genieDown, setGenieDown] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    if (sessionId) localStorage.setItem(SESSION_KEY, sessionId);
  }, [sessionId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  // Restore the conversation on mount.
  useEffect(() => {
    if (!sessionId) return;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/genie/history/${sessionId}`);
        setMessages((data.messages || []).map((m) => ({ role: m.role, content: m.content })));
      } catch {
        // Stale/foreign session — start clean rather than erroring.
        localStorage.removeItem(SESSION_KEY);
        setSessionId(null);
      }
    })();
  }, [sessionId]);

  const send = useCallback(async (overrideText) => {
    const text = (overrideText ?? input).trim();
    if (!text || sending) return;
    setInput("");
    setGenieDown(false);
    setMessages((m) => [...m, { role: "user", content: text }]);
    setSending(true);
    try {
      const { data } = await axios.post(`${API}/genie/chat`, {
        session_id: sessionId,
        message: text,
      });
      if (data.session_id) setSessionId(data.session_id);
      setMessages((m) => [...m, {
        role: "assistant",
        content: data.reply,
        escalated: data.escalated,
        ticket_id: data.ticket_id,
      }]);
      if (data.escalated && data.ticket_id) onTicketCreated?.();
    } catch (e) {
      if (e.response?.status === 503) {
        setGenieDown(true);
      } else {
        setMessages((m) => [...m, {
          role: "assistant",
          content: "The Genie stumbled for a moment — try again, or leave a ticket and a human will pick it up.",
        }]);
      }
    } finally {
      setSending(false);
    }
  }, [input, sending, sessionId, onTicketCreated]);

  const newChat = () => {
    localStorage.removeItem(SESSION_KEY);
    setSessionId(null);
    setMessages([]);
    setGenieDown(false);
  };

  return (
    <div className="concierge-chat" data-testid="genie-chat">
      <div className="concierge-messages" data-testid="genie-messages">
        {messages.length === 0 && !sending && (
          <div className="concierge-welcome">
            <Sparkles size={32} />
            <h3>Ask the Genie</h3>
            <p>Deposits, cash-outs, KYC, bonuses — answers instantly. Anything tricky gets handed to a human.</p>
            <div className="concierge-quicks">
              {QUICK_ASKS.map((q) => (
                <button key={q} type="button" className="chip-btn" data-testid="genie-quick"
                  onClick={() => send(q)} disabled={sending}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`concierge-msg concierge-msg-${m.role}`} data-testid={`genie-msg-${i}`}>
            {m.role === "assistant" && <div className="concierge-avatar"><Sparkles size={14} /></div>}
            <div className="concierge-bubble">
              <div dangerouslySetInnerHTML={renderRich(m.content)} />
              {m.escalated && (
                <div className="concierge-escalated" data-testid="genie-escalated">
                  A human was notified and will follow up on ticket {String(m.ticket_id || "").slice(0, 8)}…
                </div>
              )}
            </div>
          </div>
        ))}
        {sending && (
          <div className="concierge-msg concierge-msg-assistant">
            <div className="concierge-avatar"><Sparkles size={14} /></div>
            <div className="concierge-bubble"><span className="concierge-typing"><span /><span /><span /></span></div>
          </div>
        )}
        {genieDown && (
          <div className="concierge-msg concierge-msg-assistant">
            <div className="concierge-avatar"><Sparkles size={14} /></div>
            <div className="concierge-bubble">
              The Genie is offline right now — leave a ticket under <strong>My tickets</strong> and a human will answer.
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>
      <form className="concierge-input-row" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <button type="button" className="concierge-new" onClick={newChat} title="New conversation" data-testid="genie-new-chat">
          <RefreshCw size={15} />
        </button>
        <input
          type="text" className="concierge-input" data-testid="genie-input"
          placeholder="Ask about deposits, cash-outs, KYC…"
          value={input} onChange={(e) => setInput(e.target.value)} disabled={sending}
        />
        <button type="submit" className="concierge-send" data-testid="genie-send" disabled={sending || !input.trim()}>
          <Send size={16} />
        </button>
      </form>
    </div>
  );
};

const TicketsView = ({ refreshKey }) => {
  const [tickets, setTickets] = useState([]);
  const [openId, setOpenId] = useState(null);
  const [threads, setThreads] = useState({});
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [priority, setPriority] = useState("normal");
  const [isLoading, setIsLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);

  const fetchTickets = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/user/support/tickets`);
      setTickets(data);
    } catch {
      // Silent — the empty state covers it.
    }
  }, []);

  useEffect(() => { fetchTickets(); }, [fetchTickets, refreshKey]);

  const toggleThread = async (ticketId) => {
    if (openId === ticketId) { setOpenId(null); return; }
    setOpenId(ticketId);
    if (threads[ticketId]) return;
    try {
      const { data } = await axios.get(`${API}/user/support/tickets/${ticketId}`);
      setThreads((t) => ({ ...t, [ticketId]: data }));
    } catch {
      toast.error("Couldn't open that ticket");
      setOpenId(null);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      await axios.post(`${API}/user/support/ticket`, { subject, message, priority });
      toast.success("Ticket created! We'll respond soon.");
      setSubject(""); setMessage(""); setPriority("normal"); setShowForm(false);
      fetchTickets();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to create ticket");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="concierge-tickets" data-testid="concierge-tickets">
      <button type="button" className="btn-primary concierge-new-ticket" data-testid="ticket-new-btn"
        onClick={() => setShowForm((v) => !v)}>
        <Plus size={16} /> New ticket
      </button>

      {showForm && (
        <form className="concierge-ticket-form" data-testid="ticket-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Subject</label>
            <input value={subject} onChange={(e) => setSubject(e.target.value)} required
              placeholder="e.g. Deposit not showing" data-testid="ticket-subject" />
          </div>
          <div className="form-group">
            <label>Priority</label>
            <select value={priority} onChange={(e) => setPriority(e.target.value)} data-testid="ticket-priority">
              <option value="low">Low</option>
              <option value="normal">Normal</option>
              <option value="high">High</option>
            </select>
          </div>
          <div className="form-group">
            <label>Message</label>
            <textarea value={message} onChange={(e) => setMessage(e.target.value)} required rows={4}
              placeholder="What happened? Include amounts, dates, receipt numbers…" data-testid="ticket-message" />
          </div>
          <button type="submit" className="btn-primary" disabled={isLoading} data-testid="ticket-submit">
            {isLoading ? "Sending…" : "Send ticket"}
          </button>
        </form>
      )}

      {tickets.length === 0 ? (
        <div className="empty-state"><Ticket size={40} /><p>No tickets yet</p></div>
      ) : (
        <div className="transactions-list">
          {tickets.map((t) => {
            const thread = threads[t.ticket_id];
            const isOpen = openId === t.ticket_id;
            return (
              <div key={t.ticket_id} className="transaction-row concierge-ticket" data-testid="ticket-row">
                <div className="tx-details">
                  <button type="button" className="concierge-ticket-head" data-testid="ticket-toggle"
                    onClick={() => toggleThread(t.ticket_id)}>
                    <span className="tx-game">{t.subject}</span>
                    <ChevronDown size={16} className={isOpen ? "is-open" : ""} />
                  </button>
                  <span className="tx-date">{t.created_at ? new Date(t.created_at).toLocaleString() : ""}</span>
                  {isOpen && thread && (
                    <div className="concierge-thread" data-testid="ticket-thread">
                      <div className="concierge-thread-msg me"><p>{thread.message}</p><span>you</span></div>
                      {(thread.responses || []).map((r, i) => (
                        <div key={i} className="concierge-thread-msg them">
                          <p>{r.message}</p><span>{r.by} · {r.at ? new Date(r.at).toLocaleString() : ""}</span>
                        </div>
                      ))}
                      {(thread.responses || []).length === 0 && (
                        <div className="concierge-thread-empty">No reply yet — we answer every ticket.</div>
                      )}
                    </div>
                  )}
                </div>
                <div className="tx-side">
                  <span className={`badge tx-status-${t.status === "closed" ? "ok" : t.status === "open" ? "wait" : "wait"}`}>
                    {String(t.status || "").replace(/_/g, " ")}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

const Concierge = () => {
  const [view, setView] = useState("chat");
  const [ticketBump, setTicketBump] = useState(0);

  return (
    <div className="tab-content concierge-tab">
      <div className="section-header">
        <h2>Concierge</h2>
        <p>Instant answers from the Genie, humans one ticket away</p>
      </div>
      <div className="ledger-filters" data-testid="concierge-views">
        <button type="button" data-testid="concierge-view-chat"
          className={`chip-btn ${view === "chat" ? "active" : ""}`} onClick={() => setView("chat")}>
          <MessageCircle size={14} /> Ask the Genie
        </button>
        <button type="button" data-testid="concierge-view-tickets"
          className={`chip-btn ${view === "tickets" ? "active" : ""}`} onClick={() => setView("tickets")}>
          <Ticket size={14} /> My tickets
        </button>
      </div>
      {view === "chat"
        ? <GenieChat onTicketCreated={() => setTicketBump((n) => n + 1)} />
        : <TicketsView refreshKey={ticketBump} />}
    </div>
  );
};

export default Concierge;
