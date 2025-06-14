import os
from typing import AsyncGenerator
from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import QueuePool

from shared.config.logger.config import get_logger

logger = get_logger(__name__)

DATABASE_URL = os.getenv("FD_BACKEND_DATABASE_URL")
ASYNC_DATABASE_URL = os.getenv("FD_BACKEND_ASYNC_DB_URL")

#Sqlalchemy setup
metadata = MetaData()
Base     = declarative_base(metadata = metadata)

# Ensure all models are registered with Base before any create_all/drop_all
from shared.models.database import models

sync_engine = create_engine(
    DATABASE_URL,
    poolclass      = QueuePool,
    pool_size      = 20,
    max_overflow   = 30,
    pool_pre_ping  = True,
    echo           = False
)

if ASYNC_DATABASE_URL:
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL, 
        pool_size      = 20,
        max_overflow   = 30,
        pool_pre_ping  = True,
        echo           = False
    )
else:
    async_engine = None
    logger.warning("ASYNC_DATABASE_URL is not set. Async database features will be unavailable.")

SessionLocal = sessionmaker(
    autocommit = False,
    autoflush  = False,
    bind       = sync_engine
)

AsyncSessionLocal = async_sessionmaker(
    bind             = async_engine,
    class_           = AsyncSession,
    autocommit       = False,
    autoflush        = False,
    expire_on_commit = False
)

def get_sync_db() -> Session:
    """
    TODO: Add comments
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as error:
        logger.error(f"Database session error: {str(error)}")
        db.rollback()
        raise
    finally:
        db.close()

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    TODO: Add comments
    """

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as error:
            logger.error(f"Async database session error: {str(error)}")
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """
    TODO: Add comments
    """
    if async_engine is None:
        logger.error("Cannot initialize async database: ASYNC_DATABASE_URL is not set.")
        return
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully.")
    except Exception as error:
        logger.error(f"Error creating database tables: {str(error)}")
        raise

async def close_db():
    """
    TODO: Add comments
    """ 
    try:
        await async_engine.dispose()
        sync_engine.dispose()
        logger.info("Database connections closed successfully.")
    
    except Exception as error:
        logger.error(f"Error closing database connections: {str(error)}")
    
async def check_db_health() -> bool:
    """
    TODO: Add comments
    """

    try:
        async with AsyncSessionLocal() as session:
            await session.execute("SELECT ")
        return True
    
    except Exception as error:
        logger.error(f"Database health check failed: {str(error)}")
        return False
    
class DatabaseManager:

    """
    TODO: Add comments
    """

    @staticmethod
    async def create_table():
        """
        Create all the tables from the predefined schema
        """
        await init_db()
    
    @staticmethod
    async def drop_tables():
        """
        Drop all the tables 
        """
        try:
            async with async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            logger.warning("All database tables dropped.")
        
        except Exception as error:
            logger.error(f"Error dropping tables: {str(error)}")
    
    @staticmethod
    async def reset_database():
        """
        Reset database for a fresh table instances
        """
        await DatabaseManager.drop_tables()
        await DatabaseManager.create_table()
        logger.info("Database reset completed")
