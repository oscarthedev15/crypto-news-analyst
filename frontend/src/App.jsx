import React, { useState, useEffect } from "react";
import { api } from "./services/api";
import "./App.css";
import QuestionInput from "./components/QuestionInput";
import StreamingResponse from "./components/StreamingResponse";
import IndexStats from "./components/IndexStats";
import LoadingIndicator from "./components/LoadingIndicator";

function App() {
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState("");
  const [sources, setSources] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [searchMode, setSearchMode] = useState("database");

  const handleSubmitQuestion = async (newQuestion, mode) => {
    setQuestion(newQuestion);
    setResponse("");
    setSources([]);
    setError("");
    setIsLoading(true);
    setSearchMode(mode);

    try {
      if (mode === "database") {
        await api.askQuestion(
          newQuestion,
          (sources) => setSources(sources),
          (chunk) => setResponse((prev) => prev + chunk),
          () => setIsLoading(false),
          (error) => {
            setError(error);
            setIsLoading(false);
          }
        );
      } else if (mode === "websearch") {
        await api.askWebSearch(
          newQuestion,
          (chunk) => setResponse((prev) => prev + chunk),
          () => setIsLoading(false),
          (error) => {
            setError(error);
            setIsLoading(false);
          }
        );
      }
    } catch (err) {
      setError(err.message);
      setIsLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div className="container">
          <h1>🚀 Crypto News Agent</h1>
          <p className="subtitle">
            AI-powered semantic search over cryptocurrency news
          </p>
        </div>
      </header>

      <main className="container">
        <IndexStats />

        {error && (
          <div className="error-message">
            <span className="error-icon">⚠️</span>
            <span>{error}</span>
          </div>
        )}

        <QuestionInput
          onSubmit={handleSubmitQuestion}
          disabled={isLoading}
          defaultMode="database"
        />

        {/* Show streaming response during loading OR after completion */}
        {(response || sources.length > 0) && (
          <StreamingResponse
            text={response}
            isStreaming={isLoading}
            sources={sources}
            mode={searchMode}
          />
        )}

        {!isLoading && !response && sources.length === 0 && !error && (
          <div className="empty-state">
            <div className="empty-icon">💭</div>
            <h2>Ask a question about crypto news</h2>
            <p>Choose between searching our database or searching the web</p>
          </div>
        )}
      </main>

      <footer className="footer">
        <p>Sources: CoinTelegraph • The Defiant • Decrypt</p>
      </footer>
    </div>
  );
}

export default App;
