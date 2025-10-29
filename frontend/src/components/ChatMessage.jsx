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
      .replace(/\n{3,}/g, "\n\n") // Replace 3+ line breaks with 2
      .replace(/^\s+|\s+$/g, "") // Trim leading/trailing whitespace
      .replace(/\n\s*\n\s*\n/g, "\n\n"); // Clean up multiple empty lines
  };

  // Extract cited article numbers from the response content
  const getCitedArticleNumbers = (text) => {
    if (!text) return new Set();

    // Match patterns like [Article 1], [Article 2], etc.
    const matches = text.match(/\[Article\s+(\d+)\]/gi);
    if (!matches) return new Set();

    return new Set(
      matches
        .map((match) => {
          const num = match.match(/\d+/);
          return num ? parseInt(num[0]) : null;
        })
        .filter((num) => num !== null)
    );
  };

  // Check if response indicates no information available
  const isNoInfoResponse = () => {
    if (!content) return false;

    const contentLower = content.toLowerCase().trim();
    const noInfoPatterns = [
      "i don't have information",
      "i don't have information about that",
      "couldn't find relevant articles",
      "no information available",
      "i don't have any information",
    ];

    const hasNoInfoPattern = noInfoPatterns.some((pattern) =>
      contentLower.includes(pattern)
    );

    // Also check if no citations are present
    const citedNumbers = getCitedArticleNumbers(content);
    const hasNoCitations = citedNumbers.size === 0;

    // Hide sources if it's a no-information response AND no citations
    return hasNoInfoPattern && hasNoCitations;
  };

  // Filter sources to only show those that are actually cited
  const getUsedSources = () => {
    // Don't show sources if response indicates no information
    if (isNoInfoResponse()) return [];

    if (!sources || sources.length === 0 || !content) return [];

    const citedNumbers = getCitedArticleNumbers(content);
    if (citedNumbers.size === 0) return []; // Don't show any sources if none are cited

    return sources
      .map((source, index) => ({ source, originalIndex: index + 1 }))
      .filter(({ originalIndex }) => citedNumbers.has(originalIndex))
      .sort(
        (a, b) =>
          (b.source.similarity_score || 0) - (a.source.similarity_score || 0)
      );
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

          {(() => {
            const usedSources = getUsedSources();
            return (
              usedSources.length > 0 &&
              !isStreaming && (
                <div className="message-sources">
                  <div className="sources-label">
                    📚 Sources ({usedSources.length})
                  </div>
                  <div className="sources-list-compact">
                    {usedSources.map(({ source, originalIndex }) => (
                      <SourceCard
                        key={source.id}
                        article={source}
                        index={originalIndex}
                        similarity_score={source.similarity_score}
                        compact={true}
                      />
                    ))}
                  </div>
                </div>
              )
            );
          })()}
        </div>
      </div>
    </div>
  );
};

export default ChatMessage;
