from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


def broadcast_update(item):
    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        "restock_updates",
        {
            "type": "send_restock_update",
            "data": {
                "id": item.id,
                "status": item.status,
                "product_name": item.product_name,
            },
        },
    )
