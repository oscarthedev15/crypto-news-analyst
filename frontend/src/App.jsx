import React, { useState, useEffect, useRef } from "react";
import { api } from "./services/api";
import "./App.css";
import QuestionInput from "./components/QuestionInput";
import ChatMessage from "./components/ChatMessage";
import IndexStats from "./components/IndexStats";

function App() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const messagesEndRef = useRef(null);
  const chatContainerRef = useRef(null);

  // Auto-scroll to bottom when new messages arrive
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmitQuestion = async (newQuestion, mode) => {
    // Add user message
    const userMessage = {
      id: Date.now(),
      role: "user",
      content: newQuestion,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setError("");
    setIsLoading(true);

    // Create assistant message placeholder
    const assistantMessageId = Date.now() + 1;
    const assistantMessage = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      sources: [],
      isStreaming: true,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, assistantMessage]);

    try {
      if (mode === "database") {
        await api.askQuestion(
          newQuestion,
          (sources) => {
            // Update assistant message with sources
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId ? { ...msg, sources } : msg
              )
            );
          },
          (chunk) => {
            // Append content chunks
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? { ...msg, content: msg.content + chunk }
                  : msg
              )
            );
          },
          () => {
            // Mark as complete
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? { ...msg, isStreaming: false }
                  : msg
              )
            );
            setIsLoading(false);
          },
          (errorMsg) => {
            setError(errorMsg);
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? {
                      ...msg,
                      content: `Error: ${errorMsg}`,
                      isStreaming: false,
                    }
                  : msg
              )
            );
            setIsLoading(false);
          }
        );
      } else if (mode === "websearch") {
        await api.askWebSearch(
          newQuestion,
          (chunk) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? { ...msg, content: msg.content + chunk }
                  : msg
              )
            );
          },
          () => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? { ...msg, isStreaming: false }
                  : msg
              )
            );
            setIsLoading(false);
          },
          (errorMsg) => {
            setError(errorMsg);
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantMessageId
                  ? {
                      ...msg,
                      content: `Error: ${errorMsg}`,
                      isStreaming: false,
                    }
                  : msg
              )
            );
            setIsLoading(false);
          }
        );
      }
    } catch (err) {
      setError(err.message);
      setIsLoading(false);
    }
  };

  const handleClearChat = async () => {
    if (
      window.confirm("Clear chat history? This will start a new conversation.")
    ) {
      await api.clearSession();
      setMessages([]);
      setError("");
    }
  };

  return (
    <div className="app">
      <header className="chat-header">
        <div className="header-content">
          <div className="header-title">
            <h1>🚀 Crypto News Agent</h1>
            <p className="subtitle">AI-powered crypto news assistant</p>
          </div>
          <IndexStats compact />
        </div>
      </header>

      <main className="chat-container" ref={chatContainerRef}>
        <div className="messages-wrapper">
          {messages.length === 0 && (
            <div className="welcome-screen">
              <div className="welcome-icon">💬</div>
              <h2>Welcome to Crypto News Agent</h2>
              <p>Ask me anything about cryptocurrency news!</p>

              <IndexStats />

              <div className="example-questions">
                <div className="example-label">Try asking:</div>
                <button
                  className="example-btn"
                  onClick={() =>
                    handleSubmitQuestion(
                      "What's the latest news about Bitcoin?",
                      "database"
                    )
                  }
                  disabled={isLoading}
                >
                  What's the latest news about Bitcoin?
                </button>
                <button
                  className="example-btn"
                  onClick={() =>
                    handleSubmitQuestion(
                      "Explain Ethereum Layer 2 solutions",
                      "database"
                    )
                  }
                  disabled={isLoading}
                >
                  Explain Ethereum Layer 2 solutions
                </button>
                <button
                  className="example-btn"
                  onClick={() =>
                    handleSubmitQuestion("What happened with FTX?", "database")
                  }
                  disabled={isLoading}
                >
                  What happened with FTX?
                </button>
              </div>
            </div>
          )}

          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}

          {error && (
            <div className="error-banner">
              <span className="error-icon">⚠️</span>
              <span>{error}</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </main>

      <footer className="chat-footer">
        <div className="footer-content">
          <QuestionInput
            onSubmit={handleSubmitQuestion}
            disabled={isLoading}
            defaultMode="database"
            onClearChat={handleClearChat}
          />
          <div className="footer-info">
            <span>Sources: CoinTelegraph • The Defiant • Decrypt</span>
            <span>•</span>
            <span>{messages.length / 2} messages in conversation</span>
            <span>•</span>
            <span>Session: {api.sessionId}</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
