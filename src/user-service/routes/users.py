from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import secrets
from typing import Optional, List
from datetime import datetime, timedelta
from decimal import Decimal
from pydantic import BaseModel, validator, Field


from shared.config.database.config import get_async_db
from shared.config.logger.config import get_logger
from shared.models.database.models import User
from shared.utils.shared_utility import (hash_password, verify_password, validate_password_strength, 
                                         validate_email, validate_phone_number, create_access_token, verify_jwt_token)


#Initializing logger
logger = get_logger("user-service/users")

#Intitializing router
router = APIRouter()

security = HTTPBearer()

#JWT Configuration.
JWT_SECRET_KEY       = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM        = os.getenv("JWT_ALGORITHM")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

if not JWT_SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY IS NOT DEFINED IN ENV.")

if len(JWT_SECRET_KEY) < 32:
    raise ValueError("JWT_SECRET_KEY MUST BE 32 CHARACTERS LONG FOR SECURITY.")

class CreateUser(BaseModel):
    """
    TODO: Add comments
    """

    name: str              = Field(..., min_length = 2, max_length = 100, description = "Full name")
    email: str             = Field(..., description = "Email address")
    phone: str             = Field(..., description = "Phone number")
    password: str          = Field(..., min_length = 8, description = "Password") 
    confirm_password: str  = Field(..., description = "Confirm password")
    address: Optional[str] = Field(None, max_length = 500, description = "Delivery address")

    @validator('name')
    def validate_name(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be empty.")
        if any(char.isdigit() for char in value):
            raise ValueError('Name should not contain numbers')
        return value.strip()
    
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
    
    @validator('confirm_password')
    def match_password(cls, value, values):
        if 'password' in values and value != values['password']:
            raise ValueError('Passwords do not match')
        return value
    
    @validator('password')
    def validate_password_strength(cls, value):
        validation_result = validate_password_strength(value)
        if not validation_result['is_valid']:
            raise ValueError(f"Password is not upto requirements: {', '.join(validation_result['issues'])}")
        return value
    
class UserLogin(BaseModel):
    """
    TODO: Add comments
    """
    email: str    = Field(..., description = "Login Email")
    password: str = Field(..., description = "Password")

    @validator('email')
    def validate_email_format(cls, value):
        if not validate_email(value):
            raise ValueError('Invalid email format.')
        return value.lower()

class UserInformationUpdate(BaseModel):
    """
    """
    name: Optional[str]    = Field(None, min_length = 2, max_length = 100)
    phone: Optional[str]   = Field(None, description = "Phone number")
    address: Optional[str] = Field(None, max_length = 500)

    @validator('name')
    def validate_name(cls, value):
        if not value.strip():
            raise ValueError("Name cannot be empty.")
        if any(char.isdigit() for char in value):
            raise ValueError('Name should not contain numbers')
        return value.strip()
    
    @validator('phone')
    def validate_phone_number_format(cls, value):
        if value is not None and not validate_phone_number(value):
            raise ValueError('Invalid phone number format')
        return value

class ChangePassword(BaseModel):
    """
    """
    current_password: str = Field(..., description = "Current password")
    new_password: str     = Field(..., min_length = 8, description = "new password")
    confirm_password: str = Field(..., description = "Re-Enter new password")

    @validator('confirm_password')
    def match_password(cls, value, values):
        if 'new_password' in values and value != values['new_password']:
            raise ValueError('Passwords do not match')
        return value
    
    @validator('new_password')
    def validate_password_strength(cls, value):
        validation_result = validate_password_strength(value)
        if not validation_result['is_valid']:
            raise ValueError(f"Password is not upto requirements: {', '.join(validation_result['issues'])}")
        return value

class ForgotPasswordRequest(BaseModel):
    """
    """
    email: str = Field(..., description = "email address")

    @validator('email')
    def validate_email_format(cls, value):
        if not validate_email(value):
            raise ValueError('Invalid email format.')
        return value.lower()
    
class ResetPassword(BaseModel):
    """
    """
    email: str            = Field(..., description = "email address")
    reset_token: str      = Field(..., description = "password reset token")
    new_password: str     = Field(..., min_length = 8, description = "new password")
    confirm_password: str = Field(..., description = "Re-Enter new password")

    @validator('email')
    def validate_email_format(cls, value):
        if not validate_email(value):
            raise ValueError('Invalid email format.')
        return value.lower()

    @validator('confirm_password')
    def match_password(cls, value, values):
        if 'new_password' in values and value != values['new_password']:
            raise ValueError('Passwords do not match')
        return value
    
    @validator('new_password')
    def validate_password_strength(cls, value):
        validation_result = validate_password_strength(value)
        if not validation_result['is_valid']:
            raise ValueError(f"Password is not upto requirements: {', '.join(validation_result['issues'])}")
        return value
    
class DeleteAccountRequest(BaseModel):
    """
    """
    password: str     = Field(..., description = "Current for password for verification.")
    confirmation: str = Field(..., description = "Type 'DELETE' to confirm")

    @validator('confirmation')
    def validate_confirmation(cls, value):
        if value != 'DELETE':
            raise ValueError("Type 'DELETE' to confirm account deletion.")

class UserResponse(BaseModel):
    """
    """
    id: str
    name: str
    email: str
    phone: str
    address: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: 'UserResponse'

class UserListResponse(BaseModel):

    id: str
    name: str
    email: str
    phone: str
    is_active: str
    created_at: datetime


#In memory reset tokens - using redis for production is better (use in memory due to time constraints)
reset_tokens = {}

async def get_current_user(user_id: str = Depends(verify_jwt_token), 
                           db: AsyncSession = Depends(get_async_db)) -> User:
    
    """
    Get current user from token.
    """
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code = 401, detail = "User not found or inactive")
    
    return user

