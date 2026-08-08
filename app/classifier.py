import re
from abc import ABC, abstractmethod
from google import genai
from google.genai import types
from app.schemas import TicketClassification
from app.config import settings, logger

# Keyword weights map for heuristic classification
KEYWORDS = {
    "security_emergency": {
        "theft": 5, "stolen": 5, "break-in": 5, "vandalism": 4, "vandalized": 4, 
        "fire": 5, "smoke": 4, "flood": 5, "flooding": 5, "water leak": 4, 
        "unlocked": 3, "open door": 3, "suspicious": 3, "alarm": 4, "robbed": 5,
        "hazard": 4, "injury": 4, "police": 5, "emergency": 4, "unsafe": 3
    },
    "access_issue": {
        "fingerprint": 4, "biometric": 4, "scanner": 3, "face id": 4, "rfid": 3,
        "access card": 3, "jammed": 4, "won't open": 5, "cannot open": 5, 
        "stuck": 4, "frozen": 3, "screen blank": 3, "pin code": 2, "pin number": 2, 
        "forgot pin": 3, "reset pin": 2, "keypad": 3, "keycard": 3, "bluetooth": 3,
        "unable to unlock": 5, "failed access": 4, "kiosk": 2, "denied": 3
    },
    "onboarding_kyc": {
        "kyc": 5, "registration": 4, "register": 4, "document": 3, "upload": 3,
        "verification": 4, "verify": 4, "aadhaar": 4, "pan card": 4, "identity": 3,
        "profile": 2, "activation": 3, "sign up": 4, "create account": 4,
        "selfie": 3, "address proof": 4, "validation": 3, "identity verify": 5
    },
    "billing_payment": {
        "charge": 3, "charged": 3, "double charge": 5, "billing": 4, "invoice": 4,
        "receipt": 3, "refund": 5, "payment": 4, "failed payment": 4, "transaction": 3,
        "price": 2, "subscription": 3, "autopay": 4, "card declined": 4, "deducted": 3,
        "bank transfer": 3, "overcharged": 5, "statement": 2, "money": 2
    },
    "locker_management": {
        "upgrade": 4, "downgrade": 4, "larger locker": 5, "smaller locker": 5,
        "locker size": 4, "terminate": 5, "cancel subscription": 5, "relocate": 4,
        "society transfer": 5, "move out": 4, "transfer locker": 5, "rent locker": 3,
        "close locker": 4, "cancel contract": 5, "allocation": 3, "box upgrade": 4
    },
    "general_support": {
        "help": 1, "question": 2, "hours": 3, "timings": 3, "manual": 3,
        "guideline": 2, "feedback": 3, "suggestion": 2, "support": 1,
        "how to": 2, "information": 2, "inquiry": 2, "contact": 2, "ask": 1
    }
}

SUGGESTED_ACTIONS = {
    "security_emergency": "Page emergency on-call manager immediately. Dispatch security guards to check the locker site.",
    "access_issue": "Initiate remote kiosk diagnostic check. Contact resident to assist with manual override or biometric reset.",
    "onboarding_kyc": "Validate Aadhaar/identity documents manually in CRM. Update verification status.",
    "billing_payment": "Verify stripe transaction logs. Process refund request if overcharged. Email confirmation.",
    "locker_management": "Check availability of locker sizes in the target society database. Prepare upgrade/transfer agreement.",
    "general_support": "Share operational user manual link and society operating hours FAQ."
}

DRAFT_REPLIES = {
    "security_emergency": "Dear Resident, we take security matters extremely seriously. An emergency operations officer has been alerted and is investigating this immediately. We will contact you directly within 15 minutes.",
    "access_issue": "Dear Resident, we apologize for the locker access issues. Our engineering team is running remote diagnostics. Please try using the manual pin override in your mobile app, or contact our helpline if you are trapped.",
    "onboarding_kyc": "Dear Resident, thank you for completing the registration. We are review your KYC submissions manually. You will receive an app notification once verification is complete, typically within 2 hours.",
    "billing_payment": "Dear Resident, we have received your billing inquiry. Our accounts department is reviewing the transactions. If an overcharge has occurred, a refund will be processed to your source card within 3-5 business days.",
    "locker_management": "Dear Resident, thank you for reaching out. We have registered your request for locker size/subscription modification. Our operations executive will confirm the box availability in your society shortly.",
    "general_support": "Dear Resident, thanks for contacting support. You can view the complete user manual and locker room operational hours directly inside the Help section of the mobile app."
}


