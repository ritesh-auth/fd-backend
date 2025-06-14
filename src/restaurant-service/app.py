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

from routes.restaurants import router as restaurant_router
from routes.menu import router as menu_router
from routes.orders import router as orders_router

#Initialize logger
logger = get_logger("restaurant-service/main")

app = FastAPI(
    title       = "Restaurant Service",
    description = "FD - Backend - Restaunrant service",
    version     =  "1.0.0",
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

app.include_router(restaurant_router, prefix = "/api/v1/restaurants", tags = ["restaurants"])
app.include_router(menu_router, prefix = "/api/v1/menu", tags = ["menu"])
app.include_router(orders_router, prefix = "/api/v1/orders", tags = ["orders"])

@app.on_event("startup")
async def startup():
    """
    Intilalize the neccessary service on startup for now (database service)
    """
    await init_db()
    logger.info("Restaurant Service started successfully")

@app.on_event("shutdown")
async def shutdown():
    """
    Close all the open connections for now (database service)
    """
    await close_db()
    logger.info("Restaurant service closed")


@app.get("/")
async def root():
    """
    Root end point for the user service.
    """
    return {"service": "Restaurant Service", "status": "running", "version": "1.0.0", "auth": "JWT authentication for protected routes"}

if __name__ == "__main__":

    import uvicorn
    uvicorn.run(
        "app:app",
        host      = "0.0.0.0",
        port      = 8002,
        reload    = True,
        log_level = "info"
    )