async def send_password_reset_email(user_name: str, email: str, reset_token: str):
    """
    Mocking this part for development 
    we can use email services like: zeptomail, SendGrid
    """

    logger.info(f"Password reset email sent to you registered email address.")

    #Demo email content
    email_content = f"""
    Subject: Password Reset Request - Foodies
    
    Dear {user_name},

    You have requested to reset your account password. Please use the following code:
    Reset Token / OTP: {reset_token}

    This token is valid for 5min.

    Best Regards,
    Foodies
    """
    print(f"Email Sent successfully: \n{email_content}")
    logger.info(f"Email Sent successfully: \n{email_content}")

async def send_welcome_mail(email: str, name: str):

    """
    Send welcome mail to all new users.
    """

    logger.info(f"welcome mail sent to {email}")
    print(f"welcome email sent to {name} at registered email")

@router.post("/register-user", response_model = UserResponse)
async def resgister_user(
    user_data: CreateUser,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
):
    """New User registration route."""

    try:
        existing_mail = await db.execute(select(User).where(User.email == user_data.email.lower()))

        if existing_mail.scalar_one_or_none():
            raise HTTPException(status_code = 400, detail = "User with this email already exists. Please login")
        
        existing_phone = await db.execute(select(User).where(User.phone == user_data.phone))

        if existing_phone.scalar_one_or_none():
            raise HTTPException(status_code = 400, detail = "User with this phone number already exists")

        #Hash the user password for better security
        hashed_password = hash_password(user_data.password)

        #Create new user
        user = User(
            name            = user_data.name,
            email           = user_data.email.lower(),
            phone           = user_data.phone,
            hashed_password = hashed_password,
            address         = user_data.address,
            is_active       = True
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)

        #Adding send welcome email to background task.
        background_tasks.add_task(send_welcome_mail, user.email, user.name)

        logger.info(f"New user registered: {user.email}")

        return UserResponse(
            id         = str(user.id),
            name       = user.name,
            email      = user.email, 
            phone      = user.phone,
            address    = user.address,
            is_active  = user.is_active,
            created_at = user.created_at
        )
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error new registering, error: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error")
    
