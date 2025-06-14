from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config.database.config import get_async_db
from shared.models.database.models import Rating, Order, Restaurant, DeliveryAgent, OrderStatus
from shared.config.logger.config import get_logger

from pydantic import BaseModel, Field

#Initialize logger
logger = get_logger("user-service/rating")

#Initialize router
router = APIRouter()

class RatingCreate(BaseModel):
    user_id: str
    order_id: str
    restaurant_rating: Optional[int] = Field(None, ge=1, le=5)
    delivery_rating: Optional[int] = Field(None, ge=1, le=5)
    food_rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = None

class RatingResponse(BaseModel):
    id: int
    user_id: int
    order_id: int
    delivery_agent_id: Optional[int]
    restaurant_rating: Optional[int]
    delivery_rating: Optional[int]
    food_delivery: Optional[int]
    comment: Optional[str]
    created_at: str

@router.post("/rate-order", response_model = RatingResponse)
async def create_rating(
    rating_data: RatingCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """Rating route for the user to give rating for delivery agents and food."""

    try:
        #Check if the order exists and belong to same user.
        order = await db.get(Order, rating_data.order_id)
        if not order:
            raise HTTPException(status_code = 404, default = "Order details not found.")
        
        if order.user_id != rating_data.user_id:
            raise HTTPException(status_code = 403, detail = "You can only your own orders")
        
        # Check if the order is delivered
        if order.status != OrderStatus.DELIVERED:
            raise HTTPException(status_code = 400, detail = "You can only rate once the order is delivered.")
        
        exisitng_rating = await db.execute(
            select(Rating).where(
                Rating.user_id  == rating_data.user_id,
                Rating.order_id == rating_data.order_id 
            )
        )

        if exisitng_rating.scalar_one_or_none():
            raise HTTPException(status_code = 400, detail = "You have already rated this order")
        
        if not any([rating_data.restaurant_rating, rating_data.delivery_rating, rating_data.food_rating]):
            raise HTTPException(status_code = 400, detail = "At least one rating must be provided.")
        
        rating = Rating(
            user_id           = rating_data.user_id,
            order_id          = rating_data.order_id,
            delivery_agent_id = order.delivery_agent_id,
            restaurant_rating = rating_data.restaurant_rating,
            delivery_rating   = rating_data.delivery_rating,
            food_rating       = rating_data.food_rating,
            comment           = rating_data.comment
        )

        db.add(rating)
        await db.commit()
        await db.refresh(rating)

        #Update the restaurant rating.
        if rating_data.restaurant_rating:
            await update_restaurant_rating(db, order.restaurant_id)

        #Update the delivery agent rating.
        if rating_data.delivery_rating and order.delivery_agent_id:
            await update_delivery_agent_rating(db, order.delivery_agent_id)

        logger.info(f"Rating created for order {rating_data.order_id} by user {rating.user_id}")

        return RatingResponse(
            id                = rating.id,
            user_id           = rating.user_id,
            order_id          = rating.order_id,
            delivery_agent_id = rating.delivery_agent_id,
            restaurant_rating = rating.restaurant_rating,
            delivery_rating   = rating.delivery_rating,
            food_rating       = rating.food_rating,
            comment           = rating.comment,
            created_at        = rating.created_at.isoformat() 
        )

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error creating rating: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error!.")
    
async def update_restaurant_rating(db: AsyncSession, restaurant_id: int):

    """
    Utility function to update the restaurant rating.
    TODO: can be moved to utility folder.
    """

    try: 
        average_rating_query = select(func.avg(Rating.restaurant_rating)).where(Rating.restaurant_rating.isnot(None)).join(Order).where(Order.restaurant_id == restaurant_id)

        query_result   = await db.execute(average_rating_query)
        average_rating = query_result.scalar()

        if average_rating:
            restaurant = await db.get(Restaurant, restaurant_id)
            if restaurant:
                restaurant.rating = round(float(average_rating), 2)
                await db.commit()

    except Exception as error:
        logger.error(f"Error updating restaurant rating: {str(error)}")

async def update_delivery_agent_rating(db: AsyncSession, delivery_agent_id: int):
    """
    function to update the delivery agent rating.
    """ 

    try:
        average_rating_query = select(func.avg(Rating.delivery_rating)).where(
            Rating.delivery_rating.isnot(None),
            Rating.delivery_agent_id == delivery_agent_id
        )

        query_result   = await db.execute(average_rating_query)
        average_rating = query_result.scalar()

        if average_rating:
            delivery_agent = await db.get(DeliveryAgent, delivery_agent_id)
            if delivery_agent:
                delivery_agent.rating = round(float(average_rating), 2)
                await db.commit()

    except Exception as error:
        logger.error(f"Error in updating delivery agent rating: error: {str(error)}")

 
@router.get("/oder/{order_id}", response_model = RatingResponse)
async def get_order_rating(order_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    Get an rating for a specific order using:
    Args:
        order_id
    """

    try: 
        rating_query = select(Rating).where(Rating.order_id == order_id)
        query_result = await db.execute(rating_query)
        rating       = query_result.scalar_one_or_none()

        if not rating:
            raise HTTPException(status_code = 404, detail = "Rating not found for this order")
        
        return RatingResponse(
            id                = rating.id,
            user_id           = rating.user_id,
            order_id          = rating.order_id,
            delivery_agent_id = rating.delivery_agent_id,
            restaurant_rating = rating.restaurant_rating,
            delivery_rating   = rating.delivery_rating,
            food_rating       = rating.food_rating,
            comment           = rating.comment,
            created_at        = rating.created_at.isoformat() 
        )
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error getting rating for order {order_id}: error: {str(error)}")
        raise HTTPException(status_code = 500, detail = "Internal server error!.")