class BaseClassifier(ABC):
    """
    Abstract Base Class outlining interface requirements for all classification providers.
    """
    
    @abstractmethod
    def classify(self, title: str, body: str) -> TicketClassification:
        """
        Analyze email content and return ticket categories, priorities, and metadata.
        """
        pass


class HeuristicClassifier(BaseClassifier):
    """
    Heuristic rules-based classifier executing local text parsing.
    Used as the primary fallback when running offline or without credentials.
    """
    
    def _generate_summary(self, title: str, text: str) -> str:
        """
        Extract or generate a clean one-sentence summary from email title and body.
        """
        clean_title = title.strip()
        if len(clean_title) > 10 and not clean_title.lower().startswith("re:") and not clean_title.lower().startswith("fwd:"):
            return clean_title
        
        # Fallback to extracting first readable sentence from body
        sentences = [s.strip() for s in re.split(r'[.!?\n]', text) if s.strip()]
        if sentences:
            first_sentence = sentences[0]
            if len(first_sentence) > 80:
                return first_sentence[:77] + "..."
            return first_sentence
        return "Customer support request."

    def classify(self, title: str, body: str) -> TicketClassification:
        """
        Analyzes keywords and patterns locally to determine classification.
        """
        text = f"{title} {body}".lower()
        
        # Base scores for each category
        scores = {cat: 0.0 for cat in KEYWORDS}
        explainable_signals = []
        
        # 1. Keyword scoring
        for category, keyword_weights in KEYWORDS.items():
            for word, weight in keyword_weights.items():
                count = text.count(word)
                if count > 0:
                    scores[category] += weight * count
                    explainable_signals.append(f"Keyword match '{word}' in {category}: {count}x (weight={weight})")
                    
        # 2. Phrase matching (high weight boosts)
        phrases = {
            "security_emergency": ["door left open", "stolen locker", "locker room alarm", "water leak", "fire alarm", "unauthorized entry", "stole my", "someone opened"],
            "access_issue": ["cannot open", "won't open", "jammed door", "fingerprint scanner", "screen frozen", "forgot pin", "can't unlock", "stuck locker", "biometric fail"],
            "onboarding_kyc": ["kyc rejected", "upload document", "aadhaar verification", "identity verification", "register account", "verification failed"],
            "billing_payment": ["charged twice", "double charge", "refund request", "autopay failed", "card declined", "charged me", "payment failed"],
            "locker_management": ["upgrade locker", "cancel subscription", "larger box", "change locker size", "locker transfer", "close my locker", "cancel my subscription"],
            "general_support": ["society hours", "operating timings", "user manual", "how does it work", "where is it", "timing of"]
        }
        for category, phrase_list in phrases.items():
            for phrase in phrase_list:
                if phrase in text:
                    scores[category] += 8.0
                    explainable_signals.append(f"Keyphrase match '{phrase}' in {category}: +8.0 score")
                    
        # Determine the category with the highest score
        best_category = max(scores, key=scores.get)
        max_score = scores[best_category]
        
        # Calculate confidence score (normalized between 0.3 and 0.95)
        total_score = sum(scores.values())
        if total_score > 0:
            confidence = min(0.95, 0.3 + (max_score / total_score) * 0.65)
        else:
            confidence = 0.5
            best_category = "general_support"
            explainable_signals.append("Defaulting to 'general_support' due to zero keyword matches.")
            
        # 3. Sentiment & Urgency analysis for priority calculation
        sentiment_urgency_words = ["urgent", "emergency", "immediate", "immediately", "danger", "police", "trapped", "stuck", "broken", "help", "alarm", "smoke"]
        urgency_score = sum(1 for word in sentiment_urgency_words if word in text)
        if urgency_score > 0:
            explainable_signals.append(f"Urgency/sentiment markers matched: +{urgency_score} priority trigger words")
        
        # Establish default priority based on category
        if best_category == "security_emergency":
            priority = "P0"
        elif best_category == "access_issue":
            priority = "P0" if urgency_score > 0 else "P1"
        elif best_category in ["onboarding_kyc", "billing_payment"]:
            priority = "P1" if urgency_score > 1 else "P2"
        elif best_category == "locker_management":
            priority = "P2" if urgency_score > 0 else "P3"
        else:
            priority = "P3"
            
        # 4. Generate metadata outputs
        summary = self._generate_summary(title, text)
        reasoning = f"Heuristic classification selected '{best_category}' with confidence {confidence:.2f}. " \
                    f"Weighted keyword score: {max_score:.1f} (out of {total_score:.1f} total tokens matched)."
        if urgency_score > 0:
            reasoning += f" Urgency markers detected (+{urgency_score} priority signals)."
            
        suggested_action = SUGGESTED_ACTIONS[best_category]
        draft_reply = DRAFT_REPLIES[best_category]
        
        # Compile explainable AI log
        explainable_ai = "Weighted Scoring Signals:\n" + "\n".join([f"- {sig}" for sig in explainable_signals])
        
        return TicketClassification(
            category=best_category,
            priority=priority,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            summary=summary,
            suggested_action=suggested_action,
            draft_reply=draft_reply,
            explainable_ai=explainable_ai
        )


