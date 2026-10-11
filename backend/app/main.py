from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection, ensure_indexes, ensure_interview_indexes
from app.api.routes import health, auth, admin_interviews, student_interviews, interview_rooms

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_to_mongo()
    await ensure_indexes()
    await ensure_interview_indexes()
    yield
    # Shutdown
    await close_mongo_connection()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Adaptive Interview Intelligence Platform for Vignan University (VFSTR)",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
app.include_router(health.router, prefix=settings.API_V1_STR, tags=["Health"])
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["Authentication"])
app.include_router(admin_interviews.router, prefix=f"{settings.API_V1_STR}/admin/interviews", tags=["Admin Interviews"])
app.include_router(student_interviews.router, prefix=f"{settings.API_V1_STR}/student/interviews", tags=["Student Interviews"])
app.include_router(interview_rooms.router, prefix=f"{settings.API_V1_STR}/interview-rooms", tags=["Interview Rooms"])


@app.get("/")
async def root():
    return {
        "message": "Welcome to Adaptive Interview Intelligence API - VFSTR",
        "docs_url": "/docs",
        "health_url": f"{settings.API_V1_STR}/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
