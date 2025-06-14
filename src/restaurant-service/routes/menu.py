from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from typing import List, Optional
from pydantic import BaseModel, validator, Field

from shared.config.database.config import get_async_db
from shared.config.logger.config import get_logger
from shared.models.database.models import MenuItems, Restaurant, User
from shared.utils.shared_utility import verify_jwt_token, to_decimal, to_float, get_current_user, get_current_user_optional


#Initiate logger
logger = get_logger("restaurant-service/menu")

#Initiate router
router = APIRouter()

security = HTTPBearer()

"""TODO: Seperate the pydantic model for more maintainable code"""
#Pydantic Models
class CreateMenuItem(BaseModel):
    restaurant_id: str
    name: str = Field(..., min_length = 2, max_length = 100, description = "Menu Item name")
    description: Optional[str] = Field(None, max_length = 500, description = "Menu item description")
    price: float = Field(..., gt = 0, description = "Price of the be greater than 0")
    category: Optional[str] = Field(None, max_length = 50, description = "Menu category")
    image_urls: Optional[str] = Field(None, description = "Item's image URL")

    @validator('price')
    def validate_price(cls, value):
        if value <= 0:
            raise ValueError('Price must be greater than 0')
        return round(value ,2)

class UpdateMenuItem(BaseModel):
    name: str = Field(..., min_length = 2, max_length = 100, description = "Menu Item name")
    description: Optional[str] = Field(None, max_length = 500, description = "Menu item description")
    price: float = Field(..., gt = 0, description = "Price of the be greater than 0")
    category: Optional[str] = Field(None, max_length = 50, description = "Menu category")
    image_url: Optional[str] = Field(None, description = "Item's image URL")
    is_available: Optional[bool] = Field(None, description = "Item Availability status")

    @validator('price')
    def validate_price(cls, value):
        if value <= 0:
            raise ValueError('Price must be greater than 0')
        return round(value ,2)
    
class MenuItemResponse(BaseModel):
    id: str
    restaurant_id: str
    name: str
    description: Optional[str]
    price: float
    is_available: bool
    category: Optional[str]
    image_url: Optional[str]

@router.post("/create-menu-items", response_model = MenuItemResponse)
async def create_menu_items(
    item_data: CreateMenuItem,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Add a new item to the menu (Authentication is required)"""

    try:
        #check if the restaurant exists
        restaurant = await db.get(Restaurant, item_data.restaurant_id)
        if not restaurant:
            raise HTTPException(status_code = 404, detail = "Restaurant not found")
        
        #check if the user is owner of this particular restaurant
        if str(restaurant.owner_id) != str(current_user.id) and not getattr(current_user, 'is_admin', False):
            raise HTTPException(status_code = 403, detail = "Access denied: you can menu items only if you own the restaurant.")
        

        menu_item = MenuItems(
            restaurant_id = item_data.restaurant_id,
            name          = item_data.name,
            description   = item_data.description,
            price         = to_decimal(item_data.price),
            is_available  = True,
            category      = item_data.category,
            image_urls    = item_data.image_urls
        )

        db.add(menu_item)
        await db.commit()
        await db.refresh(menu_item)

        logger.info(f"Created menu item: {menu_item.name} for restaurant {item_data.restaurant_id} by user: {current_user.id}")

        return MenuItemResponse(
            id            = str(menu_item.id),
            restaurant_id = str(menu_item.restaurant_id),
            name          = menu_item.name,
            description   = menu_item.description,
            price         = to_float(menu_item.price),
            is_available  = menu_item.is_available,
            category      = menu_item.category,
            image_url     = menu_item.image_urls
        )
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error creating menu item: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error.")
    
@router.get("/get-restaurant-menu/{restaurant_id}")
async def get_restaurant_menu(
    restaurant_id: str,
    available_only: bool = False,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession             = Depends(get_async_db)
):
    """Get all menu for a particular restaurant. (public endpoint)"""

    try:
        restaurant = await db.get(Restaurant, restaurant_id)
        
        if not restaurant:
            raise HTTPException(status_code = 404, detail = "Restaurant not found.")
        
        menu_query = select(MenuItems).where(MenuItems.restaurant_id == restaurant_id)

        if not current_user or (str(restaurant.owner_id) != str(current_user.id) and not getattr(current_user, 'is_admin', False)):
            menu_query = menu_query.where(MenuItems.is_available == True)

        elif available_only:
            menu_query = menu_query.where(MenuItems.is_available == True)
        
        menu_query   = menu_query.order_by(MenuItems.category, MenuItems.name)
        query_result = await db.execute(menu_query)
        menu_items   = query_result.scalars().all()

        return [
            MenuItemResponse(
                id            = str(item.id),
                restaurant_id = str(item.restaurant_id),
                name          = item.name,
                description   = item.description,
                price         = to_float(item.price),
                is_available  = item.is_available,
                category      = item.category,
                image_url     = item.image_urls

            ) for item in menu_items
        ] 
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error getting menu for restaurant {restaurant_id}, error: {str(error)}")
        raise HTTPException(status_code = 500, detail = "Internal server error.")

@router.patch("/items/update-status/{item_id}")
async def update_item_status(
    item_id: str,
    is_available: bool,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_async_db)
):
    """Update the availabilty of item in a menu of a particular restaurant"""

    try:
        menu_item = await db.get(MenuItems, item_id)
        if not menu_item:
            raise HTTPException(status_code = 404, detail = "menu item not found.")
        
        restaurant = await db.get(Restaurant, menu_item.restaurant_id)
        if not restaurant:
            raise HTTPException(status_code = 404, detail = "Restaurant not found.")
        
        if str(restaurant.owner_id) != str(current_user.id) and not getattr(current_user, 'is_admin', False):
            raise HTTPException(status_code = 403, detail = "Access denied: you are not allowed update the menu item status." )
        
        menu_item.is_available = is_available
        await db.commit()

        status_text = "available" if is_available else "unavailable"
        logger.info(f"Menu item availabilty status successfully changed to : {status_text} by {current_user.id}")

        return {
            "message": f"Menu item availabilty status successfully changed to : {status_text} by {current_user.id}",
            "item_id": item_id,
            "is_available": is_available
        }
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error updating menu item availabilty status, error: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error.")

@router.delete("/items/delete/{item_id}")
async def delete_menu_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_async_db)
):
    """Delete a menu item (Only authenticate restaurant owner)"""

    try:
        #check if menu item is present.
        menu_item = await db.get(MenuItems, item_id)
        if not menu_item:
            raise HTTPException(status_code = 404, detail = "Menu item not found.")
        
        #check if the restaurant is valid.
        restaurant = await db.get(Restaurant, menu_item.restaurant_id)
        if not restaurant:
            raise HTTPException(status_code = 403, detail = "Restaurant not found")
        
        if str(restaurant.owner_id) != str(current_user.id) and not getattr(current_user, 'is_admin', False):
            raise HTTPException(status_code = 403, detail = "Access denied: you are not allowed to delete this menu. Required admin privileges")
        
        await db.delete(menu_item)
        await db.commit()

        logger.info(f"Deleted menu item {item_id} by user: {current_user.id}")
        return {"message": "Menu item deleted successfully", "item_id": item_id}
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error deleting menu item, error: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error.")
