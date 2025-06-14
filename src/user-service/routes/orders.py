import os
import sys
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config.database.config import get_async_db
from shared.models.database.models import Order, OrderItem, MenuItems, Restaurant, User, OrderStatus
from shared.config.logger.config import get_logger
from shared.utils.shared_utility import to_decimal, to_float, calculate_order_total, validate_price, verify_jwt_token, get_current_user

from models.orders_schema import OrderItemCreate, OrderCreate, OrderItemResponse, OrderResponse, UserCreate, UserResponse

#Initialize logger instance
logger = get_logger("user-service/orders")

#Initialize router
router = APIRouter()

#Intialize security from fastapi
security = HTTPBearer()

@router.post("/place-order", response_model = OrderResponse)
async def place_order(
    order_data: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_async_db)
):
    """Place order from available restaurants"""

    try:

        restaurant = await db.get(Restaurant, order_data.restaurant_id)

        if not restaurant:
            logger.error("Restaurant not found.")
            raise HTTPException(status_code = 404, detail = "Restaurant not found.")
        
        if not restaurant.is_online:
            logger.error("Restaurant is currently offline.")
            raise HTTPException(status_code = 400, detail = "Restaurant is currently offline.")
        

        total_amount     = Decimal('0.00')
        
        order_items_data = []
        for item_data in order_data.items:
            menu_item = await db.get(MenuItems, item_data.menu_item_id)
            if not menu_item:
                logger.error(f"Menu item {item_data.menu_item_id} not found")
                raise HTTPException(status_code = 404, detail = f"Menu item {item_data.menu_item_id} not found")
            
            if not menu_item.is_available:
                logger.error(f"Menu item '{menu_item.name}' is not available")
                raise HTTPException(status_code = 400, detail = f"Menu item '{menu_item.name}' is not available")
            
            if str(menu_item.restaurant_id) != str(order_data.restaurant_id):
                logger.error(f"Menu item '{menu_item.name}' does not belong to this restaurant")
                raise HTTPException(status_code = 400, detail = f"Menu item '{menu_item.name}' does not belong to this restaurant")
            
            item_price    = menu_item.price
            quantity      = item_data.quantity
            item_total    = item_price * quantity
            total_amount += item_total

            order_items_data.append({
                "menu_item": menu_item,
                "quantity": quantity,
                "price": item_price
            })

        if total_amount <= 0:
            logger.error("Order total must be greater than 0")
            raise HTTPException(status_code = 400, detail = "Order total must be greater than 0")
        
        order = Order(
            user_id                 = str(current_user.id),
            restaurant_id           = order_data.restaurant_id,
            status                  = OrderStatus.PENDING,
            total_amount            = total_amount,
            delivery_address        = order_data.delivery_address,
            special_instructions    = order_data.special_instructions
        )

        db.add(order)
        await db.flush()

        order_items = []
        for item_data in order_items_data:
            order_item = OrderItem(
                order_id = order.id,
                menu_item_id = item_data["menu_item"].id, 
                quantity = item_data["quantity"],
                price = item_data["price"]
            )
            db.add(order_item)
            order_items.append(order_item)

        await db.commit()
        await db.refresh(order)

        order_items_response = []
        logger.debug(f"order_items_data: {order_items_data}")
        for order_item in order_items:
            menu_item = next(item["menu_item"] for item in order_items_data if item["menu_item"].id == order_item.menu_item_id)
            logger.debug(f"order_item: {order_item}, menu_item: {menu_item}")
            order_items_response.append(OrderItemResponse(
                order_item_id = str(order_item.id),
                menu_item_id = str(order_item.menu_item_id),
                menu_item_name = menu_item.name,
                quantity = order_item.quantity,
                price = to_float(order_item.price)
            ))
        logger.debug(f"order_items_response: {order_items_response}")

        logger.info(f"Order {order.id} placed successfully for user {current_user.id}")
        return OrderResponse(
            order_id                = str(order.id),
            user_id                 = str(order.user_id),
            restaurant_id           = str(order.restaurant_id),
            restaurant_name         = restaurant.name,
            delivery_agent_id       = str(order.delivery_agent_id) if order.delivery_agent_id else None,
            status                  = order.status,
            total_amount            = to_float(order.total_amount),
            delivery_address        = order.delivery_address,
            special_instructions    = order.special_instructions,
            estimated_delivery_time = "30",
            created_at              = order.created_at,
            items                   = order_items_response
        )
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error in placing order, error: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error.")
    
