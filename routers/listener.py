"""
Módulo de compatibilidad y alias para el Modo Oyente (Escucha Pasiva de Vendedores).
Reexporta el router oficial ubicado en app/api/v1/listener.py para mantener consistencia
con cualquier convención de importación 'routers.listener'.
"""
from app.api.v1.listener import router

__all__ = ["router"]
