import React from "react";
import "./SourceCard.css";

function SourceCard({ article, index, similarity_score }) {
  const formatDate = (dateString) => {
    if (!dateString) return "Unknown date";
    const date = new Date(dateString);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(date);
  };

  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className="source-card"
    >
      <div className="source-badge">[{index}]</div>
      <h3 className="source-title">{article.title}</h3>
      <div className="source-meta">
        <span className="source-name">{article.source}</span>
        <span className="source-date">
          {formatDate(article.published_date)}
        </span>
      </div>
      {similarity_score !== undefined && (
        <div className="similarity-score">
          Relevance: {(similarity_score * 100).toFixed(0)}%
        </div>
      )}
      <div className="read-link">Read Article →</div>
    </a>
  );
}

export default SourceCard;
