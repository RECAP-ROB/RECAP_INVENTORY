from typing import Optional

from pydantic import BaseModel


class RestockRequest(BaseModel):
    item_id: int
    product_name: str
    quantity: int
    shelf_location: str
    current_state: Optional[str] = "unknown"