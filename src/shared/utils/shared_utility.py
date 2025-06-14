"""
TODO: Add comments
"""
from fastapi import Depends, HTTPException, APIRouter,status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from decimal import Decimal, ROUND_HALF_UP
from typing import Union, Optional, Dict
import httpx
import asyncio
from datetime import datetime, timedelta
import bcrypt
import re
import os

import secrets
import jwt

from dotenv import load_dotenv

from sqlalchemy.ext.asyncio import AsyncSession

from shared.config.database.config import get_async_db
from shared.config.logger.config import get_logger
from shared.models.database.models import Restaurant, User

#Initiate logger
logger = get_logger("utils/shared_utility")

#Initiate router
router = APIRouter()

security = HTTPBearer()

#JWT Configuration.
JWT_SECRET_KEY       = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM        = os.getenv("JWT_ALGORITHM")
JWT_EXPIRATION_HOURS = os.getenv("JWT_EXPIRATION_HOURS")

if not JWT_SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY IS NOT DEFINED IN ENV.")

if len(JWT_SECRET_KEY) < 32:
    raise ValueError("JWT_SECRET_KEY MUST BE 32 CHARACTERS LONG FOR SECURITY.")

#Convert to decimal
def to_decimal(value: Union[float, int, str, Decimal]) -> Decimal:
    """
    TODO: Add comments
    """
    if isinstance(value, Decimal):
        return value.quantize(Decimal('0.01'), rounding = ROUND_HALF_UP)

    decimal_value = Decimal(str(value))
    return decimal_value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


#Convert to float value
def to_float(value: Union[Decimal, float, int, str]) -> float:
    """
    TODO: Add comments
    """
    if value is None:
        return 0.0
    return float(value)

#Calculate total order value of order
def calculate_order_total(items: list) -> Decimal:
    """
    TODO: Add comments
    """
    total = Decimal('0.00')
    for item in items:
        item_price = to_decimal(item.get('price', 0))
        quantity   = int(item.get('quantity', 0))
        total     += item_price * quantity

    return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

#Format currency
def format_currency(amount: Union[Decimal, float], currency_symbol: str = "$") -> str:
    """
    TODO: Add comments
    """
    decimal_amount = to_decimal(amount)
    return f"{currency_symbol}{decimal_amount}"

def validate_price(price: Union[float, str, Decimal]) -> Decimal:
    """
    TODO: Add comments
    """
    decimal_price = to_decimal(price)

    if decimal_price <= 0:
        raise ValueError("Price must be greater than 0")
    if decimal_price > Decimal('99999999.99'):
        raise ValueError("Price is too large")

    return decimal_price

#Calculate average rating
def calculate_average_rating(ratings: list) -> Decimal:
    """
    TODO: Add comments
    """

    if not ratings:
        return Decimal('0.00')

    valid_ratings = [to_decimal(rating) for rating in ratings if rating is not None]

    if not valid_ratings:
        return Decimal('0.00')

    total   = sum(valid_ratings)
    average = total / len(valid_ratings)

    return average.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def add_tax(amount: Union[Decimal, float], tax_rate: float = 0.00) -> Decimal:
    """
    TODO: Add comments
    """
    base_amount    = to_decimal(amount)
    tax_amount     = base_amount * Decimal(str(tax_rate))
    total_with_tax = base_amount + tax_amount

    return total_with_tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def calculate_delivery_fee(distance_in_km: float, base_fee: float = 2.99) -> Decimal:
    """
    Calculate delivery fee based on the kilometer

    Args:
        distance_in_km: Total distance in (kilometer)
        base_fee: The base delivery fees

    Returns:
        >>> calculate_delivery_fee(5.0)
        Decimal('3.99')
    """
    base = to_decimal(base_fee)

    if distance_in_km <= 2:
        return base

    elif distance_in_km <= 5:
        return base + Decimal('1.00')

    elif distance_in_km <= 10:
        return base + Decimal('2.00')

    #After 10km add $0.50 / km
    else:
        extra_distance = distance_in_km - 10
        extra_fee      = Decimal(str(extra_distance)) * Decimal('0.50')

        return base + Decimal('2.00') + extra_fee.quantize(Decimal('0.01'), rounding = ROUND_HALF_UP)
    

