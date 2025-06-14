from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.event.base import slots_dispatcher

#SQLalchemy Imports
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

#general imports
from typing import List, Optional
from datetime import datetime, time
import sys
import os
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

#Getting shared folder imports
from shared.config.database.config import get_async_db
from shared.models.database.models import Restaurant, MenuItems
from shared.config.logger.config import get_logger


logger = get_logger("user-service/restaurants")

router = APIRouter()

#Pydanti models for request and response
#TODO: move this models in separate folder later.

class MenuItemResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    price: float
    is_available: bool
    category: Optional[str]
    image_url: Optional[str]

class WorkingHourResponse(BaseModel):
    opening_time: str
    closing_time: str
    is_24_hours: bool
    operates_monday: bool
    operates_tuesday: bool
    operates_wednesday: bool
    operates_thursday: bool
    operates_friday: bool
    operates_saturday: bool
    operates_sunday: bool

class RestaurantResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    address: str
    phone: str
    email: Optional[str]
    is_online: bool
    rating: float
    working_hours: WorkingHourResponse
    menu_items: List[MenuItemResponse] = []

#Checks restaurant open status
def is_restaurant_open(restaurant: Restaurant, check_timing: datetime) -> bool:
    """
    Check the operating status of the restaurant base on work hours and working days
    Args:
        restaurant: The restaurant for which we need to check the status
        check_timing: 0-23 (hours) and 0-6 (Monday = 0, sunday = 0)
    """
    check_day  = check_timing.weekday()
    check_time = check_timing.time()

    day_operations = [
        restaurant.operates_monday,
        restaurant.operates_tuesday,
        restaurant.operates_wednesday,
        restaurant.operates_thursday,
        restaurant.operates_friday,
        restaurant.operates_saturday,
        restaurant.operates_sunday
    ]

    if not day_operations[check_day]:
        return False

    if restaurant.is_24_hours:
        return True

    opening = restaurant.opening_time
    closing = restaurant.closing_time

    if closing < opening:
        return check_time >= opening or check_time < closing
    else:
        return opening <= check_time < closing

@router.get("/", response_model=List[RestaurantResponse])
async def get_available_restaurants(hour: Optional[int] = Query(default=None, description= "Hours of the day to check restaurant availability"),
                                    minute: Optional[int] = Query(default=None, description="Minute of hours (0-59)"),
                                    day: Optional[int] = Query(default=None, description= "Day of the week(0 = monday, 6 = sunday)"),
                                    db: AsyncSession = Depends(get_async_db)):

    """
    Get all the restaurant available for order based on the hours and day of the week.
    if the hours and day is not provided by default use current time and day
    """

    try:
        current_time = datetime.now()
        check_hour   = hour if hour is not None else current_time.hour
        check_minute = minute if minute is not None else current_time.minute
        check_day    = day if day is not None else current_time.weekday()

        check_datetime = current_time.replace(
            hour        = check_hour,
            minute      = check_minute,
            second      = 0,
            microsecond = 0
        )
        #validate the retrieve parameter for hour and day
        if hour is not None and (hour < 0 or hour > 23):
            logger.error(f"Hour must be between 0 and 23")
            raise HTTPException(status_code=400, detail="Hour must be between 0 and 23")
        if minute is not None and (minute < 0 or minute > 59):
            logger.error("Minute must be between 0 and 59")
            raise HTTPException(status_code = 400, detail = "Minute must be between 0 and 59")
        if day is not None and (day < 0 or day > 6):
            logger.error(f"Day must be between 0 - (Monday) and 6 - (Sunday)")
            raise HTTPException(status_code=400, detail="Day must be between 0 - (Monday) and 6 - (Sunday)")

        query        = select(Restaurant).where(Restaurant.is_online == True)
        result       = await db.execute(query)
        restaurants  = result.scalars().all()

        available_restaurants = []
        for restaurant in restaurants:
            if is_restaurant_open(restaurant, check_datetime):

                #Get all the menu items for the restaurant
                menu_query = select(MenuItems).where(
                    MenuItems.restaurant_id == restaurant.id,
                    MenuItems.is_available == True
                )
                menu_query_result = await db.execute(menu_query)
                menu_items        = menu_query_result.scalars().all()

                restaurant_response = RestaurantResponse(
                    id            = str(restaurant.id),
                    name          = restaurant.name,
                    description   = restaurant.description,
                    address       = restaurant.address,
                    phone         = restaurant.phone,
                    email         = restaurant.email,
                    is_online     = restaurant.is_online,
                    rating        = restaurant.rating,

                    working_hours = WorkingHourResponse(
                        opening_time       = restaurant.opening_time.strftime("%H:%M") if restaurant.opening_time else "00:00",
                        closing_time       = restaurant.closing_time.strftime("%H:%M") if restaurant.closing_time else "00:00",
                        is_24_hours        = restaurant.is_24_hours,
                        operates_monday    = restaurant.operates_monday,
                        operates_tuesday   = restaurant.operates_tuesday,
                        operates_wednesday = restaurant.operates_wednesday,
                        operates_thursday  = restaurant.operates_thursday,
                        operates_friday    = restaurant.operates_friday,
                        operates_saturday  = restaurant.operates_saturday,
                        operates_sunday    = restaurant.operates_sunday
                    ),
                    menu_items = [
                        MenuItemResponse(
                            id           = str(item.id),
                            name         = item.name,
                            description  = item.description,
                            price        = item.price,
                            is_available = item.is_available,
                            category     = item.category,
                            image_url    = item.image_urls

                        ) for item in menu_items
                    ]
                )
                available_restaurants.append(restaurant_response)

        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        logger.info(f"Retrived {len(available_restaurants)} available restaurants which is available now.")
        return available_restaurants
    
    except Exception as error:
        logger.error(f"Error getting available restaurants: {str(error)}")
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.get("/{restaurant_id}")
async def get_restaurant(restaurant_id: str, db: AsyncSession = Depends(get_async_db)):
    """
    TODO: Add comments
    """

    try:
        #The only the particular restaurant which matches the id 
        restaurant_query  = select(Restaurant).where(Restaurant.id == restaurant_id)
        restaurant_result = await db.execute(restaurant_query)
        restaurant        = restaurant_result.scalar_one_or_none()

        if not restaurant:
            logger.error(f"No restaurant with id {restaurant_id} found in database.")
            raise HTTPException(status_code = 404, detail = f"Restaurant with id {restaurant_id} not found.")
        
        menu_query = select(MenuItems).where(
            MenuItems.restaurant_id == restaurant_id,
            MenuItems.is_available  == True
        )
        menu_result = await db.execute(menu_query)
        menu_items  = menu_result.scalars().all()

        return RestaurantResponse(
            id            = str(restaurant.id),
            name          = restaurant.name,
            description   = restaurant.description,
            address       = restaurant.address,
            phone         = restaurant.phone,
            email         = restaurant.email,
            is_online     = restaurant.is_online,
            rating        = restaurant.rating,

            working_hours = WorkingHourResponse(
                opening_time       = restaurant.opening_time.strftime("%H:%M") if restaurant.opening_time else "00:00",
                closing_time       = restaurant.closing_time.strftime("%H:%M") if restaurant.closing_time else "00:00",
                is_24_hours        = restaurant.is_24_hours,
                operates_monday    = restaurant.operates_monday,
                operates_tuesday   = restaurant.operates_tuesday,
                operates_wednesday = restaurant.operates_wednesday,
                operates_thursday  = restaurant.operates_thursday,
                operates_friday    = restaurant.operates_friday,
                operates_saturday  = restaurant.operates_saturday,
                operates_sunday    = restaurant.operates_sunday
            ),
            menu_items = [
                MenuItemResponse(
                    id           = str(item.id),
                    name         = item.name,
                    description  = item.description,
                    price        = item.price,
                    is_available = item.is_available,
                    category     = item.category,
                    image_url    = item.image_urls

                ) for item in menu_items
            ]
        )

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error getting restaurant {restaurant_id}: {str(error)}")
        raise HTTPException(status_code = 500, detail = "Internal server error.")
        

