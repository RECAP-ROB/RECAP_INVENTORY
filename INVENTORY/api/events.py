from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json


class EventBus:
    # Domain events are published to the Redis channel layer

    @staticmethod
    def publish(event_type, data):
        # Event is published to websocket subscribers
        channel_layer = get_channel_layer()

        async_to_sync(channel_layer.group_send)(
            "restock_updates",
            {
                "type": "send_event",
                "event_type": event_type,
                "data": data,
            },
        )