def hash_password(password: str) -> str:
    """
    Hash the user password 
    Args:
        password: plain text password
    
    Returns:
        str: Hashed password
    """

    salt   = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)

    return hashed.decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    """
    To verify the password with stored password.
    """

    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    except Exception:
        return False
    
def validate_password_strength(password: str) -> Dict[str, Union[bool, str, list]]:

    """
    Validate the password whether it meets the criteria
    """

    issues = []

    common_passwords = [
        "password", "12345678", "password123", "admin123", "qwerty123",
        "letmein0", "welcome", "monkey", "1234567890"
    ]

    if len(password) < 8:
        issues.append("Password must be at least 8 characters long")

    if not re.search(r"[A-Z]", password):
        issues.append("at least one uppercase letter is required")

    if not re.search(r"[a-z]", password):
        issues.append("at least one lowercase letter is required")
    
    if not re.search(r"\d", password):
        issues.append("at least one number letter is required")

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        issues.append("at least one special character is required")


    if password.lower() in common_passwords:
        issues.append("Password is too easy to guess.Please choose a strong password.")

    if len(set(password)) < len(password) * 0.6:
        issues.append("Password has a repeated characters. please create a unique password.")
    
    is_valid = len(issues) == 0
    message = "Valid password" if is_valid else "Invalid password."

    return {
        "is_valid": is_valid,
        "message": message,
        "issues": issues 
    }

def validate_email(email: str) -> bool:

    """
    TODO: Add comments
    """

    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_phone_number(phone_no: str) -> bool:
    """
    TODO: Add comments
    """

    pattern = r'^(\+1[-.\s]?)?(\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}$'
    return re.match(pattern, phone_no) is not None

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT token for authentication"""

    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours = JWT_EXPIRATION_HOURS)

    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm = JWT_ALGORITHM)

    return encoded_jwt

def verify_jwt_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verify JWT Token and return user id
    """
    # Accept both HTTPAuthorizationCredentials and raw string tokens
    if isinstance(credentials, str):
        token = credentials
    else:
        token = credentials.credentials

    try: 
        payload      = jwt.decode(token, JWT_SECRET_KEY, algorithms = [JWT_ALGORITHM])
        user_id: str = payload.get("sub")

        if user_id is None:
            raise HTTPException(status_code = 401, detail = "Invalid token")
        
        return user_id
    
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code = 401, detail = "Token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code = 401, detail = "Could not validate credentails")
    
async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: AsyncSession                          = Depends(get_async_db)
) -> User: 
    """
    Validate JWT token and return current user.
    """

    try:
        user_id = verify_jwt_token(credentials.credentials)

        if not user_id:
            raise HTTPException(status_code = status.HTTP_401_UNAUTHORIZED, detail = "Invalid token: missing user_id",
                                headers = {"WW-Authenticate": "Bearer"})
        
        #Get the user from database if jwt is valid
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code = status.HTTP_401_UNAUTHORIZED, detail = "User not found.",
                                headers = {"WW-Authenticate": "Bearer"})
        
        #Check if the user is active
        if not user.is_active:
            raise HTTPException(status_code = status.HTTP_401_UNAUTHORIZED, detail = "User is not active",
                                headers = {"WW-Authenticate": "Bearer"})
        
        return user
    
    except Exception as error:
        logger.error(f"JWT validation error, error: {str(error)}")
        raise HTTPException(status_code = status.HTTP_401_UNAUTHORIZED, detail = "Invalid token",
                                headers = {"WW-Authenticate": "Bearer"})
    
async def get_current_user_optional(
        credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error = False)),
        db: AsyncSession = Depends(get_async_db)
) -> Optional[User]:
    
    """Some API can work with and without authentication to 
       handle such kind of API we use this function """
    
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials, db)
    except:
        return None

#########END#############