class GeminiClassifier(BaseClassifier):
    """
    AI classifier powered by the official google-genai SDK.
    Supports structured schema outputs for absolute alignment.
    """
    
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        
    def classify(self, title: str, body: str) -> TicketClassification:
        """
        Queries Gemini with custom prompt engineering to obtain structured outputs.
        """
        prompt = f"Title: {title}\nBody: {body}"
        system_prompt = (
            "You are a Senior Customer Support AI for Aurm, a company that provides secure, premium automated safe deposit lockers "
            "located directly inside housing societies. Your job is to classify the support query.\n\n"
            "Categories:\n"
            "- security_emergency: fire, theft, water leak, flooding, alarm, vandalism, door left open, broken safe.\n"
            "- access_issue: finger scanner fail, RFID fail, kiosk frozen, screen blank, forgot PIN, manual key jams.\n"
            "- onboarding_kyc: document verification issues, Pan/Aadhaar verify, facial profile setup, profile registration.\n"
            "- billing_payment: double charging, refund requests, invoices, expired credit cards, billing renewal.\n"
            "- locker_management: upgrading size, terminating contract, society transfer, terminating box.\n"
            "- general_support: manuals, operating timings, general society locker questions.\n\n"
            "Priorities:\n"
            "- P0: Critical safety emergency or locker trapped block (e.g. stuck inside, safety threat, broken scanner during night).\n"
            "- P1: Direct access blocker (unable to retrieve valuables, RFID fail, jammed door).\n"
            "- P2: Active account or payment issue blocking setup/verify, KYC rejection, auto-charge fail.\n"
            "- P3: Inquiries, upgrades, timing checks, suggestions.\n\n"
            "For explainable_ai, list specific words, phrases, or conceptual patterns matched in the title/body "
            "that directed your decision (e.g., 'Matched phrase \"charged twice\" -> billing_payment').\n\n"
            "You MUST return a JSON structure matching the required schema. Ensure reasoning is clear and concise, and the "
            "draft_reply is professional, addressing the user's issue directly."
        )

        # Execute request, retrying once on failure
        last_exception = None
        for attempt in range(2):
            try:
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=TicketClassification,
                        system_instruction=system_prompt,
                        temperature=0.1
                    )
                )
                
                # Validate response structure
                if not response.text:
                    raise ValueError("Gemini returned empty classification output.")
                    
                result = TicketClassification.model_validate_json(response.text)
                return result
            except Exception as e:
                logger.warning(f"Gemini API classification attempt {attempt + 1} failed: {e}")
                last_exception = e
                
        raise last_exception or RuntimeError("Gemini classification failed after multiple retries.")


class UnifiedClassifier(BaseClassifier):
    """
    Orchestration classifier routing request to Gemini or fallback local Heuristics.
    """
    
    def __init__(self) -> None:
        self.heuristic = HeuristicClassifier()
        self.gemini = None
        self.last_source = "heuristic"
        
        # Pre-initialize Gemini if key is available
        api_key = settings.GEMINI_API_KEY
        if api_key and api_key.strip():
            try:
                self.gemini = GeminiClassifier(api_key=api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Classifier engine: {e}")

    def classify(self, title: str, body: str) -> TicketClassification:
        """
        Dynamically dispatches queries based on credential presence and API health.
        """
        if self.gemini:
            try:
                logger.info("Attempting ticket classification via Gemini LLM engine...")
                res = self.gemini.classify(title, body)
                self.last_source = "gemini"
                return res
            except Exception as e:
                logger.error(f"Gemini engine failed, executing fallback Heuristics. Error: {e}", exc_info=True)
                # Fall through to Heuristics
                
        logger.info("Classifying ticket via Heuristic rule engine...")
        res = self.heuristic.classify(title, body)
        self.last_source = "heuristic"
        return res


def get_classifier() -> BaseClassifier:
    """
    Dependency helper returning the active UnifiedClassifier orchestrator.
    """
    return UnifiedClassifier()
