from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import List, Optional
from pydantic import BaseModel, validator, Field

from shared.config.database.config import get_async_db
from shared.config.logger.config import get_logger
from shared.models.database.models import Restaurant, User
from shared.utils.shared_utility import verify_jwt_token, validate_email, validate_phone_number, get_current_user, get_current_user_optional

#Initiate logger
logger = get_logger("restaurant-service/restaurants")

#Initiate router
router = APIRouter()

security = HTTPBearer()


#Pydantic Models
class CreateRestaurant(BaseModel):
    """
    TODO: Add comments
    """

    name: str                  = Field(..., min_length = 2, max_length = 100, description = "Restaurant name")
    description: Optional[str] = Field(None, max_length = 500, description = "Restaurant description")
    email: str                 = Field(..., description = "Restaurant email")
    phone: str                 = Field(..., description = "Restaurant Phone number")
    address: Optional[str]     = Field(None, max_length = 500, description = "Restaurantaddress")

    @validator('email')
    def validate_email_format(cls, value):
        if not validate_email(value):
            raise ValueError('Invalid email format')
        return value.lower()
    
    @validator('phone')
    def validate_phone_number_format(cls, value):
        if value is not None and not validate_phone_number(value):
            raise ValueError('Invalid phone number format')
        return value

class UpdateRestaurantInformation(BaseModel):
    """
    TODO: Add comments
    """

    name: str                  = Field(...,  min_length  = 2, max_length = 100, description = "Restaurant name")
    description: Optional[str] = Field(None, max_length  = 500, description = "Restaurant description")
    email: str                 = Field(...,  description = "Restaurant email")
    phone: str                 = Field(...,  description = "Restaurant Phone number")
    address: Optional[str]     = Field(None, max_length  = 500, description = "Restaurantaddress")
    is_online: Optional[bool]  = Field(None, description = "Restaurant availability status")

    @validator('email')
    def validate_email_format(cls, value):
        if not validate_email(value):
            raise ValueError('Invalid email format')
        return value.lower()
    
    @validator('phone')
    def validate_phone_number_format(cls, value):
        if value is not None and not validate_phone_number(value):
            raise ValueError('Invalid phone number format')
        return value

class RestaunrantResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    address: str
    phone: str
    email: Optional[str]
    is_online: bool
    rating: float
    owner_id: Optional[str] = None

@router.post("/register", response_model = RestaunrantResponse)
async def create_restaurant(
    restaurant_data: CreateRestaurant,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_async_db)
):
    """Create a new restaurant"""
    try:
        #Check if the restaurant already exists
        exisiting_restaurant = await db.execute(
            select(Restaurant).where(
                Restaurant.name    == restaurant_data.name,
                Restaurant.address == restaurant_data.address
            )
        )

        if exisiting_restaurant.scalar_one_or_none():
            raise HTTPException(status_code = 400, detail = "Restaurant with this name and address already exists.")
        
        restaurant = Restaurant(
            name        = restaurant_data.name,
            description = restaurant_data.description,
            address     = restaurant_data.address,
            phone       = restaurant_data.phone,
            email       = restaurant_data.email,
            owner_id    = str(current_user.id),
            is_online   = True,
            rating      = 0.0
        )

        db.add(restaurant)
        await db.commit()
        await db.refresh(restaurant)

        logger.info(f"Restaurant successfully registered. restaurant-name: {restaurant.name}, owner-id: {current_user.id}")
        return RestaunrantResponse(
            id          = str(restaurant.id),
            name        = restaurant.name,
            description = restaurant.description,
            address     = restaurant.address,
            phone       = restaurant.phone,
            email       = restaurant.email,
            is_online   = restaurant.is_online,
            rating      = restaurant.rating,
            owner_id    = str(restaurant.owner_id)
        )
    
    except HTTPException:
        raise
    except Exception as error:
        logger.info(f"Error creating restaurant, error:{str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error.")

@router.get("/get-all-restaurants", response_model = List[RestaunrantResponse])
async def get_all_restaurant(
        current_user: Optional[User] = Depends(get_current_user_optional),
        db: AsyncSession = Depends(get_async_db)
):
    
    """Get all restaurants, (but show restaurant owner information if jwt is provided)"""

    try:
        restaurant_query = select(Restaurant).order_by(Restaurant.created_at.desc())
        query_result     = await db.execute(restaurant_query)
        restaurants      = query_result.scalars().all()

        return [
            RestaunrantResponse(
                id          = str(restaurant.id),
                name        = restaurant.name,
                description = restaurant.description,
                address     = restaurant.address,
                phone       = restaurant.phone,
                email       = restaurant.email,
                is_online   = restaurant.is_online,
                rating      = restaurant.rating,
                owner_id    = str(restaurant.owner_id) if current_user and (
                    str(restaurant.owner_id) == str(current_user.id) or 
                    getattr(current_user, 'is_admin', False)
                ) else None
            ) for restaurant in restaurants
        ]
    
    except Exception as error: 
        logger.error(f"Error getting restaurants, error: {str(error)}")
        raise HTTPException(status_code = 500, detail = "Internal server error")
    
@router.patch("/update-status/{restaurant_id}")
async def update_restaurant_status(
    restaurant_id: str,
    is_online: bool,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_async_db)
): 
    """Update restaurant status whether it is (Online / Offline) only authorized users"""

    try: 
        restaurant = await db.get(Restaurant, restaurant_id)
        if not restaurant:
            raise HTTPException(status_code = 404, detail = "Restaurant not found")
        
        if str(restaurant.owner_id) != str(current_user.id) and not getattr(current_user, 'is_admin', False):
            raise HTTPException(status_code = 403, detail = "Access denied: you only update statuses of restaurant which you own or you must be a admin.")
        
        restaurant.is_online = is_online
        await db.commit()

        status_text = "online" if is_online else "offline"
        logger.info(f"Restaurant {restaurant_id} status updated to {status_text} by user {current_user.id}")

        return {
            "message": f"Restaurant status updated to {status_text}",
            "restaurant_id": restaurant_id,
            "is_online": is_online
        }
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error updating restaurant status, error: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error")
    

@router.delete("/delete/{restaurant_id}")
async def delete_restaurant(
    restaurant_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a restaurant only by authorized user"""

    try: 
        restaurant = await db.get(Restaurant, restaurant_id)
        if not restaurant:
            raise HTTPException(status_code = 404, detail = "Restaurant not found")
        
        if str(restaurant.owner_id) != str(current_user.id) and not getattr(current_user, 'is_admin', False):
            raise HTTPException(status_code = 403, detail = "Access denied: you only delete restaurants which you own. contact admin!")
        
        await db.delete(restaurant)
        await db.commit()

        logger.info(f"Restaurant {restaurant_id} deleted successfully by user: {current_user.id}")
        return {"message": "Restaurant successfully deleted", "restaurant_id": restaurant_id}
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error deleting restaurant, error: {str(error)}")
        await db.rollback
        raise HTTPException(status_code = 500, detail = "Internal server error.")
