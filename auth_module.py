"""
Módulo de autenticación NFT mejorado para Streamlit
Persiste la autenticación entre páginas usando el servidor FastAPI
"""

import streamlit as st
import requests
import time
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

# --- CONFIGURACIÓN ---
NFT_CONTRACT_ADDRESS = "0xF4820467171695F4d2760614C77503147A9CB1E8"
ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"
FASTAPI_SERVER_URL = "https://privy-moralis-streamlit-production.up.railway.app"  # Cambiar a tu URL de Railway

# --- INICIALIZAR SESSION STATE ---
def init_auth_session():
    """Inicializar variables de sesión para autenticación"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user_wallet' not in st.session_state:
        st.session_state.user_wallet = None
    if 'user_nfts' not in st.session_state:
        st.session_state.user_nfts = None

# --- FUNCIONES DE VERIFICACIÓN ---
def verify_nft_ownership(wallet_address):
    """
    Verifica si una dirección de billetera posee un NFT ACTIVO requerido en Arbitrum.
    Usa la función activeBalanceOf para verificar solo NFTs que no han caducado.
    """
    try:
        w3 = Web3(Web3.HTTPProvider(ARBITRUM_RPC))
        if not w3.is_connected():
            return False, None
        
        ERC721_ABI = [
            {
                "constant": True,
                "inputs": [{"name": "owner", "type": "address"}],
                "name": "activeBalanceOf",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function"
            }
        ]
        
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(NFT_CONTRACT_ADDRESS),
            abi=ERC721_ABI
        )
        
        active_balance = contract.functions.activeBalanceOf(Web3.to_checksum_address(wallet_address)).call()
        
        if active_balance > 0:
            return True, {"active_balance": active_balance, "contract": NFT_CONTRACT_ADDRESS}
        else:
            return False, None
            
    except Exception as e:
        return False, None

def verify_signature(wallet_address, message, signature):
    """
    Verifica que la firma fue creada por la billetera especificada.
    """
    try:
        message_hash = encode_defunct(text=message)
        recovered_address = Account.recover_message(message_hash, signature=signature)
        return recovered_address.lower() == wallet_address.lower()
    except Exception as e:
        return False

def check_auth_on_server(wallet_address):
    """
    Consultar el servidor FastAPI para ver si hay datos de autenticación.
    """
    try:
        response = requests.get(
            f"{FASTAPI_SERVER_URL}/api/auth/check/{wallet_address}",
            timeout=5
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"authenticated": False}
    except Exception as e:
        return {"authenticated": False}

def clear_auth_on_server(wallet_address):
    """
    Limpiar datos de autenticación del servidor.
    """
    try:
        requests.delete(
            f"{FASTAPI_SERVER_URL}/api/auth/clear/{wallet_address}",
            timeout=5
        )
    except:
        pass

def restore_auth_from_server():
    """
    Restaurar autenticación desde el servidor FastAPI.
    Esto se ejecuta en cada página para verificar si el usuario ya está autenticado.
    """
    init_auth_session()
    
    # Si ya está autenticado en esta sesión, no hacer nada
    if st.session_state.authenticated:
        return True
    
    # Intentar restaurar desde el servidor
    # Buscar en todas las sesiones activas del servidor
    try:
        response = requests.get(
            f"{FASTAPI_SERVER_URL}/api/debug/sessions",
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            sessions = data.get("sessions", [])
            
            # Si hay al menos una sesión activa, usar la primera
            if sessions:
                wallet_address = sessions[0]
                auth_result = check_auth_on_server(wallet_address)
                
                if auth_result.get("authenticated"):
                    # Verificar NFT
                    has_active_nft, nfts = verify_nft_ownership(wallet_address)
                    if has_active_nft:
                        st.session_state.authenticated = True
                        st.session_state.user_wallet = wallet_address
                        st.session_state.user_nfts = nfts
                        return True
    except:
        pass
    
    return False

# --- FUNCIÓN DE PROTECCIÓN DE PÁGINA ---
def require_nft_authentication():
    """
    Función que debe ser llamada al inicio de cada página protegida.
    Verifica si el usuario está autenticado y tiene NFT activo.
    Si no, muestra un mensaje y detiene la ejecución de la página.
    
    Retorna: True si el usuario está autenticado, False si no
    """
    init_auth_session()
    
    # Intentar restaurar autenticación desde el servidor
    if not st.session_state.authenticated:
        restore_auth_from_server()
    
    if not st.session_state.authenticated:
        st.error("❌ Acceso Denegado")
        st.warning("Debes estar autenticado y poseer un NFT activo para acceder a esta página.")
        st.info("Por favor, ve a la página de inicio (🏠 Inicio) para autenticarte.")
        st.stop()
    
    return True

# --- INTERFAZ DE AUTENTICACIÓN ---
def show_auth_interface():
    """
    Muestra la interfaz de autenticación (para usar en la página principal)
    """
    init_auth_session()
    
    # Intentar restaurar autenticación desde el servidor
    if not st.session_state.authenticated:
        restore_auth_from_server()
    
    if st.session_state.authenticated:
        # Usuario autenticado - mostrar información y botón de logout
        st.success("✅ ¡Autenticación y verificación completadas! Bienvenido.")
        st.balloons()
        
        st.info(f"Billetera conectada: `{st.session_state.user_wallet}`")
        
        if st.session_state.user_nfts:
            st.subheader("📜 Información del NFT Activo")
            st.write(f"**Balance Activo:** {st.session_state.user_nfts.get('active_balance', 0)} NFT(s) activo(s)")
            st.write(f"**Contrato:** `{st.session_state.user_nfts.get('contract', 'N/A')}`")
            st.caption("💡 Solo se cuentan los NFTs que no han caducado")
        
        if st.button("🚪 Cerrar Sesión"):
            clear_auth_on_server(st.session_state.user_wallet)
            st.session_state.authenticated = False
            st.session_state.user_wallet = None
            st.session_state.user_nfts = None
            st.rerun()
    else:
        # Usuario no autenticado - mostrar interfaz de login
        st.subheader("Paso 1: Conecta tu Billetera")
        st.caption("Haz clic en el botón para abrir la ventana de autenticación.")
        
        st.link_button("🔗 Conectar Billetera", f"{FASTAPI_SERVER_URL}")
        
        st.info("Después de autenticarte, vuelve a esta página y pega tu dirección de billetera en el campo de abajo.")
        
        st.divider()
        st.subheader("Paso 2: Verifica tu Autenticación")
        st.caption("Pega tu dirección de billetera después de autenticarte:")
        
        wallet_input = st.text_input("Dirección de billetera (0x...):")
        
        if wallet_input:
            if not wallet_input.startswith("0x") or len(wallet_input) != 42:
                st.error("❌ Dirección inválida. Debe empezar con 0x y tener 42 caracteres.")
            else:
                with st.spinner("🔍 Verificando autenticación y NFT activo..."):
                    auth_result = check_auth_on_server(wallet_input)
                    
                    if auth_result.get("authenticated"):
                        wallet_address = auth_result.get("wallet")
                        signature = auth_result.get("signature")
                        message = auth_result.get("message")
                        
                        if verify_signature(wallet_address, message, signature):
                            st.success(f"✅ Firma verificada. Billetera: `{wallet_address}`")
                            
                            has_active_nft, nfts = verify_nft_ownership(wallet_address)
                            if has_active_nft:
                                st.session_state.authenticated = True
                                st.session_state.user_wallet = wallet_address
                                st.session_state.user_nfts = nfts
                                st.success("✅ ¡NFT activo verificado! Acceso concedido.")
                                st.balloons()
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.warning("❌ Acceso Denegado")
                                st.error("La billetera conectada no posee un NFT ACTIVO en Arbitrum.")
                                st.info("💡 Nota: Solo se concede acceso si tienes al menos 1 NFT activo (no caducado).")
                                st.info(f"Contrato requerido: `{NFT_CONTRACT_ADDRESS}`")
                                st.info(f"Red: Arbitrum")
                        else:
                            st.error("❌ La firma no es válida")
                    else:
                        st.warning("⚠️ No se encontraron datos de autenticación para esta billetera.")
                        st.info("Asegúrate de haber completado el proceso de autenticación en la ventana emergente.")
                        st.info("Si ya completaste el proceso, intenta pegar tu dirección de nuevo.")
