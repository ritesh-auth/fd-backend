from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import httpx
from typing import List, Optional
from pydantic import BaseModel, validator, Field

from shared.config.database.config import get_async_db
from shared.config.logger.config import get_logger
from shared.models.database.models import Order, OrderItem, MenuItems, Restaurant, DeliveryAgent, OrderStatus, DeliveryAgentStatus, User
from shared.utils.shared_utility import verify_jwt_token, to_float, get_current_user

#Initiate logger
logger = get_logger("restaurant-service/orders")

#Initiate router
router = APIRouter()

security = HTTPBearer()

"""TODO: Seperate the pydantic model for more maintainable code"""
#Pydantic Models
class OrderItemResponse(BaseModel):
    id: str
    menu_item_id: str
    menu_item_name: str
    quantity: int
    price: float

class OrderResponse(BaseModel):
    id: str
    user_id: str
    restaurant_id: str
    delivery_agent_id: Optional[str]
    status: OrderStatus
    total_amount: float
    delivery_address: str
    special_instructions: Optional[str]
    estimated_delivery_time: Optional[int]
    created_at: str
    items: List[OrderItemResponse]

class UpdateOrderStatus(BaseModel):
    status: OrderStatus

@router.get("/my-restaurant-orders", response_model = List[OrderResponse])
async def get_my_restaurant_orders(
    status_filter: Optional[OrderStatus] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_async_db)
):
    """Get all orders from all restaurant owned by current user"""

    try:
        restaurants_query        = select(Restaurant).where(Restaurant.owner_id == str(current_user.id))
        restaurants_query_result = await db.execute(restaurants_query)
        restaurants              = restaurants_query_result.scalars().all()

        #early return is no restaurants are found.
        if not restaurants:
            return []
        
        restaurant_ids = [str(r.id) for r in restaurants]

        order_query  = select(Order).where(Order.restaurant_id.in_(restaurant_ids))
        if status_filter:
            order_query = order_query.where(Order.status == status_filter)

        order_query = order_query.order_by(Order.created_at.desc())

        order_query_result = await db.execute(order_query)
        orders             = order_query_result.scalars().all()

        #reponse
        orders_reponse = []
        for order in orders:

            items_query        = select(OrderItem).where(OrderItem.order_id == order.id)
            items_query_result = await db.execute(items_query) 
            ordered_items      = items_query_result.scalars().all()

            order_items_response = []
            for order_item in ordered_items:
                menu_item = await db.get(MenuItems, order_item.menu_item_id)
                order_items_response.append(OrderItemResponse(
                    id             = str(order_item.id),
                    menu_item_id   = str(order_item.menu_item_id),
                    menu_item_name = menu_item.name if menu_item else "Unknown Item",
                    quantity       = order_item.quantity,
                    price          = to_float(order_item.price)
                ))

            orders_reponse.append(OrderResponse(
                id                      = str(order.id),
                user_id                 = str(order.user_id),
                restaurant_id           = str(order.restaurant_id),
                delivery_agent_id       = str(order.delivery_agent_id) if order.delivery_agent_id else None,
                status                  = order.status,
                total_amount            = to_float(order.total_amount),
                delivery_address        = order.delivery_address,
                special_instructions    = order.special_instructions,
                estimated_delivery_time = order.estimated_delivery,
                created_at              = order.created_at.isoformat(),
                items                   = order_items_response
            ))

        logger.info(f"Retrieved {len(orders_reponse)} orders for user {current_user.id}'s restaurants")
        return orders_reponse
        
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error getting user restaurant orders, error: {error}")
        raise HTTPException(status_code = 500, detail = "Internal server error.")
    