@router.post("/login")
async def login_user(login_data: UserLogin, db: AsyncSession = Depends(get_async_db)):
    """
    Authenticate user with email and password.
    """
    try:
        #Find the user using email.
        user_query   = select(User).where(User.email == login_data.email.lower())
        query_result = await db.execute(user_query)
        user         = query_result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code = 401, detail = "user doesn't exist please register.")
        
        #Check if the user is currently in active state
        if not user.is_active:
            raise HTTPException(status_code = 401, detail = "Account is deactivated, Contact support.")
        
        #verify password

        if not verify_password(login_data.password, user.hashed_password):
            raise HTTPException(status_code = 401, detail = "Invalid email or password")
        
        access_token_expires = timedelta(hours=JWT_EXPIRATION_HOURS)
        access_token         = create_access_token(data = {"sub": str(user.id), "email": user.email}, expires_delta=access_token_expires)

        logger.info(f"User {user.email} logged in successfully")

        return LoginResponse(
            access_token = access_token,
            token_type   = 'Bearer',
            expires_in   = JWT_EXPIRATION_HOURS * 3600, #in seconds
            
            user = UserResponse(
                id         = str(user.id),
                name       = user.name,
                email      = user.email,
                phone      = user.phone,
                address    = user.address,
                is_active  = user.is_active,
                created_at = user.created_at 
            )
        )
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error during login, error: {str(error)}")
        raise HTTPException(status_code = 500, detail = "Internal server error")
    
@router.get("/get-profile/me", response_model = UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):

    """Get current  user's profile information"""

    return UserResponse(
        id         = str(current_user.id),
        name       = current_user.name,
        email      = current_user.email,
        phone      = current_user.phone,
        address    = current_user.address,
        is_active  = current_user.is_active,
        created_at = current_user.created_at 
    )

@router.get("/get-profile/{user_id}", response_model = UserResponse)
async def get_user_profile(user_id: str, db: AsyncSession = Depends(get_async_db)):
    """
    Get user profile information with user_id
    """
    try:
        user = await db.get(User, user_id)

        if not user:
            raise HTTPException(status_code = 404, detail = "User not found.")
        
        return UserResponse(
            id         = str(user.id),
            name       = user.name,
            email      = user.email,
            phone      = user.phone,
            address    = user.address,
            is_active  = user.is_active,
            created_at = user.created_at 
        )
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error getting user profile: {str(error)}")
        raise HTTPException(status_code = 500, detail = "Internal server error.")

@router.put("/update-profile/me", response_model = UserResponse)
async def update_current_user_profile(user_data: UserInformationUpdate, 
                                      current_user: User = Depends(get_current_user), 
                                      db: AsyncSession = Depends(get_async_db)
):
    """Update the current user's profile information."""

    try: 
        if user_data.phone and user_data.phone != current_user.phone:
            existing_phone = await db.execute(
                select(User).where(User.phone == user_data.phone, User.id != current_user.id)
            )

            if existing_phone.scalar_one_or_none():
                raise HTTPException(status_code = 400, detail = "Phone number is already registered.")
            
        if user_data.name is not None:
            current_user.name = user_data.name
        
        if user_data.phone is not None:
            current_user.phone = user_data.phone
        
        if user_data.address is not None:
            current_user.address = user_data.address

        await db.commit()
        await db.refresh(current_user)

        logger.info(f"User profile updated: {current_user.email}")

        return UserResponse(
            id         = str(current_user.id),
            name       = current_user.name,
            email      = current_user.email,
            phone      = current_user.phone,
            address    = current_user.address,
            is_active  = current_user.is_active,
            created_at = current_user.created_at 
        )
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error updating user profile, error: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error.")
    
@router.put("/update-profile/{user_id}", response_model = UserResponse)
async def update_user_profile(user_id: str, user_data: UserInformationUpdate, db: AsyncSession = Depends(get_async_db)):
    """
    Update user profile information (admin end-point)..

    """

    try:
        #Check whether user exists 
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code = 404, detail = "User not found.")
        
        #check if phone number is already taken.
        if user_data.phone and user_data.phone != user.phone:
            existing_phone = await db.execute(
                select(User).where(User.phone == user_data.phone, User.id != user_data.id)
            )

            if existing_phone.scalar_one_or_none():
                raise HTTPException(status_code = 400, detail = "Phone number is already registered.")
            
        if user_data.name is not None:
            user.name = user_data.name
        
        if user_data.phone is not None:
            user.phone = user_data.phone
        
        if user_data.address is not None:
            user.address = user_data.address

        await db.commit()
        await db.refresh(user)

        logger.info(f"User profile updated: {user.email}")

        return UserResponse(
            id         = str(user.id),
            name       = user.name,
            email      = user.email,
            phone      = user.phone,
            address    = user.address,
            is_active  = user.is_active,
            created_at = user.created_at 
        )
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error updating user profile, error: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error.")

