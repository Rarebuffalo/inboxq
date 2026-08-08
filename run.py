#!/usr/bin/env python
import os
import uvicorn
from app.config import settings, logger


def main() -> None:
    """
    Runner script starting the Uvicorn ASGI server with central configurations.
    """
    logger.info("Initializing ASGI web server environment...")
    
    # Enforce configuration-driven server values
    host = settings.HOST
    port = settings.PORT
    reload_enabled = settings.DEBUG and settings.ENV == "development"
    
    logger.info(f"Starting server on http://{host}:{port} (Reload: {reload_enabled})")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level=settings.LOG_LEVEL.lower()
    )


if __name__ == "__main__":
    main()
