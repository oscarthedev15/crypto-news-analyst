import logging
import re
from typing import Tuple, Optional, Any, List
from transformers import pipeline
from app.config import settings

logger = logging.getLogger(__name__)


class ModerationService:
    """Service for moderating user input using transformers pipeline (unitary/toxic-bert) and optionally OpenAI.
    
    Uses unitary/toxic-bert by default (always active).
    If OpenAI API key is configured, also uses OpenAI moderation for additional coverage.
    Blocks content if either service flags it.
    """
    
    # Threshold for flagging content (0.0 to 1.0)
    # LOWER = MORE STRICT (blocks more content)
    # HIGHER = MORE LENIENT (blocks less content)
    # 0.5 = moderate threshold (requires 50%+ confidence for toxicity)
    TOXICITY_THRESHOLD: float = 0.5

    # Validation constraints
    MIN_QUESTION_LENGTH: int = 1  # Allow any non-empty question
    MAX_QUESTION_LENGTH: int = 500
    REPEATED_CHAR_LIMIT: int = 10  # 10 identical chars in a row
    SPECIAL_CHAR_RATIO_LIMIT: float = 0.5  # >50% non-alnum ASCII characters
    
    def __init__(self):
        """Initialize the moderation service with transformers pipeline and optionally OpenAI."""
        # Initialize transformers pipeline with toxic-bert model
        try:
            logger.info("Loading toxicity detection model (unitary/toxic-bert)...")
            self.classifier = pipeline(
                "text-classification",
                model="unitary/toxic-bert"
            )
            logger.info("✅ Moderation: transformers pipeline (unitary/toxic-bert) loaded successfully")
        except Exception as e:
            logger.error(f"❌ Moderation: Failed to initialize transformers pipeline: {e}")
            raise RuntimeError(f"Failed to initialize moderation service: {e}")
        
        # Optionally initialize OpenAI moderation if API key is available
        self.openai_client: Optional[Any] = None
        self.use_openai: bool = False
        
        if settings.openai_api_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=settings.openai_api_key)
                self.use_openai = True
                logger.info("✅ Moderation: OpenAI Moderation API enabled (dual-layer protection)")
            except Exception as e:
                logger.warning(f"⚠️ Moderation: Could not initialize OpenAI client: {e}")
                logger.info("✅ Moderation: Using transformers pipeline only")
        else:
            logger.info("✅ Moderation: Using transformers pipeline only (OpenAI API key not configured)")
    
    def is_safe(self, text: str) -> Tuple[bool, str]:
        """Check if text is safe for processing.
        
        Args:
            text: Text to check
            
        Returns:
            Tuple of (is_safe: bool, reason: str)
            If not safe, reason contains explanation of why it was flagged.
        """
        # Basic validation
        if not text or not text.strip():
            return False, "Question cannot be empty"
        
        if len(text) > self.MAX_QUESTION_LENGTH:
            return False, "Question must not exceed 500 characters"
        
        # Check for spam patterns
        if self._has_spam_pattern(text):
            return False, "Question contains spam patterns"
        
        # Collect flags from all moderation services
        all_flagged_reasons: List[str] = []

        # 1) Transformers pipeline (toxic-bert)
        all_flagged_reasons.extend(self._run_toxicity_check(text))

        # 2) OpenAI (if configured)
        if self.use_openai and self.openai_client:
            try:
                all_flagged_reasons.extend(self._run_openai_check(text))
            except Exception as e:
                logger.warning(f"OpenAI moderation API error: {e}")

        # Block if any service flagged the content
        if all_flagged_reasons:
            # Remove duplicates while preserving order
            unique_reasons: List[str] = []
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
        repeated_char_pattern = rf'(.)\1{{{self.REPEATED_CHAR_LIMIT - 1},}}'
        if re.search(repeated_char_pattern, text):
            return True
        
        # Check for excessive special characters (more than 50% non-alphanumeric)
        if len(text) > 0:
            special_char_count = sum(
                1 for c in text 
                if not c.isalnum() and not c.isspace() and c.isascii()
            )
            special_char_ratio = special_char_count / len(text)
            if special_char_ratio > self.SPECIAL_CHAR_RATIO_LIMIT:
                return True
        
        return False

    def _run_toxicity_check(self, text: str) -> List[str]:
        """Run toxicity check using transformers pipeline and return list of flagged reasons."""
        reasons: List[str] = []
        try:
            result = self.classifier(text)
            
            # Result format: [{"label": "toxic", "score": 0.95}] or list of dicts
            if isinstance(result, list):
                for item in result:
                    label = item.get("label", "").lower()
                    score = item.get("score", 0.0)
                    
                    # Check if toxic and exceeds threshold
                    if "toxic" in label and score > self.TOXICITY_THRESHOLD:
                        reasons.append("toxic content")
                    elif score > self.TOXICITY_THRESHOLD:
                        # Other labels that exceed threshold
                        reasons.append(f"inappropriate content ({label})")
            else:
                # Single result format
                label = result.get("label", "").lower()
                score = result.get("score", 0.0)
                if "toxic" in label and score > self.TOXICITY_THRESHOLD:
                    reasons.append("toxic content")
                elif score > self.TOXICITY_THRESHOLD:
                    reasons.append(f"inappropriate content ({label})")
                    
        except Exception as e:
            logger.error(f"Error during toxicity check: {e}", exc_info=True)
        return reasons

    def _run_openai_check(self, text: str) -> List[str]:
        """Run OpenAI moderation and return list of reason labels when flagged.
        Requires client to be initialized.
        """
        if not self.openai_client:
            return []

        response = self.openai_client.moderations.create(input=text)
        if not response.results or not response.results[0].flagged:
            return []

        categories = response.results[0].categories
        reasons: List[str] = []

        # Map OpenAI categories to human-friendly reasons
        if categories.harassment:
            reasons.append("harassment")
        if getattr(categories, 'harassment_threatening', False):
            reasons.append("threatening harassment")
        if categories.hate:
            reasons.append("hate")
        if getattr(categories, 'hate_threatening', False):
            reasons.append("threatening hate")
        if categories.self_harm:
            reasons.append("self-harm")
        if getattr(categories, 'self_harm_intent', False):
            reasons.append("self-harm intent")
        if categories.sexual:
            reasons.append("sexual content")
        if getattr(categories, 'sexual_minors', False):
            reasons.append("sexual content involving minors")
        if categories.violence:
            reasons.append("violence")
        if getattr(categories, 'violence_graphic', False):
            reasons.append("graphic violence")

        return reasons


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
