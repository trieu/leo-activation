

from typing import Dict


def manage_leo_segment(segment_name: str, action: str = "create") -> Dict[str, str]:
    """
    Create, update, or delete a LEO CDP segment.

    Args:
        segment_name: The name of the target segment.
        action: The management action (create, update, or delete).
    """
    return {"status": "success", "segment": segment_name, "action": action}
