import logging
import re
from typing import Tuple
from detoxify import Detoxify
from app.config import settings

logger = logging.getLogger(__name__)


class ModerationService:
    """Service for moderating user input using Detoxify and optionally OpenAI.
    
    Uses Detoxify by default (always active).
    If OpenAI API key is configured, also uses OpenAI moderation for additional coverage.
    Blocks content if either service flags it.
    """
    
    # Threshold for flagging content (0.0 to 1.0)
    # LOWER = MORE STRICT (blocks more content)
    # HIGHER = MORE LENIENT (blocks less content)
    # 0.3 = stricter moderation, 0.5 = moderate, 0.7 = lenient
    TOXICITY_THRESHOLD = 0.3
    
    # Map Detoxify categories to user-friendly reason names
    CATEGORY_NAMES = {
        'toxicity': 'inappropriate content',
        'severe_toxicity': 'severely inappropriate content',
        'obscene': 'obscene content',
        'threat': 'threatening language',
        'insult': 'insulting language',
        'identity_attack': 'identity-based attack'
    }
    
    def __init__(self):
        """Initialize the moderation service with Detoxify and optionally OpenAI."""
        # Always initialize Detoxify
        try:
            self.detoxify_model = Detoxify('original')
            logger.info("✅ Moderation: Detoxify model loaded successfully")
        except Exception as e:
            logger.error(f"❌ Moderation: Failed to initialize Detoxify: {e}")
            raise RuntimeError(f"Failed to initialize moderation service: {e}")
        
        # Optionally initialize OpenAI moderation if API key is available
        self.openai_client = None
        self.use_openai = False
        
        if settings.openai_api_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=settings.openai_api_key)
                self.use_openai = True
                logger.info("✅ Moderation: OpenAI Moderation API enabled (dual-layer protection)")
            except Exception as e:
                logger.warning(f"⚠️ Moderation: Could not initialize OpenAI client: {e}")
                logger.info("✅ Moderation: Using Detoxify only")
        else:
            logger.info("✅ Moderation: Using Detoxify only (OpenAI API key not configured)")
    
    def is_safe(self, text: str) -> Tuple[bool, str]:
        """Check if text is safe for processing.
        
        Args:
            text: Text to check
            
        Returns:
            Tuple of (is_safe: bool, reason: str)
            If not safe, reason contains explanation of why it was flagged.
        """
        # Basic validation
        if not text:
            return False, "Question cannot be empty"
        
        if len(text) < 5:
            return False, "Question must be at least 5 characters long"
        
        if len(text) > 500:
            return False, "Question must not exceed 500 characters"
        
        # Check for spam patterns
        if self._has_spam_pattern(text):
            return False, "Question contains spam patterns"
        
        # Collect flags from all moderation services
        all_flagged_reasons = []
        
        # 1. Run Detoxify toxicity detection (always active)
        try:
            detoxify_results = self.detoxify_model.predict(text)
            
            for category, score in detoxify_results.items():
                if score > self.TOXICITY_THRESHOLD:
                    reason_name = self.CATEGORY_NAMES.get(category, category)
                    all_flagged_reasons.append(reason_name)
            
        except Exception as e:
            logger.error(f"Error during Detoxify moderation check: {e}")
            # Fail open for Detoxify - continue to other checks
        
        # 2. Run OpenAI moderation (if configured)
        if self.use_openai and self.openai_client:
            try:
                response = self.openai_client.moderations.create(input=text)
                
                if response.results[0].flagged:
                    categories = response.results[0].categories
                    openai_reasons = []
                    
                    if categories.harassment:
                        openai_reasons.append("harassment")
                    if categories.harassment_threatening:
                        openai_reasons.append("threatening harassment")
                    if categories.hate:
                        openai_reasons.append("hate")
                    if categories.hate_threatening:
                        openai_reasons.append("threatening hate")
                    if categories.self_harm:
                        openai_reasons.append("self-harm")
                    if categories.self_harm_intent:
                        openai_reasons.append("self-harm intent")
                    if categories.sexual:
                        openai_reasons.append("sexual content")
                    if categories.sexual_minors:
                        openai_reasons.append("sexual content involving minors")
                    if categories.violence:
                        openai_reasons.append("violence")
                    if categories.violence_graphic:
                        openai_reasons.append("graphic violence")
                    
                    all_flagged_reasons.extend(openai_reasons)
                    
            except Exception as e:
                logger.warning(f"OpenAI moderation API error: {e}")
                # Continue - Detoxify results still apply
        
        # Block if any service flagged the content
        if all_flagged_reasons:
            # Remove duplicates while preserving order
            unique_reasons = []
            for reason in all_flagged_reasons:
                if reason not in unique_reasons:
                    unique_reasons.append(reason)
            
            reason_str = ", ".join(unique_reasons)
            logger.warning(f"Moderation flagged: {text[:50]}... Reasons: {reason_str}")
            return False, f"Question contains inappropriate content: {reason_str}"
        
        return True, ""
    
    def _has_spam_pattern(self, text: str) -> bool:
        """Check for spam patterns like repeated characters.
        
        Args:
            text: Text to check
            
        Returns:
            True if spam pattern detected
        """
        if not text:
            return False
        
        # Check for 10+ repeated identical characters
        if re.search(r'(.)\1{9,}', text):
            return True
        
        # Check for excessive special characters (more than 50% non-alphanumeric)
        if len(text) > 0:
            special_char_count = sum(
                1 for c in text 
                if not c.isalnum() and not c.isspace() and c.isascii()
            )
            special_char_ratio = special_char_count / len(text)
            if special_char_ratio > 0.5:
                return True
        
        return False


# Singleton instance
_moderation_service = None


def get_moderation_service() -> ModerationService:
    """Get or create the moderation service singleton.
    
    Returns:
        ModerationService instance
    """
    global _moderation_service
    if _moderation_service is None:
        _moderation_service = ModerationService()
    return _moderation_service
