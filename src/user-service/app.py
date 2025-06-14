from dotenv import load_dotenv
load_dotenv(dotenv_path="src/.env")

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from shared.config.database.config import init_db, close_db, check_db_health
from shared.config.logger.config import get_logger

from routes.restaurants import router as restaurant_router
from routes.orders import router as orders_router
from routes.ratings import router as ratings_router
from routes.users import router as users_router

#Initialize logger
logger = get_logger("user-service-main")

#Create FastAPI app
app = FastAPI(
    title       = "User Service",
    description = "Fd-backend - User service app",
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

# routes
app.include_router(restaurant_router, prefix = "/api/v1/restaurants", tags = ["restaurants"])
app.include_router(orders_router, prefix = "/api/v1/orders", tags = ["orders"])
app.include_router(ratings_router, prefix = "/api/v1/ratings", tags = ["ratings"])
app.include_router(users_router, prefix = "/api/v1/users", tags = ["users"])


@app.on_event("startup")
async def startup():
    """
    Intilalize the neccessary service on startup for now (database service)
    """
    await init_db()
    logger.info("User Service started successfully")

@app.on_event("shutdown")
async def shutdown():
    """
    Close all the open connections for now (database service)
    """
    await close_db()
    logger.info("User service closed")


@app.get("/")
async def root():
    """
    Root end point for the user service.
    """
    return {"service": "User Service", "status": "running", "version": "1.0.0"}

if __name__ == "__main__":

    import uvicorn
    uvicorn.run(
        "app:app",
        host      = "0.0.0.0",
        port      = 8001,
        reload    = True,
        log_level = "info"
    )
