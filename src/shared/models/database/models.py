#SQLalchemy Imports
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum, Time, Numeric
from sqlalchemy.dialects.mysql import NUMERIC
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from shared.config.database.config import Base

#General Imports
from datetime import datetime, time
import enum
import uuid


#Order status table schema
class OrderStatus(enum.Enum):
    """
    TODO: Add comments later
    """
    PENDING           = "pending"
    ACCEPTED          = "accepted"
    REJECTED          = "rejected"
    PREPARING         = "preparing"
    READY_FOR_PICKUP  = "ready_for_pickup"
    OUT_FOR_DELIVERY  = "out_for_delivery"
    DELIVERED         = "delivered"
    CANCELLED         = "cancelled"

class DeliveryAgentStatus(enum.Enum):

    AVAILABLE = "available"
    BUSY      = "busy"
    OFFLINE   = "offline"

#User table
class User(Base):
    """
    User table containing all user details like
    id, name, email. etc
    """

    __tablename__ = "users"

    id              = Column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True, index=True, )
    name            = Column(String(100), nullable=False)
    email           = Column(String(100), unique=True, index=True, nullable=False)
    phone           = Column(String(15), nullable=False)
    hashed_password = Column(String(255), nullable = False)
    is_active       = Column(Boolean, default=True)
    address         = Column(Text)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    #Relationships
    orders     = relationship("Order", back_populates="user")
    ratings    = relationship("Rating", back_populates="user")

# Restaurant table
class Restaurant(Base):

    """
    TODO: Add comments later
    """
    __tablename__ = "restaurants"

    id          = Column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True, index=True)
    name        = Column(String(100), nullable=False)
    description = Column(Text)
    address     = Column(Text, nullable=False)
    phone       = Column(String(20), nullable=False)
    email       = Column(String(100))
    is_online   = Column(Boolean, default=True)
    rating      = Column(Float, default=0.0)
    owner_id    = Column(UUID(as_uuid=True), ForeignKey("users.id"), default=uuid.uuid4, nullable=False )

    #Working hours config
    opening_time = Column(Time, default=time(10, 0), nullable=False)
    closing_time = Column(Time, default=time(23, 0), nullable=False)
    is_24_hours  = Column(Boolean, default=False)

    #Working days config
    operates_monday    = Column(Boolean, default=True)
    operates_tuesday   = Column(Boolean, default=True)
    operates_wednesday = Column(Boolean, default=True)
    operates_thursday  = Column(Boolean, default=True)
    operates_friday    = Column(Boolean, default=True)
    operates_saturday  = Column(Boolean, default=True)
    operates_sunday    = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    menu_items = relationship("MenuItems", back_populates="restaurant")
    orders     = relationship("Order", back_populates="restaurant")

class MenuItems(Base):
    """
    TODO: Add comments later
    """
    __tablename__ = "menu_items"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    restaurant_id = Column(UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False)
    name          = Column(String(100), nullable=False)
    description   = Column(Text)
    price         = Column(Numeric(10, 2), nullable=False) #
    is_available  = Column(Boolean, default=True)
    category      = Column(String(50))
    image_urls    = Column(String(255))
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    restaurant  = relationship("Restaurant", back_populates="menu_items")
    order_items = relationship("OrderItem", back_populates="menu_item")

class DeliveryAgent(Base):
    """
    TODO: Add comments later
    """

    __tablename__ = "delivery_agents"

    id                  = Column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True, index=True)
    delivery_hero_id    = Column(String(10), unique=True, nullable=False, index=True)
    name                = Column(String(100), nullable=False)
    phone               = Column(String(20), unique=True, nullable=False)
    email               = Column(String(100), unique=True, nullable=False)
    status              = Column(Enum(DeliveryAgentStatus), default=DeliveryAgentStatus.AVAILABLE)
    rating              = Column(Float, default=0.0)
    current_location    = Column(String(255))
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    orders  = relationship("Order", back_populates="delivery_agent")
    ratings = relationship("Rating", back_populates="delivery_agent")

class Order(Base):
    """
    TODO: Add comments later
    """

    __tablename__ = "orders"

    id                    = Column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True, index=True)
    user_id               = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    restaurant_id         = Column(UUID(as_uuid=True), ForeignKey("restaurants.id"), nullable=False)
    delivery_agent_id     = Column(UUID(as_uuid=True), ForeignKey("delivery_agents.id"))
    status                = Column(Enum(OrderStatus), default=OrderStatus.PENDING)
    total_amount          = Column(Numeric(10, 2), nullable=False)
    delivery_address      = Column(Text, nullable=False)
    special_instructions  = Column(Text)
    estimated_delivery    = Column(Integer)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    updated_at            = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user           = relationship("User", back_populates="orders")
    restaurant     = relationship("Restaurant", back_populates="orders")
    delivery_agent = relationship("DeliveryAgent", back_populates="orders")
    order_items    = relationship("OrderItem", back_populates="order")
    ratings        = relationship("Rating", back_populates="order")

class OrderItem(Base):
    """
    TODO: Add comments later
    """
    __tablename__ = "order_items"

    id           = Column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True, index=True)
    order_id     = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    menu_item_id = Column(UUID(as_uuid=True), ForeignKey("menu_items.id"), nullable=False)
    quantity     = Column(Integer, nullable=False)
    price        = Column(Numeric(10, 2), nullable=False)

    # Relationships
    order     = relationship("Order", back_populates="order_items")
    menu_item = relationship("MenuItems", back_populates="order_items")


class Rating(Base):
    """
    """
    __tablename__ = "ratings"

    id                = Column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True, index=True)
    user_id           = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    order_id          = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    delivery_agent_id = Column(UUID(as_uuid=True), ForeignKey("delivery_agents.id"))
    restaurant_rating = Column(Integer)
    delivery_rating   = Column(Integer)
    food_rating       = Column(Integer)
    comment           = Column(Text)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user           = relationship("User", back_populates='ratings')
    order          = relationship("Order", back_populates="ratings")
    delivery_agent = relationship("DeliveryAgent", back_populates="ratings")
