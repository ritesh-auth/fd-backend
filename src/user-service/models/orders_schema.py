from typing import List, Optional
from pydantic import BaseModel, validator

from datetime import datetime

from shared.models.database.models import Order, OrderItem, MenuItems, Restaurant, User, OrderStatus

#Pydantic models
class OrderItemCreate(BaseModel):
    menu_item_id: str
    quantity: int

class OrderCreate(BaseModel):
    user_id: str
    restaurant_id: str
    delivery_address: str
    special_instructions: Optional[str] = None
    items: List[OrderItemCreate]

class OrderItemResponse(BaseModel):
    order_item_id: str
    menu_item_id: str
    menu_item_name: str
    quantity: int
    price: float

class OrderResponse(BaseModel):
    order_id: str
    user_id: str
    restaurant_id: str
    restaurant_name: str
    delivery_agent_id: Optional[str]
    status: OrderStatus
    total_amount: float
    delivery_address: str
    special_instructions: Optional[str]
    estimated_delivery_time: Optional[str]
    created_at: datetime
    items: List[OrderItemResponse]

class UserCreate(BaseModel):
    name: str
    email: str
    phone: str
    address: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    password: str
    repeat_password: str
    address: Optional[str]
