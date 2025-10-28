import logging
import re
from typing import Tuple
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)

class ModerationService:
    """Service for moderating user input using OpenAI's moderation API"""
    
    # Basic blocklist - add more as needed
    OFFENSIVE_KEYWORDS = {
        "hate", "violence", "abuse", "spam", "scam",
        "porn", "illegal", "bomb", "kill", "destroy"
    }
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
    
    def is_safe(self, text: str) -> Tuple[bool, str]:
        """Check if text is safe for processing
        
        Args:
            text: Text to check
            
        Returns:
            Tuple of (is_safe: bool, reason: str)
        """
        if not text:
            return False, "Question cannot be empty"
        
        # Length validation
        if len(text) < 5:
            return False, "Question must be at least 5 characters long"
        
        if len(text) > 500:
            return False, "Question must not exceed 500 characters"
        
        # Check for spam (excessive repeated characters)
        if self._has_spam_pattern(text):
            return False, "Question contains spam patterns"
        
        # Use OpenAI's moderation API for comprehensive content filtering
        try:
            response = self.client.moderations.create(input=text)
            
            # Check if any categories are flagged
            if response.results[0].flagged:
                categories = response.results[0].categories
                reasons = []
                
                if categories.harassment:
                    reasons.append("harassment")
                if categories.harassment_threatening:
                    reasons.append("threatening harassment")
                if categories.hate:
                    reasons.append("hate")
                if categories.hate_threatening:
                    reasons.append("threatening hate")
                if categories.self_harm:
                    reasons.append("self-harm")
                if categories.self_harm_intent:
                    reasons.append("self-harm intent")
                if categories.sexual:
                    reasons.append("sexual content")
                if categories.sexual_minors:
                    reasons.append("sexual content involving minors")
                if categories.violence:
                    reasons.append("violence")
                if categories.violence_graphic:
                    reasons.append("graphic violence")
                
                reason_str = ", ".join(reasons)
                logger.warning(f"Moderation flagged: {text[:50]}... Reasons: {reason_str}")
                return False, f"Question contains inappropriate content: {reason_str}"
        
        except Exception as e:
            # If moderation API fails, fall back to keyword filtering
            logger.error(f"Moderation API error: {e}")
            text_lower = text.lower()
            for keyword in self.OFFENSIVE_KEYWORDS:
                if keyword in text_lower:
                    return False, f"Question contains inappropriate content"
        
        return True, ""
    
    def _has_spam_pattern(self, text: str) -> bool:
        """Check for spam patterns like repeated characters
        
        Args:
            text: Text to check
            
        Returns:
            True if spam pattern detected
        """
        # Check for 10+ repeated identical characters
        if re.search(r'(.)\1{9,}', text):
            return True
        
        # Check for excessive special characters
        special_char_ratio = sum(1 for c in text if not c.isalnum() and c.isascii()) / len(text)
        if special_char_ratio > 0.5:
            return True
        
        return False


# Singleton instance
_moderation_service = None

def get_moderation_service() -> ModerationService:
    """Get or create the moderation service singleton"""
    global _moderation_service
    if _moderation_service is None:
        _moderation_service = ModerationService()
    return _moderation_service
