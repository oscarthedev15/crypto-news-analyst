import React from "react";
import "./LoadingIndicator.css";

function LoadingIndicator() {
  return (
    <div className="loading-indicator">
      <div className="spinner"></div>
      <p>Getting answer...</p>
    </div>
  );
}

export default LoadingIndicator;
