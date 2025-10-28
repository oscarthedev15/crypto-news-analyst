import React, { useState, useEffect } from "react";
import { api } from "../services/api";
import "./IndexStats.css";

function IndexStats({ compact = false }) {
  const [stats, setStats] = useState(null);
  const [isCollapsed, setIsCollapsed] = useState(compact);

  useEffect(() => {
    fetchStats();
    // Refresh every 60 seconds
    const interval = setInterval(fetchStats, 60000);
    return () => clearInterval(interval);
  }, []);

  const fetchStats = async () => {
    const data = await api.getIndexStats();
    if (data) {
      setStats(data);
    }
  };

  if (!stats) {
    return null;
  }

  const formatDate = (dateString) => {
    if (!dateString) return "Never";
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));

    if (diffMinutes < 1) return "Just now";
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffHours < 72) return `${Math.floor(diffHours / 24)}d ago`;

    return date.toLocaleDateString();
  };

  // Check if ingestion is stale (older than 2 hours for hourly cron job)
  const isStale =
    stats.last_refresh &&
    new Date() - new Date(stats.last_refresh) > 2 * 60 * 60 * 1000;

  // Compact mode - just show summary
  if (compact) {
    return (
      <div className="index-stats-compact">
        <span className="stats-icon">📊</span>
        <span className="stats-value">{stats.indexed_articles} articles</span>
        <span className="stats-separator">•</span>
        <span className="stats-time">{formatDate(stats.last_refresh)}</span>
      </div>
    );
  }

  return (
    <div className={`index-stats ${isCollapsed ? "collapsed" : ""}`}>
      <div
        className="stats-header"
        onClick={() => setIsCollapsed(!isCollapsed)}
      >
        <div className="stats-left">
          <span className="stats-icon">📊</span>
          <span className="stats-label">Database Status</span>
          {isStale && <span className="stale-warning">⚠️ Data is stale</span>}
        </div>
        <span className="toggle-icon">{isCollapsed ? "▸" : "▾"}</span>
      </div>

      {!isCollapsed && (
        <div className="stats-content">
          <div className="stats-grid">
            <div className="stat-item">
              <div className="stat-value">{stats.total_articles}</div>
              <div className="stat-label">Total Articles</div>
            </div>

            <div className="stat-item">
              <div className="stat-value">{stats.indexed_articles}</div>
              <div className="stat-label">Indexed</div>
            </div>

            {stats.articles_by_source &&
              Object.entries(stats.articles_by_source).map(
                ([source, count]) => (
                  <div key={source} className="stat-item">
                    <div className="stat-value">{count}</div>
                    <div className="stat-label">{source}</div>
                  </div>
                )
              )}
          </div>

          {stats.last_refresh && (
            <div className="stats-footer">
              Last ingested: <strong>{formatDate(stats.last_refresh)}</strong>
              {stats.last_scraped &&
                stats.last_scraped !== stats.last_refresh && (
                  <span className="stats-subtitle">
                    {" "}
                    (scraped: {formatDate(stats.last_scraped)})
                  </span>
                )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default IndexStats;
