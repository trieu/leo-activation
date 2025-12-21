import os
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any, Type

# =====================================================
#  ACTIVATION CHANNEL STRATEGY LAYER (OOP)
# =====================================================


class NotificationChannel(ABC):
    """Base strategy for all activation channels."""
    @abstractmethod
    def send(self, recipient_segment: str, message: str, **kwargs) -> Dict[str, Any]:
        pass


class EmailChannel(NotificationChannel):
    def send(self, recipient_segment: str, message: str, **kwargs):
        print(f"[Email] Segment={recipient_segment} | Message={message}")
        return {"status": "success", "channel": "email", "sent": 120}


class ZaloOAChannel(NotificationChannel):
    def __init__(self):
        self.api_url = "https://openapi.zalo.me/v3.0/oa/message/cs"
        self.access_token = os.getenv("ZALO_OA_TOKEN")

    def send(self, recipient_segment: str, message: str, **kwargs):
        print(f"[Zalo OA] Segment={recipient_segment}")
        return {"status": "success", "channel": "zalo_oa", "delivered": True}


class MobilePushChannel(NotificationChannel):
    def send(self, recipient_segment: str, message: str, **kwargs):
        title = kwargs.get("title", "Notification")
        print(f"[Mobile Push] Segment={recipient_segment} | Title={title}")
        return {"status": "success", "channel": "mobile_push"}


class WebPushChannel(NotificationChannel):
    def send(self, recipient_segment: str, message: str, **kwargs):
        print(f"[Web Push] Segment={recipient_segment}")
        return {"status": "success", "channel": "web_push"}

class FacebookPageChannel(NotificationChannel):
    def send(self, recipient_segment: str, message: str, **kwargs):
        print(f"[Facebook Page] Segment={recipient_segment}")
        return {"status": "success", "channel": "facebook_page"}


class ActivationManager:
    """Factory + registry for activation channels."""
    _channels: Dict[str, Type[NotificationChannel]] = {
        "email": EmailChannel,
        "zalo_oa": ZaloOAChannel,
        "mobile_push": MobilePushChannel,
        "web_push": WebPushChannel,
        "facebook_page": FacebookPageChannel,
    }

    @classmethod
    def execute(cls, channel_key: str, segment: str, message: str, **kwargs) -> Dict[str, Any]:
        channel_class = cls._channels.get(channel_key.lower())
        if not channel_class:
            raise ValueError(f"Unsupported channel: {channel_key}")
        return channel_class().send(segment, message, **kwargs)
    
# =====================================================

def activate_channel(channel: str, segment_name: str, message: str, title: str = "Notification") -> Dict[str, Any]:
    """
    LEO CDP activation tool for sending messages.

    Args:
        channel: Channel type (email, zalo, mobile_push, or web_push).
        segment_name: The target segment for activation.
        message: The content message to send.
        title: Optional title for push notifications.
    """
    try:
        print(f"Activating channel '{channel}' for segment '{segment_name}' with message '{message}'")
        
        # Call the ActivationManager to execute the channel activation
        return ActivationManager.execute(
            channel_key=channel,
            segment=segment_name,
            message=message,
            title=title,
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}
