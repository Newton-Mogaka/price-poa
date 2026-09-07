from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
import logging

# Add project root to sys.path dynamically
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import Telegram webhook router
from telegram_webhook import router as telegram_router
from telegram_bot import set_telegram_webhook

# Import admin routes
from admin import admin_router

# Import Redis cache
from redis_cache import init_redis_cache, close_redis_cache

# Logging
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)

# Create app
app = FastAPI(
    title="PricePoa API",
    description="AI agent for Kenyan grocery price comparisons"
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Include Telegram webhook routes
app.include_router(telegram_router)

# Include admin routes
app.include_router(admin_router)


@app.on_event("startup")
async def startup_event():
    """
    Auto-register the webhook on boot and initialize Redis cache.
    """
    # Initialize Redis cache
    await init_redis_cache()

    # Auto-register the webhook on boot
    webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL", "")
    if not webhook_url:
        logger.warning("TELEGRAM_WEBHOOK_URL not set - skipping webhook registration")
    else:
        success = set_telegram_webhook(webhook_url)
        if not success:
            logger.error("Telegram webhook registration failed on startup")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up services on shutdown."""
    await close_redis_cache()


@app.get("/")
async def root():
    return {"message": "PricePoa API is running"}


@app.get("/health")
async def health_check():
    # Check MongoDB connection
    mongodb_uri = os.getenv("MONGODB_URI", "not_set")
    mongodb_db = os.getenv("MONGODB_DB", "not_set")

    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "api",
            "mongodb_uri": mongodb_uri,
            "mongodb_db": mongodb_db
        }
    )
