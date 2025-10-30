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
  // Supports both [Article N] and Article N formats
  const getCitedArticleNumbers = (text) => {
    if (!text) return new Set();

    const citedNumbers = new Set();

    // Match [Article N] format (preferred format)
    const bracketMatches = text.match(/\[Article\s+(\d+)\]/gi);
    if (bracketMatches) {
      bracketMatches.forEach((match) => {
        const num = match.match(/\d+/);
        if (num) citedNumbers.add(parseInt(num[0]));
      });
    }

    // Match "Article N" format (without brackets) - look for various citation patterns
    // Patterns like:
    // - "According to Article 1"
    // - "Article 1 from CoinTelegraph"
    // - "from Article 1"
    const articlePatterns = [
      /(?:According to|from|using|referring to|based on|per)\s+Article\s+(\d+)/gi,
      /Article\s+(\d+)\s+(?:from|according to|in|per)/gi,
    ];

    articlePatterns.forEach((pattern) => {
      const matches = text.matchAll(pattern);
      for (const match of matches) {
        const num = match[1];
        if (num) {
          citedNumbers.add(parseInt(num));
        }
      }
    });

    return citedNumbers;
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
      "i don't have recent articles about",
      "couldn't find relevant articles in our database",
    ];

    return noInfoPatterns.some((pattern) => contentLower.includes(pattern));
  };

  // Get sources that are actually cited in the response
  const getCitedSources = () => {
    // Don't show sources if response indicates no information
    if (isNoInfoResponse()) return [];

    if (!sources || sources.length === 0 || !content) return [];

    const citedNumbers = getCitedArticleNumbers(content);

    // If no citations found, don't show sources
    if (citedNumbers.size === 0) return [];

    // Return only sources that are cited
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
            const citedSources = getCitedSources();
            return (
              citedSources.length > 0 &&
              !isStreaming && (
                <div className="message-sources">
                  <div className="sources-label">
                    📚 Sources ({citedSources.length})
                  </div>
                  <div className="sources-list-compact">
                    {citedSources.map(({ source, originalIndex }) => (
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
