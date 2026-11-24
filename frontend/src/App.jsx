import { useState, useRef, useEffect } from "react";
import "./App.css";

const API_URL =
  import.meta.env.VITE_API_URL ||
  "http://localhost:8000";

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [systemPrompt, setSystemPrompt] = useState(
    "You are a helpful assistant."
  );
  const [loading, setLoading] = useState(false);

  const [sessionId] = useState(
    () => `s-${crypto.randomUUID()}`
  );

  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, loading]);

  const sendMessage = async () => {
    const trimmedMessage = input.trim();

    if (!trimmedMessage || loading) {
      return;
    }

    const userMessage = {
      role: "user",
      content: trimmedMessage,
    };

    setMessages((current) => [
      ...current,
      userMessage,
    ]);

    setInput("");
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: "POST",

        headers: {
          "Content-Type": "application/json",
        },

        body: JSON.stringify({
          session_id: sessionId,
          message: trimmedMessage,
          system_prompt:
            systemPrompt.trim() || undefined,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Something went wrong."
        );
      }

      const assistantMessage = {
        role: "assistant",
        content: data.reply,
        metadata: data.metadata,
      };

      setMessages((current) => [
        ...current,
        assistantMessage,
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: "error",
          content:
            error.message ||
            "Unable to reach the server.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (event) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {
      event.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <div className="logo">L</div>

          <div>
            <h1>Lyftr AI</h1>
            <p>Resilient AI Assistant</p>
          </div>
        </div>

        <div className="status">
          <span className="status-dot"></span>
          Backend connected
        </div>
      </header>

      <main className="main">
        <aside className="sidebar">
          <div className="sidebar-section">
            <p className="sidebar-label">
              SESSION
            </p>

            <div className="session-id">
              {sessionId.slice(0, 18)}...
            </div>
          </div>

          <div className="sidebar-section">
            <label
              className="sidebar-label"
              htmlFor="system-prompt"
            >
              SYSTEM PROMPT
            </label>

            <textarea
              id="system-prompt"
              data-testid="system-prompt-input"
              className="system-prompt"
              value={systemPrompt}
              onChange={(event) =>
                setSystemPrompt(event.target.value)
              }
              placeholder="Set assistant behaviour..."
            />
          </div>

          <div className="sidebar-info">
            <p>Powered by</p>
            <strong>LiteLLM + Gemini</strong>

            <p className="sidebar-small">
              Automatic key failover and response
              caching enabled.
            </p>
          </div>
        </aside>

        <section className="chat-panel">
          <div className="messages">
            {messages.length === 0 && (
              <div className="welcome">
                <div className="welcome-icon">
                  ✦
                </div>

                <h2>How can I help?</h2>

                <p>
                  Start a conversation with the
                  resilient Lyftr AI assistant.
                </p>

                <div className="feature-row">
                  <span>⚡ Cached responses</span>
                  <span>↻ Automatic failover</span>
                  <span>◈ Token tracking</span>
                </div>
              </div>
            )}

            {messages.map((message, index) => (
              <div
                key={index}
                className={`message-row ${message.role}`}
              >
                {message.role === "user" && (
                  <div className="message user-message">
                    {message.content}
                  </div>
                )}

                {message.role === "assistant" && (
                  <div
                    className="assistant-wrapper"
                    data-testid="assistant-message"
                  >
                    <div className="assistant-header">
                      <div className="assistant-avatar">
                        L
                      </div>
                      <span>Lyftr AI</span>
                    </div>

                    <div className="message assistant-message">
                      {message.content}
                    </div>

                    <div className="metadata">
                      <div className="meta-item">
                        <span>Source</span>

                        <strong
                          data-testid="meta-source"
                        >
                          {
                            message.metadata
                              .resolution_source
                          }
                        </strong>
                      </div>

                      <div className="meta-item">
                        <span>Model</span>

                        <strong
                          data-testid="meta-model"
                        >
                          {message.metadata.model}
                        </strong>
                      </div>

                      <div className="meta-item">
                        <span>Latency</span>

                        <strong
                          data-testid="meta-latency"
                        >
                          {
                            message.metadata
                              .latency_ms
                          }{" "}
                          ms
                        </strong>
                      </div>

                      <div className="meta-item">
                        <span>Input</span>

                        <strong
                          data-testid="meta-input-tokens"
                        >
                          {
                            message.metadata
                              .input_tokens
                          }
                        </strong>
                      </div>

                      <div className="meta-item">
                        <span>Output</span>

                        <strong
                          data-testid="meta-output-tokens"
                        >
                          {
                            message.metadata
                              .output_tokens
                          }
                        </strong>
                      </div>
                    </div>
                  </div>
                )}

                {message.role === "error" && (
                  <div className="error-message">
                    <strong>Request failed</strong>
                    <p>{message.content}</p>
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="thinking">
                <span></span>
                <span></span>
                <span></span>
              </div>
            )}

            <div ref={bottomRef}></div>
          </div>

          <div className="composer-container">
            <div className="composer">
              <textarea
                data-testid="chat-input"
                value={input}
                onChange={(event) =>
                  setInput(event.target.value)
                }
                onKeyDown={handleKeyDown}
                placeholder="Message Lyftr AI..."
                rows="1"
              />

              <button
                data-testid="send-button"
                onClick={sendMessage}
                disabled={
                  loading || !input.trim()
                }
                aria-label="Send message"
              >
                ↑
              </button>
            </div>

            <p className="composer-hint">
              Press Enter to send · Shift + Enter
              for a new line
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;