@router.get("/{restaurant_id}/is-open")
async def check_restaurant_availability(
    restaurant_id: str,
    hour: Optional[int]   = Query(default = None, description = "Hour to check "),
    minute: Optional[int] = Query(default = None, description = "minutes for precise availability check"),
    day: Optional[int]    = Query(default = None, description = "Day to check restaurant availabilty" ),
    db: AsyncSession      = Depends(get_async_db)
):

    """
    """
    try:
        restaurant = await db.get(Restaurant, restaurant_id)

        if not restaurant:
            raise HTTPException(status_code = 404, detail = f"Restaurant with id {restaurant_id} is not found!.")
        
        current_time = datetime.now()
        check_hour   = hour if hour is not None else current_time.hour
        check_minute = minute if minute is not None else current_time.minute
        check_day    = day if day is not None else current_time.weekday()

        check_datetime = current_time.replace(
            hour        = check_hour,
            minute      = check_minute,
            second      = 0,
            microsecond = 0
        )

        is_res_open = restaurant.is_online and is_restaurant_open(restaurant, check_datetime)
        day_names   = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        return {
            "restaurant_id": restaurant_id,
            "restaurant_name": restaurant.name,
            "is_restaurant_open": is_res_open,
            "is_online": restaurant.is_online,
            "checked_time": f"{day_names[check_day]} at {check_hour:02d}:{check_minute:02d}",
            "working_hours": {
                "opening_time": restaurant.opening_time.strftime("%H:%M") if restaurant.opening_time else "00:00",
                "closing_time": restaurant.closing_time.strftime("%H:%M") if restaurant.closing_time else "00:00",
                "is_24_hours": restaurant.is_24_hours,
                "operates_today": [
                    restaurant.operates_monday,
                    restaurant.operates_tuesday,
                    restaurant.operates_wednesday,
                    restaurant.operates_thursday,
                    restaurant.operates_friday,
                    restaurant.operates_saturday,
                    restaurant.operates_sunday
                ][check_day]
            }
        }
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error checking the restaurant availability: {str(error)}")
        raise HTTPException(status_code = 500, detail = "Internal server error")
