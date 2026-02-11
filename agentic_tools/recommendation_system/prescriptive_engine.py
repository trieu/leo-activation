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
    
    # STRATEGY 1: CAPTURE (User is ready to buy)
    # Goal: Remove friction and close the deal immediately.
    if predicted_event == "place_order":
        return (
            "STRONG_BUY_ALERT", 
            "PUSH_NOTIFICATION", 
            0.7, 
            "User intent is high (Place Order). Nudge to execute."
        )

    # STRATEGY 2: NURTURE (User is researching)
    # Goal: Provide value/information to build confidence.
    if predicted_event == "view_ticker_details":
        return (
            "SEND_ANALYST_REPORT", 
            "EMAIL_DIGEST", 
            0.50, 
            "User is researching. Provide fundamental data."
        )

    # STRATEGY 3: RETAIN (User is watching)
    # Goal: Keep the product top-of-mind without being annoying.
    if predicted_event == "add_to_watchlist":
        return (
            "WATCHLIST_SUGGESTION", 
            "IN_APP_BANNER", 
            0.30, 
            "User is in consideration phase. Suggest monitoring."
        )

    # STRATEGY 4: IGNORE (Low Value)
    # Goal: Do not spam users with low intent.
    return (
        "WAIT", 
        "NONE", 
        0.0, 
        f"Predicted event '{predicted_event}' does not warrant intervention."
    )