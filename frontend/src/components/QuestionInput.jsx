import React, { useState, useRef, useEffect } from "react";
import "./QuestionInput.css";

function QuestionInput({ onSubmit, disabled, onClearChat }) {
  const [question, setQuestion] = useState("");
  const textareaRef = useRef(null);

  useEffect(() => {
    // Auto-resize textarea
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        textareaRef.current.scrollHeight + "px";
    }
  }, [question]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (question.trim() && !disabled) {
      onSubmit(question.trim());
      setQuestion("");
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="chat-input-container">
      <div className="chat-controls">
        <button
          type="button"
          className="clear-btn"
          onClick={onClearChat}
          disabled={disabled}
          title="Start new chat"
        >
          🗑️ Clear Chat
        </button>
      </div>

      <form onSubmit={handleSubmit} className="chat-input-form">
        <textarea
          ref={textareaRef}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about crypto news... (Enter to send, Shift+Enter for new line)"
          disabled={disabled}
          rows="1"
          maxLength={500}
        />
        <button
          type="submit"
          disabled={disabled || !question.trim()}
          className="send-btn"
          title="Send message"
        >
          {disabled ? "⏳" : "➤"}
        </button>
      </form>
    </div>
  );
}

export default QuestionInput;
