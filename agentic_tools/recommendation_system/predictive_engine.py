"""
================================================================================
MODULE: PREDICTIVE ENGINE (Next Likely Action - NLA)
================================================================================
PURPOSE:
    Forecasts the User's future behavior based on their current state.
    This module simulates the user's mind.

INPUTS:
    - score (float): The current interest score (0.0 - 1.0).
    - segment_names (list): The user's personas (e.g., "Active Trader").

OUTPUTS:
    - predicted_event (str): The specific event the user is likely to perform next.
      (Must match 'eventName' in cdp_eventtracking for validation).
    - probability (float): Confidence level of this prediction (0.0 - 1.0).

MAINTENANCE:
    Update this file when you want to refine behavioral models or add ML logic.
================================================================================
"""

from typing import Tuple, List

# Personas
PERSONA_ACTIVE_TRADER = "High-Frequency Traders"
PERSONA_PASSIVE_INVESTOR = "Passive Investors"

def predict_user_event(score: float, segment_names: List[str]) -> Tuple[str, float]:
    """
    Determines the Next Likely Action (NLA) of the user.
    """
    is_active_trader = PERSONA_ACTIVE_TRADER in segment_names

    # ----------------------------------------
    # SCENARIO 1: High Intent (Hot Lead)
    # ----------------------------------------
    if score >= 0.5:
        if is_active_trader:
            # Active traders execute quickly when interest is high
            return "order-created", 0.92
        else:
            # Passive investors need to view details/charts first
            return "ticker-view", 0.85

    # ----------------------------------------
    # SCENARIO 2: Consideration (Warm Lead)
    # ----------------------------------------
    elif 0.3 <= score < 0.5:
        # User is interested but not committed. Likely to monitor.
        return "watchlist-add", 0.65

    # ----------------------------------------
    # SCENARIO 3: Low Intent (Cold / Churn)
    # ----------------------------------------
    else:
        # Score is too low to predict specific engagement.
        # High risk of ignoring the app or churning.
        return "ignore_content", 0.80