import React from "react";
import ReactMarkdown from "react-markdown";
import "./ChatMessage.css";
import SourceCard from "./SourceCard";

const ChatMessage = ({ message }) => {
  const { role, content, sources, isStreaming } = message;

  // Clean up markdown content to remove excessive line breaks
  const cleanMarkdownContent = (text) => {
    if (!text) return text;
    
    // Remove excessive line breaks (more than 2 consecutive)
    return text
      .replace(/\n{3,}/g, '\n\n') // Replace 3+ line breaks with 2
      .replace(/^\s+|\s+$/g, '') // Trim leading/trailing whitespace
      .replace(/\n\s*\n\s*\n/g, '\n\n'); // Clean up multiple empty lines
  };

  return (
    <div className={`chat-message ${role}`}>
      <div className="message-wrapper">
        <div className="message-avatar">{role === "user" ? "👤" : "🤖"}</div>
        <div className="message-content">
          <div className="message-bubble">
            {role === "assistant" && content ? (
              <ReactMarkdown>{cleanMarkdownContent(content)}</ReactMarkdown>
            ) : (
              content || (isStreaming && "Thinking...")
            )}
            {isStreaming && <span className="typing-indicator">▊</span>}
          </div>

          {sources && sources.length > 0 && !isStreaming && (
            <div className="message-sources">
              <div className="sources-label">📚 Sources ({sources.length})</div>
              <div className="sources-list">
                {sources
                  .sort(
                    (a, b) =>
                      (b.similarity_score || 0) - (a.similarity_score || 0)
                  )
                  .map((source, index) => (
                    <SourceCard
                      key={source.id}
                      article={source}
                      index={index + 1}
                      similarity_score={source.similarity_score}
                    />
                  ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatMessage;
