"""
Archivo de configuración centralizado para autenticación NFT
Edita este archivo para cambiar los parámetros de autenticación
"""

# --- CONFIGURACIÓN DE BLOCKCHAIN ---
NFT_CONTRACT_ADDRESS = "0xF4820467171695F4d2760614C77503147A9CB1E8"
BLOCKCHAIN_NAME = "Arbitrum"
ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"

# --- CONFIGURACIÓN DEL SERVIDOR FASTAPI ---
# IMPORTANTE: Cambiar esto a tu URL de Railway cuando despliegues
FASTAPI_SERVER_URL = "https://nft.campamentodefi.com"

# Para Railway, sería algo como:
# FASTAPI_SERVER_URL = "https://tu-proyecto-railway.up.railway.app"

# --- CONFIGURACIÓN DE AUTENTICACIÓN ---
NFT_EXPIRATION_ENABLED = True  # Si True, solo verifica NFTs activos (no caducados)
REQUIRE_ACTIVE_NFT = True  # Si True, requiere al menos 1 NFT activo

# --- CONFIGURACIÓN DE INTERFAZ ---
APP_TITLE = "🏠 Inicio"
APP_ICON = "🔐"
SHOW_NFT_INFO = True  # Mostrar información del NFT después de autenticarse

# --- MENSAJES PERSONALIZABLES ---
MESSAGES = {
    "auth_required": "❌ Acceso Denegado - Debes estar autenticado",
    "no_active_nft": "❌ No tienes un NFT activo en tu billetera",
    "auth_success": "✅ ¡Autenticación completada!",
    "connect_wallet": "🔗 Conectar Billetera",
    "logout": "🚪 Cerrar Sesión",
}
