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

  // Extract cited article numbers from the response content with their order
  // Returns an array of article numbers in order of appearance
  const getCitedArticleNumbersInOrder = (text) => {
    if (!text) return [];

    // Track earliest position for each article number
    const articlePositions = new Map();

    // Helper to record match with earliest position
    const recordMatch = (num, position) => {
      const numInt = parseInt(num);
      if (numInt) {
        const currentPos = articlePositions.get(numInt);
        // Record the earliest position for this article number
        if (currentPos === undefined || position < currentPos) {
          articlePositions.set(numInt, position);
        }
      }
    };

    // Match [Article N] format (preferred format)
    try {
      const bracketPattern = /\[Article\s+(\d+)\]/gi;
      let match;
      while ((match = bracketPattern.exec(text)) !== null) {
        recordMatch(match[1], match.index);
      }
    } catch (e) {
      // Ignore regex errors
    }

    // Match "Article N" format (without brackets) - comprehensive patterns
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

    // Process all patterns and collect matches with positions
    articlePatterns.forEach((patternStr) => {
      try {
        // Create a new regex instance for each pattern to avoid state issues
        const pattern = new RegExp(patternStr.source, patternStr.flags);
        let match;
        while ((match = pattern.exec(text)) !== null) {
          recordMatch(match[1], match.index);
        }
      } catch (e) {
        // Ignore regex errors
      }
    });

    // Convert map to array, sort by position, and return just the numbers
    return Array.from(articlePositions.entries())
      .sort((a, b) => a[1] - b[1]) // Sort by position
      .map(([number]) => number); // Return just the article numbers
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

  // Get sources that are actually cited in the response, ordered by appearance
  // Only return sources that are explicitly cited in the response text
  const getCitedSources = () => {
    // Don't show sources if response indicates no information
    if (isNoInfoResponse()) return [];

    // No sources available
    if (!sources || sources.length === 0) return [];

    // Get cited article numbers in order of appearance
    const citedNumbersInOrder = getCitedArticleNumbersInOrder(content || "");

    // If no citations found, don't show any sources
    if (citedNumbersInOrder.length === 0) return [];

    // Map article numbers (1-indexed) to sources (0-indexed)
    const citedSources = citedNumbersInOrder
      .map((articleNum) => {
        // Article numbers are 1-indexed, sources array is 0-indexed
        const sourceIndex = articleNum - 1;
        if (sourceIndex >= 0 && sourceIndex < sources.length) {
          return {
            source: sources[sourceIndex],
            citationOrder: citedNumbersInOrder.indexOf(articleNum),
            articleNumber: articleNum,
          };
        }
        return null;
      })
      .filter((item) => item !== null); // Remove any null entries (invalid article numbers)

    // Return sources in citation order (already ordered by appearance in response)
    return citedSources;
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
                    {citedSources.map(({ source, articleNumber }) => (
                      <SourceCard
                        key={source.id}
                        article={source}
                        index={articleNumber}
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
