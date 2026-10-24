from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logger import logger
from app.api.router import api_router
from app.database.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestor del ciclo de vida del servidor (Startup y Shutdown).
    """
    logger.info("=" * 60)
    logger.info(f"🚀 Iniciando {settings.PROJECT_NAME} v{settings.VERSION}")
    logger.info(f"📍 Entorno: {settings.ENVIRONMENT} | Debug: {settings.DEBUG}")
    logger.info(f"🌐 Host: {settings.HOST}:{settings.PORT}")
    logger.info(f"🔗 Webhook WhatsApp: {settings.API_V1_STR}/webhooks/whatsapp")
    logger.info("=" * 60)
    # Inicialización de esquema de Base de Datos
    await init_db()
    yield
    logger.info(f"🛑 Deteniendo {settings.PROJECT_NAME}...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend del Asistente Virtual Omnicanal de WhatsApp y Voz con Enrutamiento Comercial Inteligente.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de logging de peticiones
@app.middleware("http")
async def log_requests(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    logger.debug(f"Petición entrante: {request.method} {request.url.path} desde {client_ip}")
    response = await call_next(request)
    return response

# Enrutador principal v1
app.include_router(api_router, prefix=settings.API_V1_STR)

# Endpoints directos en raíz para facilidad de acceso y monitoreo
@app.get("/", tags=["Root"])
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "documentation": "/docs",
        "webhook_url": f"{settings.API_V1_STR}/webhooks/whatsapp"
    }


@app.get("/health", tags=["Health"])
async def root_health():
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION
    }


# Manejador global de excepciones no controladas
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Error inesperado en {request.method} {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor", "error": str(exc)}
    )
