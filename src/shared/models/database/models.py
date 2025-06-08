from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum


Base = declarative_base()

#Order status table schema
class OrderStatus(enum.Enum):
    """
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
    BUSY 