@router.patch("/change-password/me")
async def change_current_user_password(
    password_data: ChangePassword,
    current_user:  User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):

    """Change current user password (currently logged in)"""

    try:
        #Check current password is correct / not
        if not verify_password(password_data.current_password, current_user.hashed_password):
            raise HTTPException(status_code = 401, detail = "Current password is incorrect.")

        #hash the new password entered by user.
        current_user.hashed_password = hash_password(password_data.new_password)
        await db.commit()

        logger.info(f"Password changed for user: {current_user.email}")
        return {"message": "Password changed successfully"}

        #In production send mail to the user after changing password

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error changing user password, error: {str(error)}") 
        await db.commit()
        raise HTTPException(status_code = 500, detail = "Internal server error.")

@router.patch("/change-password/{user_id}")
async def change_password(
    user_id: str,
    password_data: ChangePassword,
    db: AsyncSession = Depends(get_async_db)
):
    """Change user password (admin-endpoint)."""

    try: 
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code = 404, detail = "User not found")

        #verify current password
        if not verify_password(password_data.current_password, user.hashed_password):
            raise HTTPException(status_code = 401, detail = "Current password is incorrect")

        #Hash the new password
        user.hashed_password = hash_password(password_data.current_password, user.hashed_password)
        await db.commit() 

        logger.info(f"Password changed for user: {user.email}")
        return {"message": "Password changed successfully"}
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error in changing password, error: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error.")
        
    
@router.post("/forgot-password")
async def forgot_password(request_data: ForgotPasswordRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_async_db)):

    """Request password reset."""

    try:
        #Find the user by mail
        user_query   = select(User).where(User.email == request_data.email.lower())
        query_result = await db.execute(user_query)
        user         = query_result.scalar_one_or_none()

        #We will always return success message for security reasons
        if user and user.is_active:

            reset_token = secrets.token_urlsafe(32)

            reset_tokens[user.email] = {
                'token': reset_token,
                'expires_at': datetime.now() + timedelta(minutes=5),
                'user_id': str(user.id)
            }

            background_tasks.add_task(send_password_reset_email, user.email, reset_token)
            
            logger.info(f"Password reset requested for: {user.email}")

        return {"message": "If the email exists, a password reset link has been sent"}
    
    except Exception as error:
        logger.error(f"Error in forgot password, error: {str(error)}")
        raise HTTPException(status_code = 500, detail = "Internal server error.")
    

@router.post("/reset-password")
async def reset_password(reset_data: ResetPassword, db: AsyncSession = Depends(get_async_db)):
    """"""

    try:
        email = reset_data.email.lower()

        #Check token validity
        if email not in reset_tokens:
            raise HTTPException(status_code = 400, detail = "Invalid or expired reset token.")

        token_data = reset_tokens[email]

        if (token_data['token'] != reset_data.reset_token or datetime.now() > token_data['expires_at']):
            """
            If the reset token is expired remove it.
            """ 
            reset_tokens.pop(email, None)
            raise HTTPException(status_code = 400, detail = "Invalid or expired reset token")
        
        user = await db.get(User, token_data['user_id'])
        if not user or not user.is_active:
            raise HTTPException(status_code = 404, detail = "User not found.") 
        
        user.hashed_password = hash_password(reset_data.new_password)
        await db.commit()


        reset_tokens.pop(email, None)

        logger.info(f"Password reset completed for: {user.email}")
        return {"message": {"Password reset successfully"}}
    
    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error resetting password, error: {str(error)}")
        await db.rollback()
        raise HTTPException(status_code = 500, detail = "Internal server error")

@router.post("/logout")
async def logout_user(current_user: User = Depends(get_current_user)):
    """
    Logout user.
    """

    #In ideal production situation the token must be store to blacklist,
    #so it can't be re-used.

    logger.info(f"User {current_user.email} logged out")
    return {"message": "Successfully logged out"}
