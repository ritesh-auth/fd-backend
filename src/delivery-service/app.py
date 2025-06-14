import sys
import os
from dotenv import load_dotenv

# Load environment variables from src/.env
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config.database.config import init_db, close_db, check_db_health
from shared.config.logger.config import get_logger

from routes.orders import router as orders_router

# Initialize logger
logger = get_logger("delivery-service/main")

app = FastAPI(
    title       = "Delivery Service",
    description = "FD - Backend - Delivery service",
    version     = "1.0.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"]
)

app.include_router(orders_router, prefix="/api/v1/orders", tags=["orders"])

@app.on_event("startup")
async def startup():
    """
    Initialize the necessary service on startup (database service)
    """
    await init_db()
    logger.info("Delivery Service started successfully")

@app.on_event("shutdown")
async def shutdown():
    """
    Close all the open connections (database service)
    """
    await close_db()
    logger.info("Delivery Service closed")

@app.get("/")
async def root():
    """
    Root endpoint for the delivery service.
    """
    return {"service": "Delivery Service", "status": "running", "version": "1.0.0", "auth": "JWT authentication for protected routes"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host      = "0.0.0.0",
        port      = 8003,
        reload    = True,
        log_level = "info"
    )