@router.patch("/update-status/{order_id}", response_model = OrderResponse)
async def update_order_status(
    order_id: str,
    status_update: UpdateOrderStatus,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_async_db)
):
    """Restaurant route to take action on the order (Accept / reject)"""

    try: 
        order = await db.get(Order, order_id)
        if not order:
            raise HTTPException(status_code = 404, detail = "Order not found")
        
        restaurant = await db.get(Restaurant, order.restaurant_id)
        if not restaurant:
            raise HTTPException(status_code = 404, detail = "Restaurant not found")
        
        if str(restaurant.owner_id) != str(current_user.id) and not getattr(current_user, 'is_admin', False):
            raise httpx(status_update = 403, detail = "Access denied: You are not allowed to perform this action.") 
        
        current_status = order.status
        updated_status = status_update.status

        valid_transitions = {
            OrderStatus.PENDING: [OrderStatus.ACCEPTED, OrderStatus.REJECTED],
            OrderStatus.ACCEPTED: [OrderStatus.PREPARING],
            OrderStatus.PREPARING: [OrderStatus.READY_FOR_PICKUP],
            OrderStatus.READY_FOR_PICKUP: [OrderStatus.OUT_FOR_DELIVERY]
        }

        if current_status not in valid_transitions or updated_status not in valid_transitions[current_status]:
            raise HTTPException(status_code = 400, detail = f"Invalid status transition from {current_status.value} to {updated_status.value}")
        
        #if the status passes all above criteria then update the status in database.
        order.status = updated_status

        # Only assign a delivery agent if not already assigned
        if (updated_status == OrderStatus.ACCEPTED or updated_status == OrderStatus.PREPARING or updated_status == OrderStatus.OUT_FOR_DELIVERY) and not order.delivery_agent_id:
            delivery_agent = await auto_assign_delivery_agent(db)
            if delivery_agent:
                order.delivery_agent_id = str(delivery_agent.id)
                delivery_agent.status = DeliveryAgentStatus.BUSY #if the order is assigned then mark them as busy.
                logger.info(f"Auto assigned delivery agent {delivery_agent.id} to order {order_id}")
            else:
                logger.warning(f"No delivery agent available at the moment. Assigning an agent shortly") #probably start some cron job unless the order is assigned to a delivery partner

        await db.commit()
        await db.refresh(order)

        items_query        = select(OrderItem).where(OrderItem.order_id == order.id)
        items_query_result = await db.execute(items_query) 
        ordered_items      = items_query_result.scalars().all()

        order_items_response = []
        for order_item in ordered_items:
            menu_item = await db.get(MenuItems, order_item.menu_item_id)
            order_items_response.append(OrderItemResponse(
                id             = str(order_item.id),
                menu_item_id   = str(order_item.menu_item_id),
                menu_item_name = menu_item.name if menu_item else "Unknown Item",
                quantity       = order_item.quantity,
                price          = to_float(order_item.price)
            ))

        logger.info(f"Order {order_id} status updated to {updated_status.value} by {current_user.id}")

        return OrderResponse(
            id                      = str(order.id),
            user_id                 = str(order.user_id),
            restaurant_id           = str(order.restaurant_id),
            delivery_agent_id       = str(order.delivery_agent_id) if order.delivery_agent_id else None,
            status                  = order.status,
            total_amount            = to_float(order.total_amount),
            delivery_address        = order.delivery_address,
            special_instructions    = order.special_instructions,
            estimated_delivery_time = order.estimated_delivery,
            created_at              = order.created_at.isoformat(),
            items                   = order_items_response
        )
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error updating order status: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error.")
    
async def auto_assign_delivery_agent(db: AsyncSession) -> Optional[DeliveryAgent]:
    """
    Auto assign delivery agent
    """

    try:
        agent_query        = select(DeliveryAgent).where(DeliveryAgent.status == DeliveryAgentStatus.AVAILABLE)
        agent_query_result = await db.execute(agent_query)
        available_agent    = agent_query_result.scalars().all()

        if not available_agent:
            return None

        selected_agent = available_agent[0]

        return selected_agent

    except Exception as error:
        logger.error(f"Error auto-assigning delivery agent, error: {str(error)}")
        return None
