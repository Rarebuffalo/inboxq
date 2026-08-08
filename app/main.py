import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings, logger
from app.database import init_db, get_db, Ticket
from app.schemas import TicketAnalytics
from app.services import ticket_service
from app.routes.tickets import router as tickets_router

# Track startup timestamp for uptime telemetry
STARTUP_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager controlling startup and shutdown events.
    Automatically initializes SQLite database schemas and seeds 50 mock tickets if empty.
    """
    logger.info("Starting up InboxIQ backend services...")
    init_db()
    
    # Auto-seed mock data on startup
    from app.database import SessionLocal
    from app.services.mock_data import seed_mock_data
    db = SessionLocal()
    try:
        seed_mock_data(db)
    except Exception as e:
        logger.error(f"Auto-seeding mock data failed: {e}")
    finally:
        db.close()
        
    yield
    logger.info("Shutting down InboxIQ backend services...")


def create_app() -> FastAPI:
    """
    Application factory initializing the FastAPI application with configurations,
    routers, CORS middleware, static file directories, and exception handlers.
    """
    app = FastAPI(
        title="InboxIQ",
        description="Automated Email Ticket Classification & Prioritization API Engine",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # Cross-Origin Resource Sharing (CORS) setup
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict to specific domains in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Telemetry Middleware: Inject Request IDs and compute Latency processing times
    @app.middleware("http")
    async def add_process_time_and_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start_time = time.time()
        
        # Inject request ID into request context state
        request.state.request_id = request_id
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.6f}"
        response.headers["X-Request-ID"] = request_id
        
        logger.info(
            f"Request: {request.method} {request.url.path} | "
            f"Status: {response.status_code} | "
            f"Latency: {process_time:.4f}s | "
            f"Request-ID: {request_id}"
        )
        return response

    # Register ticket routing domains
    app.include_router(tickets_router, prefix="/api/v1")

    # Configure directory for templates and mount static assets
    templates = Jinja2Templates(directory="app/templates")
    # Workaround: Disable template cache to avoid python 3.14 unhashable dict cache key issue
    templates.env.cache = None
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Global Exception Handling
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            f"Unhandled exception caught during request to {request.url.path}: {exc}", 
            exc_info=True
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred. Please contact the administrator."
            }
        )

    # Core Routes
    @app.get("/health", tags=["Health"], status_code=status.HTTP_200_OK)
    @app.get("/api/v1/health", tags=["Health"], status_code=status.HTTP_200_OK)
    async def health_check(db: Session = Depends(get_db)) -> JSONResponse:
        """
        Comprehensive liveness/readiness probe verifying database connection,
        Gemini configurations, and live queue load metrics.
        """
        db_connected = False
        total_tickets = 0
        active_critical_alerts = 0
        
        try:
            # Query db count to check connection health
            from sqlalchemy import select, func
            total_tickets = db.query(func.count(Ticket.id)).scalar() or 0
            active_critical_alerts = db.query(func.count(Ticket.id)).filter(
                Ticket.priority.in_(["P0", "P1"]),
                Ticket.status.in_(["open", "investigating"])
            ).scalar() or 0
            db_connected = True
        except Exception as e:
            logger.error(f"Healthcheck database ping failure: {e}")
            
        uptime = time.time() - STARTUP_TIME
        gemini_ready = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip())
        
        status_code = status.HTTP_200_OK if db_connected else status.HTTP_503_SERVICE_UNAVAILABLE
        
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "healthy" if db_connected else "unhealthy",
                "database_connected": db_connected,
                "gemini_active": gemini_ready,
                "heuristic_ready": True,
                "uptime_seconds": round(uptime, 2),
                "metrics": {
                    "total_tickets": total_tickets,
                    "active_critical_alerts": active_critical_alerts
                }
            }
        )

    @app.get("/api/v1/analytics/stats", response_model=TicketAnalytics, tags=["Analytics"])
    async def get_stats(db: Session = Depends(get_db)) -> TicketAnalytics:
        """
        Calculates operational aggregates to feed the Ops Analytics interface.
        """
        return ticket_service.get_analytics(db)

    @app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
    async def get_dashboard(request: Request) -> HTMLResponse:
        """
        Renders the main Jinja2-powered live operation queue dashboard.
        """
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"env": settings.ENV}
        )

    return app


# Expose application instance for ASGI servers (Uvicorn)
app = create_app()
