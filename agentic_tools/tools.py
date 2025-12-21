
from typing import Dict, Any

from agentic_tools.customer_data_tools import manage_leo_segment
from agentic_tools.datetime_tools import get_date
from agentic_tools.marketing_tools import activate_channel
from agentic_tools.weather_tools import get_current_weather


# =====================================================
# LLM-CALLABLE TOOLS (With Mandatory Docstrings)
# =====================================================

AVAILABLE_TOOLS: Dict[str, Any] = {
    "get_date": get_date,
    "get_current_weather": get_current_weather,
    "get_current_marketing_event": get_current_weather,
    "manage_leo_segment": manage_leo_segment,
    "activate_channel": activate_channel,
}