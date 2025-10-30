/**
 * API Service for Crypto News Agent
 * Handles communication with backend API endpoints
 */

class CryptoNewsAPI {
  constructor(baseURL = "/api") {
    this.baseURL = baseURL;
    this.sessionId = this.getOrCreateSessionId();
  }

  /**
   * Get or create a session ID from sessionStorage (tab-specific)
   * @returns {string} Session ID
   */
  getOrCreateSessionId() {
    let sessionId = sessionStorage.getItem("crypto_news_session_id");
    if (!sessionId) {
      sessionId = this.generateSessionId();
      sessionStorage.setItem("crypto_news_session_id", sessionId);
    }
    return sessionId;
  }

  /**
   * Generate a new session ID
   * @returns {string} New session ID
   */
  generateSessionId() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Clear current session and create new one
   */
  async clearSession() {
    try {
      // Delete session on server
      await fetch(`${this.baseURL}/session/${this.sessionId}`, {
        method: "DELETE",
      });
    } catch (error) {
      console.error("Error clearing session:", error);
    }

    // Create new session
    this.sessionId = this.generateSessionId();
    sessionStorage.setItem("crypto_news_session_id", this.sessionId);
  }

  /**
   * Parse SSE (Server-Sent Events) formatted response
   * @param {string} eventString - The event string to parse
   * @returns {object|null} Parsed JSON or null
   */
  parseSSEEvent(eventString) {
    if (!eventString.startsWith("data: ")) {
      return null;
    }

    const jsonStr = eventString.slice(6); // Remove 'data: ' prefix
    try {
      return JSON.parse(jsonStr);
    } catch (e) {
      return null;
    }
  }

  /**
   * Ask a question to the semantic search endpoint with session support
   * @param {string} question - The question to ask
   * @param {function} onSources - Callback when sources are received
   * @param {function} onChunk - Callback for each text chunk
   * @param {function} onComplete - Callback when streaming completes
   * @param {function} onError - Callback on error
   * @param {object} options - Additional options (top_k)
   */
  async askQuestion(
    question,
    onSources,
    onChunk,
    onComplete,
    onError,
    options = {}
  ) {
    const { top_k = 5 } = options;

    try {
      const response = await fetch(`${this.baseURL}/ask?top_k=${top_k}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Session-Id": this.sessionId,
        },
        body: JSON.stringify({ question }),
      });

      if (!response.ok) {
        let errorMessage = "Failed to process question";
        try {
          const error = await response.json();
          // Handle Pydantic validation errors
          if (error.detail) {
            if (Array.isArray(error.detail)) {
              // Pydantic validation error format
              const firstError = error.detail[0];
              if (firstError.msg) {
                errorMessage = firstError.msg;
              } else {
                errorMessage = error.detail;
              }
            } else if (typeof error.detail === "string") {
              errorMessage = error.detail;
            }
          }
        } catch (e) {
          // If JSON parsing fails, use default message
          errorMessage = `Request failed with status ${response.status}`;
        }
        onError(errorMessage);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");

        // Keep the last incomplete event in the buffer
        buffer = events.pop() || "";

        for (const event of events) {
          if (!event.trim()) continue;

          const data = this.parseSSEEvent(event);
          if (!data) continue;

          if (data.sources) {
            onSources(data.sources);
          } else if (data.content) {
            onChunk(data.content);
          } else if (data.error) {
            onError(data.error);
            break;
          }
        }
      }

      onComplete();
    } catch (error) {
      onError(error.message || "Network error");
    }
  }

  /**
   * Get index statistics
   * @returns {Promise<object>} Index statistics
   */
  async getIndexStats() {
    try {
      const response = await fetch(`${this.baseURL}/index-stats`);
      if (!response.ok) throw new Error("Failed to fetch index stats");
      return await response.json();
    } catch (error) {
      console.error("Error fetching index stats:", error);
      return null;
    }
  }

  /**
   * Health check
   * @returns {Promise<object>} Health status
   */
  async healthCheck() {
    try {
      const response = await fetch(`${this.baseURL}/health`);
      return await response.json();
    } catch (error) {
      console.error("Health check failed:", error);
      return { status: "unhealthy" };
    }
  }

  /**
   * Get news sources
   * @returns {Promise<object>} News sources information
   */
  async getSources() {
    try {
      const response = await fetch(`${this.baseURL}/sources`);
      if (!response.ok) throw new Error("Failed to fetch sources");
      return await response.json();
    } catch (error) {
      console.error("Error fetching sources:", error);
      return { sources: [] };
    }
  }
}

export const api = new CryptoNewsAPI();
