from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from typing import Optional
from pydantic import BaseModel

from shared.config.database.config import get_async_db
from shared.config.logger.config import get_logger
from shared.models.database.models import Order, DeliveryAgent, OrderStatus, DeliveryAgentStatus, User
from shared.utils.shared_utility import verify_jwt_token, to_float, get_current_user

# Initiate logger
logger = get_logger("delivery-service/orders")

# Initiate router
router = APIRouter()

security = HTTPBearer()

"""TODO: Separate the pydantic models for more maintainable code"""
# Pydantic models
class DeliveryStatusUpdate(BaseModel):
    status: OrderStatus

class DeliveryResponse(BaseModel):
    id: str  # UUID as string
    user_id: str  # UUID as string
    restaurant_id: str  # UUID as string
    delivery_agent_id: Optional[str]  # UUID as string
    status: OrderStatus
    total_amount: float
    delivery_address: str
    special_instructions: Optional[str]
    estimated_delivery_time: Optional[int]
    created_at: str

@router.patch("/{order_id}/status", response_model=DeliveryResponse)
async def update_delivery_status(
    order_id: str,
    status_update: DeliveryStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update the delivery status of orders (delivery agent only)."""
    try:
        order = await db.get(Order, order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if not order.delivery_agent_id:
            raise HTTPException(status_code=400, detail="No delivery agent assigned to this order")
        
        delivery_agent = await db.get(DeliveryAgent, order.delivery_agent_id)
        if not delivery_agent:
            raise HTTPException(status_code=404, detail="Delivery agent not found")
        
        # Check if current user is authorized to update this delivery
        if not (getattr(delivery_agent, 'user_id', None) == str(current_user.id) or 
                getattr(current_user, 'is_admin', False)):
            raise HTTPException(
                status_code=403, 
                detail="Access denied: can only update deliveries assigned to you"
            )
        
        # Validate status transition for delivery
        current_status = order.status
        new_status = status_update.status
        
        # Define valid delivery status transitions
        valid_delivery_transitions = {
            OrderStatus.READY_FOR_PICKUP: [OrderStatus.OUT_FOR_DELIVERY],
            OrderStatus.OUT_FOR_DELIVERY: [OrderStatus.DELIVERED],
        }
        
        if current_status not in valid_delivery_transitions or new_status not in valid_delivery_transitions[current_status]:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid delivery status transition from {current_status.value} to {new_status.value}"
            )
        
        # Update order status
        order.status = new_status
        
        # If order is delivered, mark delivery agent as available
        if new_status == OrderStatus.DELIVERED:
            delivery_agent.status = DeliveryAgentStatus.AVAILABLE
            logger.info(f"Delivery agent {delivery_agent.id} marked as available after completing order {order_id}")
        
        await db.commit()
        await db.refresh(order)
        
        logger.info(f"Order {order_id} delivery status updated to {new_status.value} by user {current_user.id}")
        
        return DeliveryResponse(
            id=str(order.id),
            user_id=str(order.user_id),
            restaurant_id=str(order.restaurant_id),
            delivery_agent_id=str(order.delivery_agent_id),
            status=order.status,
            total_amount=to_float(order.total_amount),  # Convert Decimal to float
            delivery_address=order.delivery_address,
            special_instructions=order.special_instructions,
            estimated_delivery_time=order.estimated_delivery_time,
            created_at=order.created_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating delivery status: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
