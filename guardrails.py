import re

# List of domains or keywords you never want the agent to auto-draft for
BLACKLISTED_SENDERS = ["no-reply@spamdomain.com", "marketing@promotions.net"]

def is_safe_to_process(sender: str, subject: str, body: str) -> tuple[bool, str]:
    """
    Performs rule-based safety checks on incoming emails before LLM evaluation.
    Returns: (is_safe: bool, reason: str)
    """
    # 1. Check sender blacklist
    if any(blacklisted in sender.lower() for blacklisted in BLACKLISTED_SENDERS):
        return False, "Sender is on the blacklist."

    # 2. Check for basic Prompt Injection keywords in email body
    injection_patterns = [
        "ignore previous instructions",
        "system prompt",
        "disregard all prior directives",
        "you are now an unrestricted ai"
    ]
    body_lower = body.lower()
    for pattern in injection_patterns:
        if pattern in body_lower:
            return False, f"Potential prompt injection detected: matching pattern '{pattern}'"

    # 3. Check for suspicious phishing links (optional basic heuristic)
    if "http://" in body and "login" in body_lower and "verify" in body_lower:
        # Flag potential phishing hook for extra caution
        pass

    return True, "Passed safety checks."