@router.get("/my-orders", response_model = List[OrderResponse])
async def get_my_orders(
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_async_db)
):
    """Get all orders for teh current authenticated user."""

    try:
        user_id = str(current_user.id)

        #Get user orders
        order_query  = select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
        query_result = await db.execute(order_query)
        orders       = query_result.scalars().all()

        orders_response = []
        for order in orders:
            restaurant = await db.get(Restaurant, order.restaurant_id)

            items_query        = select(OrderItem).where(OrderItem.order_id == order.id)
            items_query_result = await db.execute(items_query)
            order_items        = items_query_result.scalars().all()

            order_items_response = []
            for order_item in order_items:
                menu_item = await db.get(MenuItems, order_item.menu_item_id)
                order_items_response.append(OrderItemResponse(
                    order_item_id  = str(order_item.id),
                    menu_item_id   = str(order_item.menu_item_id),
                    menu_item_name = menu_item.name if menu_item else "Unknown Item",
                    quantity       = order_item.quantity,
                    price          = to_float(order_item.price) 
                ))

            orders_response.append(OrderResponse(
                order_id                = str(order.id),
                user_id                 = str(order.user_id),
                restaurant_id           = str(order.restaurant_id),
                restaurant_name         = restaurant.name if restaurant else "Unkown Restaurant",
                delivery_agent_id       = str(order.delivery_agent_id) if order.delivery_agent_id else None,
                status                  = order.status,
                total_amount            = to_float(order.total_amount),
                delivery_address        = order.delivery_address,
                special_instructions    = order.special_instructions,
                estimated_delivery_time = "30",
                created_at              = order.created_at,
                items                   = order_items_response
            ))
        
        logger.info(f"Retrived {len(orders_response)} orders for user {user_id}")
        return orders_response
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error getting user roles, error: {str(error)}")
        raise HTTPException(status_code = 500, detail = "Internal server error.")
    
@router.get("/get-order-details/{order_id}", response_model = OrderResponse)
async def get_orders(order_id: str, current_user: User =Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    """
    Get a specific order using a order id
    """

    try:
        order = await db.get(Order, order_id)
        if not order:
            raise HTTPException(status_code = 404, detail = "Order not found")
        
        if str(order.user_id) != str(current_user.id):
            raise HTTPException(status_code = 403, detail = "Access denied: you can view order only ordered by you.")
        
        restaurant = await db.get(Restaurant, order.restaurant_id)

        items_query        = select(OrderItem).where(OrderItem.order_id == order.id)
        items_query_result = await db.execute(items_query)
        ordered_items      = items_query_result.scalars().all()

        order_items_response = []
        for order_item in ordered_items:
            menu_item = await db.get(MenuItems, order_item.menu_item_id)
            order_items_response.append(OrderItemResponse(
                order_item_id  = str(order_item.id),
                menu_item_id   = str(order_item.menu_item_id),
                menu_item_name = menu_item.name if menu_item else "Unknown Item",
                quantity       = order_item.quantity,
                price          = to_float(order_item.price) 
            ))

        return OrderResponse(
            order_id                = str(order.id),
            user_id                 = str(order.user_id),
            restaurant_id           = str(order.restaurant_id),
            restaurant_name         = restaurant.name if restaurant else "Unkown Restaurant",
            delivery_agent_id       = str(order.delivery_agent_id) if order.delivery_agent_id else None,
            status                  = order.status,
            total_amount            = to_float(order.total_amount),
            delivery_address        = order.delivery_address,
            special_instructions    = order.special_instructions,
            estimated_delivery_time = "30",
            created_at              = order.created_at,
            items                   = order_items_response
        )
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error getting order {order_id}: error: {str(error)}")
        raise HTTPException(status_code = 500, detail = "Internal server error.") 

@router.delete("/cancel-order/{order_id}")
async def cancel_order(order_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_async_db)):
    """
    Route from which the user cancel their own order. (and only if order is in PENDING state)
    """

    try:
        order = await db.get(Order, order_id)

        if not order:
            raise HTTPException(status_code = 404, detail = "Order not found")
        
        if str(order.user_id) != str(current_user.id):
            raise HTTPException(status_code = 403, detail = "Access denied: you can only order you own.")
        
        if order.status != OrderStatus.PENDING:
            raise HTTPException(status_code = 400, detail = f"Cannot order with status {order.status.value}")

        #if order passes all these conditions then update the order status as CANCELLED
        order.status = OrderStatus.CANCELLED

        await db.commit()

        logger.info(f"Order {order_id} cancelled")
        return {"message": "Order cancelled successfully", "order_id": order_id}
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error cancelling order: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error.")
