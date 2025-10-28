import React, { useEffect, useRef } from "react";
import SourceCard from "./SourceCard";
import LoadingIndicator from "./LoadingIndicator";
import "./StreamingResponse.css";

function StreamingResponse({ text, isStreaming, sources, mode }) {
  const responseRef = useRef(null);

  // Auto-scroll to bottom as new content arrives
  useEffect(() => {
    if (responseRef.current) {
      responseRef.current.scrollTop = responseRef.current.scrollHeight;
    }
  }, [text]);

  return (
    <div className="streaming-response">
      {/* Mode indicator */}
      <div className="mode-indicator">
        <span className={`mode-badge ${mode}`}>
          {mode === "database" ? "🗄️ Database Search" : "🌐 Web Search"}
        </span>
      </div>

      {/* Response text - now shown FIRST */}
      <div className="response-section">
        <h3 className="response-title">💬 Response</h3>
        <div ref={responseRef} className="response-text">
          {text || (isStreaming ? <LoadingIndicator /> : "")}
        </div>
      </div>

      {/* Loading indicator during streaming */}
      {isStreaming && text && <LoadingIndicator />}

      {/* Sources (only for database mode) - now shown BELOW response */}
      {mode === "database" && sources.length > 0 && (
        <div className="sources-section-compact">
          <h3 className="sources-title-compact">📚 Sources</h3>
          <div className="sources-list-compact">
            {sources.map((source, idx) => (
              <SourceCard
                key={source.id}
                article={source}
                index={idx + 1}
                similarity_score={source.similarity_score}
                compact={true}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default StreamingResponse;
