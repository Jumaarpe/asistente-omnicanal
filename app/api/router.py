from fastapi import APIRouter
from app.api.v1 import health, webhooks, conversations, ai, routing, voice, customers, listener

api_router = APIRouter()

# Inclusión de subrouters con sus prefijos y tags
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(webhooks.router, tags=["Webhooks"])
api_router.include_router(conversations.router)
api_router.include_router(ai.router)
api_router.include_router(routing.router)
api_router.include_router(voice.router)
api_router.include_router(customers.router)
api_router.include_router(listener.router)
