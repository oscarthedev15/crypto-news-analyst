import React from "react";
import "./SourceCard.css";

function SourceCard({ article, index, similarity_score, compact = false }) {
  const formatDate = (dateString) => {
    if (!dateString) return "Unknown";
    const date = new Date(dateString);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
    }).format(date);
  };

  // Compact row layout
  if (compact) {
    return (
      <a
        href={article.url}
        target="_blank"
        rel="noopener noreferrer"
        className="source-card-compact"
      >
        <span className="source-badge-compact">[{index}]</span>
        <span className="source-title-compact">{article.title}</span>
        <span className="source-meta-compact">
          <span className="source-name-compact">{article.source}</span>
          <span className="source-separator">•</span>
          <span className="source-date-compact">
            {formatDate(article.published_date)}
          </span>
        </span>
      </a>
    );
  }

  // Original card layout (for future use if needed)
  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className="source-card"
    >
      <div className="source-card-content">
        <span className="source-badge">[{index}]</span>
        <span className="source-title">{article.title}</span>
        <span className="source-meta">
          <span className="source-name">{article.source}</span>
          <span className="source-separator">•</span>
          <span className="source-date">
            {formatDate(article.published_date)}
          </span>
        </span>
      </div>
    </a>
  );
}

export default SourceCard;
