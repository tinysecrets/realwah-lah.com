/**
 * BossMode.jsx — the Wah-Lah Genie Sidekick console.
 * Admin-only. Chat with the Genie; he calls platform tools on the Boss's behalf.
 */
import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import DOMPurify from "dompurify";
import { useNavigate } from "react-router-dom";
import { Send, Mic, MicOff, Sparkles, RefreshCw, ArrowLeft, Wand2, Zap, Terminal } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const QUICK_ASKS = [
  { label: "Platform snapshot", prompt: "Give me a full platform snapshot right now." },
  { label: "Pending redemptions", prompt: "List every redemption waiting for my approval." },
  { label: "Pool health", prompt: "Show me distributor pool health and flag anything red." },
  { label: "Recent alerts", prompt: "Any admin alerts I should care about in the last 24h?" },
  { label: "What's deployed?", prompt: "What version is live right now and what env flags are set?" },
  { label: "Compliance status", prompt: "Summarize the compliance queue — OFAC, KYC, AML." },
];

const BossMode = () => {
  const nav = useNavigate();
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [listening, setListening] = useState(false);
  const [brain, setBrain] = useState(null);        // { provider, model } — which LLM just replied
  const [providers, setProviders] = useState([]);   // available providers list from backend
  const [chosenProvider, setChosenProvider] = useState(
    () => localStorage.getItem("wl_boss_provider") || ""
  );
  const [showSwitcher, setShowSwitcher] = useState(false);
  const endRef = useRef(null);
  const recognitionRef = useRef(null);

  // Persist the chosen provider across reloads
  useEffect(() => {
    if (chosenProvider) localStorage.setItem("wl_boss_provider", chosenProvider);
    else localStorage.removeItem("wl_boss_provider");
  }, [chosenProvider]);

  // Load available providers for the switcher
  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API}/boss/providers`);
        setProviders(data.providers || []);
        // If our stored chosen provider isn't enabled, fall back to backend default
        if (chosenProvider) {
          const p = (data.providers || []).find(x => x.id === chosenProvider);
          if (!p?.enabled) setChosenProvider("");
        }
      } catch (e) {
        // non-fatal — switcher just won't render
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Kick a fresh session on mount
  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.post(`${API}/boss/new-session`);
        setSessionId(data.session_id);
        setMessages([{
          role: "assistant",
          content: "**At your service, Boss.**\n\nI'm the Wah-Lah Genie. Ask, and I'll handle it — users, payouts, flags, pool, compliance, logs. Or hand me a mission and I'll build the plan.",
          tool_trace: [],
        }]);
      } catch (e) {
        setMessages([{ role: "assistant", content: "Couldn't open a session. Are you logged in as admin?", tool_trace: [] }]);
      }
    })();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Voice input — Web Speech API
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;
    const r = new SpeechRecognition();
    r.continuous = false;
    r.interimResults = false;
    r.lang = "en-US";
    r.onresult = (e) => {
      const text = e.results[0][0].transcript;
      setInput((prev) => (prev ? prev + " " + text : text));
    };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    recognitionRef.current = r;
  }, []);

  const toggleMic = () => {
    const r = recognitionRef.current;
    if (!r) return;
    if (listening) {
      r.stop();
      setListening(false);
    } else {
      try {
        r.start();
        setListening(true);
      } catch (err) {
        // SpeechRecognition throws "already started" if user double-taps;
        // log it for debugging and leave the state unchanged.
        console.warn("Mic start failed:", err?.message || err);
      }
    }
  };

  const send = async (overrideText) => {
    const text = (overrideText ?? input).trim();
    if (!text || sending) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setSending(true);
    try {
      const { data } = await axios.post(`${API}/boss/chat`, {
        session_id: sessionId,
        message: text,
        provider: chosenProvider || undefined,
      });
      if (data.session_id && !sessionId) setSessionId(data.session_id);
      if (data.provider) setBrain({ provider: data.provider, model: data.model });
      setMessages((m) => [...m, {
        role: "assistant",
        content: data.reply,
        tool_trace: data.tool_trace || [],
        provider: data.provider,
        model: data.model,
      }]);
    } catch (e) {
      setMessages((m) => [...m, {
        role: "assistant",
        content: "The Genie stumbled: " + (e.response?.data?.detail || e.message),
        tool_trace: [],
      }]);
    } finally {
      setSending(false);
    }
  };

  const newSession = async () => {
    try {
      const { data } = await axios.post(`${API}/boss/new-session`);
      setSessionId(data.session_id);
      setMessages([{
        role: "assistant",
        content: "**Clean slate, Boss.** What's the move?",
        tool_trace: [],
      }]);
    } catch (err) {
      // Don't break the UI if the session-reset fails; surface the reason.
      console.warn("Boss newSession failed:", err?.response?.data?.detail || err.message);
      setMessages((m) => [...m, {
        role: "assistant",
        content: "Couldn't start a fresh session — keeping the current one.",
        tool_trace: [],
      }]);
    }
  };

  const renderMarkdown = (text) => {
    // tiny markdown: **bold** + newlines
    const safe = (text || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const html = safe
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br/>");
    // DOMPurify strips any residual scripts/iframes/on* handlers as defense in depth,
    // in case an attacker crafts a prompt that manages to slip past the escape above.
    const sanitized = DOMPurify.sanitize(html, {
      ALLOWED_TAGS: ["strong", "em", "br", "code"],
      ALLOWED_ATTR: [],
    });
    return { __html: sanitized };
  };

  return (
    <div className="boss-mode-root" data-testid="boss-mode-root">
      <div className="boss-stars" aria-hidden="true" />
      <div className="boss-smoke" aria-hidden="true" />

      <header className="boss-header">
        <button
          className="boss-back"
          onClick={() => nav("/admin")}
          data-testid="boss-back-btn"
          title="Back to Admin"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="boss-title">
          <Wand2 size={22} className="boss-title-icon" />
          <div>
            <h1>Boss Mode</h1>
            <span>The Genie · at your command</span>
          </div>
        </div>
        {(brain || providers.length > 0) && (
          <div className="boss-brain-wrap" data-testid="boss-brain-wrap">
            <button
              type="button"
              className={`boss-brain-badge boss-brain-${(brain?.provider) || chosenProvider || "cerebras"}`}
              title="Click to switch the LLM powering Genie"
              onClick={() => setShowSwitcher(v => !v)}
              data-testid="boss-brain-badge"
            >
              <span className="boss-brain-dot" />
              <span className="boss-brain-label">
                {(() => {
                  const active = brain?.provider || chosenProvider
                    || providers.find(p => p.enabled)?.id;
                  if (active === "ollama")   return "🏠 Ollama · Local";
                  if (active === "venice")   return "🌊 Venice · Uncensored";
                  if (active === "cerebras") return "⚡ Cerebras · Fast";
                  return active || "Auto";
                })()}
              </span>
              <span className="boss-brain-model">{brain?.model || providers.find(p => p.id === (chosenProvider || providers.find(x => x.enabled)?.id))?.model || ""}</span>
              <span className="boss-brain-caret">▾</span>
            </button>
            {showSwitcher && (
              <div className="boss-switcher" data-testid="boss-switcher">
                <div className="boss-switcher-head">Switch brain</div>
                <button
                  type="button"
                  className={`boss-switcher-opt ${chosenProvider === "" ? "is-active" : ""}`}
                  onClick={() => { setChosenProvider(""); setShowSwitcher(false); }}
                  data-testid="boss-switcher-auto"
                >
                  <span className="boss-sw-emoji">✨</span>
                  <span className="boss-sw-label">Auto <em>(priority: Ollama → Venice → Cerebras)</em></span>
                </button>
                {providers.map(p => (
                  <button
                    key={p.id}
                    type="button"
                    disabled={!p.enabled}
                    className={`boss-switcher-opt ${chosenProvider === p.id ? "is-active" : ""} ${!p.enabled ? "is-disabled" : ""}`}
                    onClick={() => { setChosenProvider(p.id); setShowSwitcher(false); }}
                    data-testid={`boss-switcher-${p.id}`}
                  >
                    <span className="boss-sw-emoji">{p.emoji}</span>
                    <span className="boss-sw-label">
                      {p.label}
                      <em>{p.model}</em>
                    </span>
                    {!p.enabled && <span className="boss-sw-off">not configured</span>}
                  </button>
                ))}
                <div className="boss-switcher-foot">
                  Add a key in <code>/app/backend/.env</code> to enable new providers.
                </div>
              </div>
            )}
          </div>
        )}
        <button className="boss-new" onClick={newSession} data-testid="boss-new-session">
          <RefreshCw size={14} /> New mission
        </button>
      </header>

      <div className="boss-chat-wrap">
        <aside className="boss-genie-pane" aria-hidden="true">
          <img
            src="/mascots/genie_hero.png"
            alt=""
            className={`boss-genie-hero ${sending ? "is-working" : ""}`}
            onError={(e) => { e.target.style.display = "none"; }}
          />
          <div className="boss-status-ring" />
        </aside>

        <section className="boss-chat">
          <div className="boss-messages" data-testid="boss-messages">
            {messages.map((m, i) => (
              <div key={i} className={`boss-msg boss-msg-${m.role}`} data-testid={`boss-msg-${i}`}>
                {m.role === "assistant" && (
                  <div className="boss-avatar">
                    <Sparkles size={14} />
                  </div>
                )}
                <div className="boss-bubble">
                  <div
                    className="boss-bubble-text"
                    /* renderMarkdown() runs DOMPurify.sanitize() internally — see line 179.
                       Safe: LLM output is sanitized before injection. */
                    dangerouslySetInnerHTML={renderMarkdown(m.content)}
                  />
                  {m.tool_trace && m.tool_trace.length > 0 && (
                    <div className="boss-tools">
                      {m.tool_trace.map((t, j) => (
                        <div key={j} className="boss-tool-chip" title={JSON.stringify(t.args)}>
                          <Terminal size={12} />
                          <span>{t.tool}</span>
                          {t.result?.error
                            ? <span className="boss-tool-err">error</span>
                            : <span className="boss-tool-ok">✓</span>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <div className="boss-msg boss-msg-assistant">
                <div className="boss-avatar"><Sparkles size={14} /></div>
                <div className="boss-bubble">
                  <div className="boss-thinking">
                    <span /><span /><span />
                    <em>Genie is casting…</em>
                  </div>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <div className="boss-quick-asks">
            {QUICK_ASKS.map((q, i) => (
              <button
                key={i}
                onClick={() => send(q.prompt)}
                className="boss-quick-chip"
                disabled={sending}
                data-testid={`boss-quick-${i}`}
              >
                <Zap size={12} /> {q.label}
              </button>
            ))}
          </div>

          <form
            className="boss-input-row"
            onSubmit={(e) => { e.preventDefault(); send(); }}
          >
            <button
              type="button"
              className={`boss-mic ${listening ? "is-on" : ""}`}
              onClick={toggleMic}
              title={listening ? "Listening…" : "Voice input"}
              data-testid="boss-mic"
            >
              {listening ? <MicOff size={16} /> : <Mic size={16} />}
            </button>
            <input
              type="text"
              className="boss-input"
              placeholder={listening ? "Speak, Boss…" : "Give the Genie an order…"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={sending}
              data-testid="boss-input"
            />
            <button
              type="submit"
              className="boss-send"
              disabled={sending || !input.trim()}
              data-testid="boss-send"
            >
              <Send size={16} />
            </button>
          </form>
        </section>
      </div>
    </div>
  );
};

export default BossMode;
