from fastapi import APIRouter

from app.api.routes import (
    accounts,
    admin,
    auth,
    categories,
    closings,
    health,
    lume,
    transaction_crud,
    transactions,
)


api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(accounts.router)
api_router.include_router(categories.router)
api_router.include_router(transactions.router)
api_router.include_router(transaction_crud.router)
api_router.include_router(closings.router)
api_router.include_router(lume.router)
api_router.include_router(admin.router)
