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

def predict_user_event(score: float, segment_names: List[str]) -> Tuple[str, float]:
    """
    Determines the Next Likely Action (NLA) of the user based on 4 tiers of interest.
    """
    is_active_trader = PERSONA_ACTIVE_TRADER in segment_names

    # ----------------------------------------
    # SCENARIO 1: High Intent (Hot Lead)
    # Range: 0.7 <= Score <= 1.0
    # ----------------------------------------
    if score >= 0.7:
        # Extremely high scores get a probability boost
        confidence = 0.95 if score >= 0.9 else 0.85

        if is_active_trader:
            # Active traders are likely to execute
            return "order-created", confidence
        else:
            # Passive investors are likely to research deeply
            return "ticker-view", confidence

    # ----------------------------------------
    # SCENARIO 2: Consideration (Warm Lead)
    # Range: 0.5 <= Score < 0.7
    # ----------------------------------------
    elif score >= 0.5:
        # Strong enough to monitor, not strong enough to buy yet
        return "watchlist-add", 0.70

    # ----------------------------------------
    # SCENARIO 3: Low Intent (Discovery)
    # Range: 0.1 <= Score < 0.5
    # ----------------------------------------
    elif score >= 0.1:
        # They looked at it, but interest is weak. 
        # Prediction: They might search for it again or add it if prompted.
        return "search", 0.60 

    # ----------------------------------------
    # SCENARIO 4: Noise (Ignore)
    # Range: 0.0 <= Score < 0.1
    # ----------------------------------------
    else:
        # Score is too low (noise). Likely to ignore content.
        return "ignore-content", 0.90