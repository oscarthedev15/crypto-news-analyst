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
  // Supports multiple citation formats to catch all article references
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

    // Match "Article N" format (without brackets) - comprehensive patterns
    // Patterns like:
    // - "According to Article 1"
    // - "Article 1 from CoinTelegraph"
    // - "from Article 1"
    // - "Article 1", "Article 2", etc. (standalone)
    // - "Article 1 mentions", "Article 2 states", etc.
    const articlePatterns = [
      // Patterns before "Article N"
      /(?:According to|from|using|referring to|based on|per|as mentioned in|as stated in|as reported in|mentioned in|stated in|reported in|as per|according to|in|via)\s+Article\s+(\d+)/gi,
      // Patterns after "Article N"
      /Article\s+(\d+)\s+(?:from|according to|in|per|states|reports|mentions|says|notes|indicates|explains|describes|details|discusses)/gi,
      // Standalone "Article N" followed by punctuation, space, or end of sentence
      /Article\s+(\d+)(?:[\s.,;:!?]|$)/gi,
      // "Article N" at start of sentence or after period
      /(?:^|\.\s+)Article\s+(\d+)/gim,
    ];

    articlePatterns.forEach((pattern) => {
      try {
        const matches = text.matchAll(pattern);
        for (const match of matches) {
          const num = match[1];
          if (num) {
            citedNumbers.add(parseInt(num));
          }
        }
      } catch (e) {
        // Ignore regex errors
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
  // Show ALL sources that were retrieved (they were all used to generate the answer)
  const getCitedSources = () => {
    // Don't show sources if response indicates no information
    if (isNoInfoResponse()) return [];

    // Always show all sources if they exist (regardless of citation detection)
    if (!sources || sources.length === 0) return [];

    const citedNumbers = getCitedArticleNumbers(content || "");

    // Return all sources, sorting cited ones first
    return sources
      .map((source, index) => ({
        source,
        originalIndex: index + 1,
        isCited: citedNumbers.has(index + 1),
      }))
      .sort((a, b) => {
        // Cited sources first, then by similarity score
        if (a.isCited !== b.isCited) {
          return b.isCited - a.isCited;
        }
        return (
          (b.source.similarity_score || 0) - (a.source.similarity_score || 0)
        );
      });
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
