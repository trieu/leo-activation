"""
================================================================================
MODULE: PRESCRIPTIVE ENGINE (Next Best Action - NBA)
================================================================================
PURPOSE:
    Determines the System's optimal intervention strategy.
    This module represents the "Marketing Brain" of the CDP.

INPUTS:
    - predicted_event (str): What the user is about to do (from Predictive Engine).
    - score (float): The raw interest level.

OUTPUTS:
    - action (str): The marketing action ID (e.g., "STRONG_BUY_ALERT").
    - channel (str): The delivery channel (e.g., "PUSH_NOTIFICATION").
    - confidence (float): How sure we are that this intervention is correct.
    - reason (str): Human-readable explanation for the decision.

MAINTENANCE:
    Update this file to change marketing strategies, A/B test channels, 
    or adjust engagement rules.
================================================================================
"""

from typing import Tuple

def recommend_system_action(score: float, predicted_event: str) -> Tuple[str, str, float, str]:
    """
    Determines the Next Best Action (NBA) for the CDP to take.
    Returns: (Action, Channel, Confidence, Reason)
    """
    
    # ----------------------------------------
    # STRATEGY 1: CAPTURE (High Intent / Active)
    # ----------------------------------------
    # Event: 'order-created' 
    # Context: User is likely an Active Trader with High Interest (Score >= 0.5)
    if predicted_event == "order-created":
        return (
            "STRONG_BUY_ALERT", 
            "PUSH_NOTIFICATION", 
            0.95, 
            "High intent detected. Nudge to execute order."
        )

    # ----------------------------------------
    # STRATEGY 2: NURTURE (High Intent / Passive)
    # ----------------------------------------
    # Event: 'ticker-view'
    # Context: User has High Interest (Score >= 0.7) but needs fundamental data.
    if predicted_event == "ticker-view":
        return (
            "SEND_ANALYST_REPORT", 
            "EMAIL_DIGEST", 
            0.85, 
            "User is interested but needs validation. Send report."
        )

    # ----------------------------------------
    # STRATEGY 3: RETAIN (Consideration)
    # ----------------------------------------
    # Event: 'watchlist-add'
    # Context: User is in the 'Warm' zone (Score 0.1 - 0.7).
    if predicted_event == "watchlist-add":
        return (
            "WATCHLIST_SUGGESTION", 
            "IN_APP_BANNER", 
            0.70, 
            "User is in consideration phase. Suggest monitoring."
        )
    
    # STRATEGY 4: DISCOVERY (Low Intent)
    if predicted_event == "search":
        return (
            "DISCOVERY_NUDGE", 
            "IN_APP_FEED", 
            0.50, 
            "User has low interest. Show in feed to spark curiosity."
        )

    # ----------------------------------------
    # STRATEGY 5: IGNORE (Low Value)
    # ----------------------------------------
    # Event: 'ignore_content'
    # Context: User score is < 0.1. Do not spam.
    return (
        "WAIT", 
        "NONE", 
        0.0, 
        f"Score ({score:.2f}) is too low for intervention."
    )