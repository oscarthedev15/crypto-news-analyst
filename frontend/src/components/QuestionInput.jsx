import React, { useState } from "react";
import "./QuestionInput.css";

function QuestionInput({ onSubmit, disabled, defaultMode = "database" }) {
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState(defaultMode);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (question.trim()) {
      onSubmit(question.trim(), mode);
      setQuestion("");
    }
  };

  return (
    <div className="question-input">
      <form onSubmit={handleSubmit}>
        <div className="mode-selector">
          <label className="mode-option">
            <input
              type="radio"
              name="mode"
              value="database"
              checked={mode === "database"}
              onChange={(e) => setMode(e.target.value)}
              disabled={disabled}
            />
            <span className="mode-label">
              <span className="mode-icon">🗄️</span>
              Database Search
            </span>
            <span className="mode-desc">Search our indexed articles</span>
          </label>

          <label className="mode-option">
            <input
              type="radio"
              name="mode"
              value="websearch"
              checked={mode === "websearch"}
              onChange={(e) => setMode(e.target.value)}
              disabled={disabled}
            />
            <span className="mode-label">
              <span className="mode-icon">🌐</span>
              Web Search
            </span>
            <span className="mode-desc">Search the live internet</span>
          </label>
        </div>

        <div className="input-group">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.ctrlKey) {
                handleSubmit(e);
              }
            }}
            placeholder="Ask a question about cryptocurrency news... (e.g., 'What is the latest news about Bitcoin ETFs?')"
            disabled={disabled}
            rows="3"
          />
          <button
            type="submit"
            disabled={disabled || !question.trim()}
            className="submit-btn"
          >
            {disabled ? "Processing..." : "Ask Question"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default QuestionInput;
