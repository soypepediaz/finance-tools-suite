import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from datetime import date, timedelta
from web3 import Web3
import requests
import os
import json

# ==============================================================================
#  CONFIGURACIÓN DE LA PÁGINA Y ESTILOS
# ==============================================================================
st.set_page_config(
    page_title="Looping Master - Final",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS para limpiar la interfaz
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stDeployButton {display:none;}
            
            /* Estilo para tarjetas */
            div[data-testid="column"] {
                padding: 10px;
            }
            
            div[data-testid="stMetric"] {
                background-color: #F0F2F6;
                padding: 15px;
                border-radius: 10px;
                border: 1px solid #E0E0E0;
            }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

st.title("🛡️ Looping Master: Calculadora, Backtest & On-Chain")

# ==============================================================================
#  0. GESTIÓN DE SECRETOS (BLINDADA PARA RAILWAY/RENDER)
# ==============================================================================
def get_secret(key):
    """
    Recupera una clave secreta de forma segura.
    PRIORIDAD 1: Variables de Entorno (Railway/Render/Docker).
    PRIORIDAD 2: Secrets TOML (Local/Streamlit Cloud).
    """
    # 1. Intentar leer del sistema operativo (Railway usa esto)
    env_val = os.environ.get(key)
    if env_val is not None:
        return env_val
    
    # 2. Si no está en el sistema, intentar leer de st.secrets con protección
    try:
        if key in st.secrets:
            return st.secrets[key]
    except FileNotFoundError:
        pass # No existe secrets.toml, ignoramos
    except Exception:
        pass # Cualquier otro error de Streamlit, ignoramos
        
    return None

# ==============================================================================
#  MARKETING (MOOSEND)
# ==============================================================================
MOOSEND_LIST_ID = "75c61863-63dc-4fd3-9ed8-856aee90d04a"

def add_subscriber_moosend(name, email):
    """Envía el suscriptor a la lista de Moosend vía API"""
    try:
        # Usamos la función segura get_secret
        api_key = get_secret("MOOSEND_API_KEY")
        
        if not api_key:
            return False, "Falta configuración de API Key (MOOSEND_API_KEY)."
            
        url = f"https://api.moosend.com/v3/subscribers/{MOOSEND_LIST_ID}/subscribe.json?apikey={api_key}"
        
        headers = {
            'Content-Type': 'application/json', 
            'Accept': 'application/json'
        }
        
        payload = {
            "Name": name,
            "Email": email,
            "HasExternalDoubleOptIn": False
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            return True, "Success"
        else:
            try:
                error_msg = response.json().get("Error", "Unknown Error")
            except:
                error_msg = str(response.status_code)
            return False, error_msg
    except Exception as e:
        return False, str(e)

# ==============================================================================
#  1. CONFIGURACIÓN DE REDES
# ==============================================================================
NETWORKS = {
    "Base": {
        "chain_id": 8453,
        "rpcs": ["https://base.drpc.org", "https://mainnet.base.org", "https://base-rpc.publicnode.com"],
        "pool_provider": "0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D"
    },
    "Arbitrum": {
        "chain_id": 42161,
        "rpcs": ["https://arb1.arbitrum.io/rpc", "https://rpc.ankr.com/arbitrum"],
        "pool_provider": "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb"
    },
    "Ethereum": {
        "chain_id": 1,
        "rpcs": ["https://eth.llamarpc.com", "https://rpc.ankr.com/eth"], 
        "pool_provider": "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e"
    },
    "Optimism": {
        "chain_id": 10,
        "rpcs": ["https://mainnet.optimism.io", "https://rpc.ankr.com/optimism"],
        "pool_provider": "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb"
    },
    "Polygon": {
        "chain_id": 137,
        "rpcs": ["https://polygon-rpc.com", "https://rpc.ankr.com/polygon"],
        "pool_provider": "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb"
    },
    "Avalanche": {
        "chain_id": 43114,
        "rpcs": ["https://api.avax.network/ext/bc/C/rpc"],
        "pool_provider": "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb"
    }
}

# ABI LIGERO
AAVE_ABI = [
    {
        "inputs": [],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
        "name": "getUserAccountData",
        "outputs": [
            {"internalType": "uint256", "name": "totalCollateralBase", "type": "uint256"},
            {"internalType": "uint256", "name": "totalDebtBase", "type": "uint256"},
            {"internalType": "uint256", "name": "availableBorrowsBase", "type": "uint256"},
            {"internalType": "uint256", "name": "currentLiquidationThreshold", "type": "uint256"},
            {"internalType": "uint256", "name": "ltv", "type": "uint256"},
            {"internalType": "uint256", "name": "healthFactor", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

ASSET_MAP = {
    "Bitcoin (WBTC/BTC)": "BTC-USD", 
    "Ethereum (WETH/ETH)": "ETH-USD", 
    "Arbitrum (ARB)": "ARB-USD", 
    "Base (ETH)": "ETH-USD", 
    "Solana (SOL)": "SOL-USD", 
    "Link (LINK)": "LINK-USD", 
    "✍️ Otro": "MANUAL"
}

# ==============================================================================
#  2. FUNCIONES AUXILIARES
# ==============================================================================

def get_web3_session(rpc_url):
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36'})
    # Timeout de 60s para evitar cortes en redes congestionadas
    return Web3(Web3.HTTPProvider(rpc_url, session=s, request_kwargs={'timeout': 60}))

def connect_robust(network_name):
    config = NETWORKS[network_name]
    rpcs = config["rpcs"][:]
    
    # Inyectar secreto de Railway/Streamlit usando get_secret
    secret_key = f"{network_name.upper()}_RPC_URL"
    private_rpc = get_secret(secret_key)
    
    used_private = False
    if private_rpc:
        # Limpieza agresiva de comillas o espacios
        clean_rpc = private_rpc.strip().replace('"', '').replace("'", "")
        rpcs.insert(0, clean_rpc)
        used_private = True
        
    for rpc in rpcs:
        try:
            w3 = get_web3_session(rpc)
            if w3.is_connected():
                if w3.eth.chain_id == config["chain_id"]:
                    return w3, rpc, used_private
        except: 
            continue
            
    return None, None, False

# -----------------------------------------------------------------------------
# FUNCIÓN DE SIMULACIÓN (MOVIDA AQUÍ PARA LIMPIEZA Y ALCANCE CORRECTO)
# -----------------------------------------------------------------------------
def simulacion_seccion():
    # --- SECCIÓN 1: ABRIMOS LA POSICIÓN ---
    st.subheader("1. Configuración de Apertura de Posición")
    
    col1, col2 = st.columns(2)
    
    with col1:
        tipo_posicion = st.radio("¿Qué estrategia quieres realizar?", ["Largo (Long)", "Corto (Short)"], horizontal=True)
        inversion_usdc = st.number_input("Inversión inicial (USDC)", min_value=0.0, value=100000.0, step=1000.0)
        
        # Definición de activos según la posición
        if "Largo" in tipo_posicion:
            lbl_precio = "Precio actual del Activo Volátil (ej. BTC)"
            lbl_colateral = "Activo Volátil"
            lbl_deuda = "USDC"
        else:
            lbl_precio = "Precio actual del Activo Volátil (a tomar prestado)"
            lbl_colateral = "USDC"
            lbl_deuda = "Activo Volátil"
            
        precio_activo_inicial = st.number_input(lbl_precio, min_value=0.0001, value=65000.0, step=10.0)

        # CÁLCULO Y VISUALIZACIÓN DEL COLATERAL DE PARTIDA
        colateral_base_qty_calc = 0
        if "Largo" in tipo_posicion:
            colateral_base_qty_calc = inversion_usdc / precio_activo_inicial
            st.caption(f"🔵 Tienes un total de **{colateral_base_qty_calc:,.4f} {lbl_colateral}** de partida (Inversión / Precio).")
        else:
            colateral_base_qty_calc = inversion_usdc
            st.caption(f"🔵 Tienes un total de **${colateral_base_qty_calc:,.2f} {lbl_colateral}** de partida.")


    with col2:
        ltv_liquidacion = st.slider("LTV de Liquidación del Protocolo (%)", 0, 100, 78) / 100
        umbral_defensa = st.slider("Umbral de defensa (%)", 5, 25, 10) / 100
        borrow_rate = st.slider("Borrow Rate (APY - Interés Anual) (%)", 0, 30, 5) / 100

    st.markdown("---")
    st.markdown("**Nivel de Apalancamiento**")
    
    c_lev1, c_lev2, c_lev3 = st.columns(3)
    
    with c_lev1:
        modo_apalancamiento = st.radio("Modo de selección:", ["Multiplicador (x)", "Cantidad de Deuda"], horizontal=True)
    
    with c_lev2:
        # Cálculo preliminar de colateral base (Redundante pero necesario para scope local limpio)
        colateral_base_qty = 0
        colateral_base_usd = 0
        
        if "Largo" in tipo_posicion:
            colateral_base_usd = inversion_usdc
            colateral_base_qty = inversion_usdc / precio_activo_inicial
        else:
            colateral_base_usd = inversion_usdc
            colateral_base_qty = inversion_usdc # Son USDC
            
        deuda_solicitada_usd = 0
        
        if modo_apalancamiento == "Multiplicador (x)":
            multiplicador = st.number_input("Selecciona apalancamiento (1x = sin deuda)", 1.0, 10.0, 2.0, 0.1)
            if multiplicador > 1:
                deuda_solicitada_usd = inversion_usdc * (multiplicador - 1)
        else:
            max_borrow = inversion_usdc * 10 
            deuda_input = st.number_input(f"Cantidad de deuda en {lbl_deuda}", 0.0, max_borrow, 0.0)
            if "Largo" in tipo_posicion:
                deuda_solicitada_usd = deuda_input 
            else:
                deuda_solicitada_usd = deuda_input * precio_activo_inicial

    with c_lev3:
        hacer_looping = st.checkbox("¿Hacer Looping?", value=True, help="Si marcas esto, la deuda se usa para comprar más colateral (Largo) o se vende para aumentar colateral estable (Corto).")

    # --- CÁLCULOS INICIALES ---
    collateral_final_qty = colateral_base_qty
    deuda_final_qty = 0 
    
    if hacer_looping:
        if "Largo" in tipo_posicion:
            qty_extra = deuda_solicitada_usd / precio_activo_inicial
            collateral_final_qty += qty_extra
            deuda_final_qty = deuda_solicitada_usd 
        else:
            deuda_qty_token = deuda_solicitada_usd / precio_activo_inicial
            collateral_final_qty += deuda_solicitada_usd 
            deuda_final_qty = deuda_qty_token 
    else:
        if "Largo" in tipo_posicion:
            deuda_final_qty = deuda_solicitada_usd
        else:
            deuda_final_qty = deuda_solicitada_usd / precio_activo_inicial

    valor_colateral_usd = 0
    valor_deuda_usd = 0
    
    if "Largo" in tipo_posicion:
        valor_colateral_usd = collateral_final_qty * precio_activo_inicial
        valor_deuda_usd = deuda_final_qty 
    else:
        valor_colateral_usd = collateral_final_qty 
        valor_deuda_usd = deuda_final_qty * precio_activo_inicial

    hf_inicial = 999.0
    precio_liquidacion = 0.0
    
    # Función auxiliar para calcular Liq Price
    def calc_liq_price(c_qty, d_qty, tipo, ltv):
        if d_qty <= 0: return 0.0
        if "Largo" in tipo:
            # Long: Price = Deuda / (Colateral * LTV)
            return d_qty / (c_qty * ltv)
        else:
            # Short: Price = (Colateral * LTV) / Deuda
            return (c_qty * ltv) / d_qty

    precio_liquidacion = calc_liq_price(collateral_final_qty, deuda_final_qty, tipo_posicion, ltv_liquidacion)
    
    precio_defensa = 0.0
    if "Largo" in tipo_posicion:
        precio_defensa = precio_liquidacion * (1 + umbral_defensa)
    else:
        precio_defensa = precio_liquidacion * (1 - umbral_defensa)

    if valor_deuda_usd > 0 and hf_inicial < 1.0:
        # Recalcular HF para mostrar alerta correcta
        hf_val = (valor_colateral_usd * ltv_liquidacion) / valor_deuda_usd
        if hf_val < 1.0:
            st.error(f"⚠️ ¡Cuidado! Con estos parámetros naces liquidado. HF: {hf_val:.2f}")

    # --- MOSTRAR DATOS SECCIÓN 1 (ACTUALIZADO CON CANTIDADES) ---
    st.info("📊 **Resumen de Apertura**")
    col_res1, col_res2, col_res3, col_res4 = st.columns(4)
    
    # Formatear etiquetas con cantidades
    label_col_ini = f"{colateral_base_qty:,.4f} {lbl_colateral}" if "Largo" in tipo_posicion else f"${colateral_base_qty:,.2f}"
    label_col_fin = f"{collateral_final_qty:,.4f} {lbl_colateral}" if "Largo" in tipo_posicion else f"${collateral_final_qty:,.2f}"

    col_res1.metric("Colateral Inicial", f"${colateral_base_usd:,.2f}", delta=label_col_ini, delta_color="off")
    col_res2.metric("Colateral Final", f"${valor_colateral_usd:,.2f}", delta=label_col_fin)
    col_res3.metric("Deuda Total (USD)", f"${valor_deuda_usd:,.2f}")
    
    hf_display = (valor_colateral_usd * ltv_liquidacion) / valor_deuda_usd if valor_deuda_usd > 0 else 999
    col_res4.metric("Health Factor", f"{hf_display:.2f}")
    
    col_res5, col_res6 = st.columns(2)
    col_res5.metric("Precio Liquidación", f"${precio_liquidacion:,.2f}")
    col_res6.metric("Precio Primera Defensa", f"${precio_defensa:,.2f}", help="Nivel donde deberías actuar.")

    # --- SECCIÓN 2: DESARROLLO DE LA POSICIÓN ---
    st.markdown("---")
    st.subheader("2. Desarrollo de la Posición (Intermedio)")
    
    c_dev1, c_dev2, c_dev3 = st.columns(3)
    with c_dev1:
        precio_intermedio = st.number_input("Precio intermedio del Activo Volátil", value=precio_activo_inicial, step=100.0)
    with c_dev2:
        dias_pasados = st.number_input("Días transcurridos", min_value=0, value=30, step=1)
    
    interes_generado_token = 0
    interes_generado_usd = 0
    
    # Cálculo de deuda con intereses
    if "Largo" in tipo_posicion:
        interes_generado_usd = deuda_final_qty * (borrow_rate * dias_pasados / 365)
        deuda_total_actual_token = deuda_final_qty + interes_generado_usd 
        valor_colateral_actual_usd = collateral_final_qty * precio_intermedio
        valor_deuda_actual_usd = deuda_total_actual_token
    else:
        interes_generado_token = deuda_final_qty * (borrow_rate * dias_pasados / 365)
        deuda_total_actual_token = deuda_final_qty + interes_generado_token 
        interes_generado_usd = interes_generado_token * precio_intermedio
        valor_colateral_actual_usd = collateral_final_qty 
        valor_deuda_actual_usd = deuda_total_actual_token * precio_intermedio

    equity_actual_usd = valor_colateral_actual_usd - valor_deuda_actual_usd
    pnl_usd = equity_actual_usd - inversion_usdc
    pnl_pct = (pnl_usd / inversion_usdc) * 100 if inversion_usdc > 0 else 0

    col_res_int1, col_res_int2, col_res_int3 = st.columns(3)
    col_res_int1.metric("Intereses Generados (USD)", f"-${interes_generado_usd:,.2f}")
    col_res_int2.metric("Valor Neto Actual (Equity)", f"${equity_actual_usd:,.2f}")
    col_res_int3.metric("PnL Latente (Si cierras hoy)", f"${pnl_usd:,.2f} ({pnl_pct:.2f}%)", delta_color="normal")

    st.markdown("**Acciones sobre la posición**")
    # AÑADIDA OPCIÓN "Añadir Colateral"
    accion = st.radio("Elige una acción:", ["Mantener posición", "Añadir Colateral", "Cerrar Íntegramente", "Cerrar Parcialmente"], horizontal=True)

    colateral_remanente_qty = collateral_final_qty
    deuda_remanente_token = deuda_total_actual_token 
    
    dinero_en_wallet_usado = 0.0
    qty_added_sec2 = 0.0 # [NUEVO] Variable para registrar aportación de tokens extra
    
    # Variables para calcular nuevos precios de liquidación tras la acción
    nuevo_liq_price = precio_liquidacion
    nuevo_defensa_price = precio_defensa

    if accion == "Añadir Colateral":
        st.info("💡 Añadir colateral reduce tu LTV y aleja el precio de liquidación.")
        
        # NUEVA LÓGICA: Elegir tipo de activo a depositar
        lbl_activo_volatil = "Activo Volátil" if "Largo" in tipo_posicion else "Activo Volátil (Swap a USDC)"
        opciones_deposito = ["USDC", lbl_activo_volatil]
        
        tipo_aporte = st.radio("¿Qué activo vas a depositar?", opciones_deposito, horizontal=True)
        
        col1_add, col2_add = st.columns(2)
        with col1_add:
            step_val = 0.1 if tipo_aporte == "USDC" else 0.0001
            qty_input = st.number_input(f"Cantidad de {tipo_aporte} a añadir", min_value=0.0, value=0.0, step=step_val)
        
        qty_added_to_collateral = 0.0
        msg_conversion = ""

        if qty_input > 0:
            if "Largo" in tipo_posicion:
                # Posición Larga: El colateral es el Activo Volátil.
                if tipo_aporte == "USDC":
                    # Aporta USDC -> Se convierte a Activo Volátil al precio intermedio
                    qty_added_to_collateral = qty_input / precio_intermedio
                    dinero_en_wallet_usado = qty_input
                    msg_conversion = f"Has depositado **${qty_input:,.2f} USDC**, que se han convertido en **{qty_added_to_collateral:,.4f} Activo Volátil**."
                else:
                    # Aporta Activo Volátil -> Se suma directo
                    qty_added_to_collateral = qty_input
                    dinero_en_wallet_usado = qty_input * precio_intermedio # Valor equivalente en USD
            else:
                # Posición Corta: El colateral es USDC.
                if tipo_aporte == "USDC":
                    # Aporta USDC -> Se suma directo
                    qty_added_to_collateral = qty_input
                    dinero_en_wallet_usado = qty_input
                else:
                    # Aporta Activo Volátil -> Se vende por USDC
                    qty_added_to_collateral = qty_input * precio_intermedio
                    dinero_en_wallet_usado = qty_added_to_collateral
                    msg_conversion = f"Has depositado **{qty_input:,.4f} Activo Volátil**, que se han vendido por **${qty_added_to_collateral:,.2f} USDC** de colateral."

            # Actualizar el colateral remanente
            colateral_remanente_qty += qty_added_to_collateral
            qty_added_sec2 = qty_added_to_collateral # [NUEVO] Guardamos la cantidad añadida
            
            if msg_conversion:
                st.success(msg_conversion)
            else:
                st.success(f"Has añadido **{qty_added_to_collateral:,.4f} {lbl_colateral if 'Largo' in tipo_posicion else 'USDC'}** a tu colateral.")
            
            # Recalcular Liquidation Price
            nuevo_liq_price = calc_liq_price(colateral_remanente_qty, deuda_remanente_token, tipo_posicion, ltv_liquidacion)
            if "Largo" in tipo_posicion:
                nuevo_defensa_price = nuevo_liq_price * (1 + umbral_defensa)
            else:
                nuevo_defensa_price = nuevo_liq_price * (1 - umbral_defensa)
                
            c_new_liq1, c_new_liq2 = st.columns(2)
            c_new_liq1.metric("Nuevo Precio Liquidación", f"${nuevo_liq_price:,.2f}", delta=f"{nuevo_liq_price - precio_liquidacion:,.2f}")
            c_new_liq2.metric("Nuevo Precio Defensa", f"${nuevo_defensa_price:,.2f}")
            
    elif accion == "Cerrar Íntegramente":
        metodo_pago = st.radio("¿Cómo quieres pagar la deuda?", ["Vender Colateral", "Usar Wallet (USDC Externo)"])
        
        if metodo_pago == "Vender Colateral":
            if "Largo" in tipo_posicion:
                colateral_necesario = deuda_total_actual_token / precio_intermedio
                if colateral_necesario > collateral_final_qty:
                    st.error("❌ Insolvente: No tienes suficiente colateral para pagar la deuda.")
                else:
                    remanente_colateral = collateral_final_qty - colateral_necesario
                    valor_remanente = remanente_colateral * precio_intermedio
                    st.success(f"Has vendido {colateral_necesario:.4f} {lbl_colateral} para pagar la deuda.")
                    st.write(f"Te quedan **{remanente_colateral:.4f} {lbl_colateral}** valorados en **${valor_remanente:,.2f}**.")
            else:
                coste_compra_token = deuda_total_actual_token * precio_intermedio
                if coste_compra_token > collateral_final_qty:
                    st.error("❌ Insolvente.")
                else:
                    remanente_usdc = collateral_final_qty - coste_compra_token
                    st.success(f"Has usado ${coste_compra_token:,.2f} de tu colateral para recomprar el token y cerrar.")
                    st.write(f"Te quedan **${remanente_usdc:,.2f} USDC**.")
            
            colateral_remanente_qty = 0
            deuda_remanente_token = 0
            
        else: 
            st.warning("Nota: Al pagar con wallet, asumes la pérdida/ganancia de la deuda, pero te quedas con todo el colateral intacto.")
            if "Largo" in tipo_posicion:
                st.write(f"Pagas **${deuda_total_actual_token:,.2f}** de tu bolsillo.")
                st.write(f"Liberas **{collateral_final_qty:.4f} {lbl_colateral}**.")
            else:
                coste_recompra = deuda_total_actual_token * precio_intermedio
                st.write(f"Pagas **${coste_recompra:,.2f}** para recomprar el token y cerrar.")
                st.write(f"Recuperas tu colateral íntegro: **${collateral_final_qty:,.2f} USDC**.")
            
            deuda_remanente_token = 0

    elif accion == "Cerrar Parcialmente":
        pct_repay = st.slider("Porcentaje de deuda a repagar (%)", 1, 99, 50) / 100
        metodo_pago = st.radio("¿Fuente de fondos?", ["Vender Colateral", "Usar Wallet (USDC Externo)"], key="partial_pay")
        
        cant_a_pagar_token = deuda_total_actual_token * pct_repay
        valor_a_pagar_usd = 0
        
        if "Largo" in tipo_posicion:
            valor_a_pagar_usd = cant_a_pagar_token
        else:
            valor_a_pagar_usd = cant_a_pagar_token * precio_intermedio
            
        st.markdown(f"**Operación:** Vas a repagar {pct_repay*100:.0f}% de la deuda. Valor aprox: ${valor_a_pagar_usd:,.2f}.")
        
        colateral_usado_pago = 0.0

        if metodo_pago == "Vender Colateral":
            if "Largo" in tipo_posicion:
                colateral_usado_pago = valor_a_pagar_usd / precio_intermedio
                colateral_remanente_qty -= colateral_usado_pago
                deuda_remanente_token -= cant_a_pagar_token
            else:
                colateral_usado_pago = valor_a_pagar_usd # USDC
                colateral_remanente_qty -= valor_a_pagar_usd 
                deuda_remanente_token -= cant_a_pagar_token
        else:
            dinero_en_wallet_usado = valor_a_pagar_usd
            deuda_remanente_token -= cant_a_pagar_token
        
        # --- NUEVA LÓGICA DE VISUALIZACIÓN DETALLADA ---
        # Recalcular precios de riesgo con la nueva estructura de deuda/colateral
        nuevo_liq_price = calc_liq_price(colateral_remanente_qty, deuda_remanente_token, tipo_posicion, ltv_liquidacion)
        if "Largo" in tipo_posicion:
            nuevo_defensa_price = nuevo_liq_price * (1 + umbral_defensa)
        else:
            nuevo_defensa_price = nuevo_liq_price * (1 - umbral_defensa)

        st.markdown("#### 📝 Resultado del Repago Parcial")
        
        txt_col_restante = f"{colateral_remanente_qty:,.4f} {lbl_colateral}" if "Largo" in tipo_posicion else f"${colateral_remanente_qty:,.2f}"
        txt_deuda_restante = f"${deuda_remanente_token:,.2f}" if "Largo" in tipo_posicion else f"{deuda_remanente_token:,.4f} {lbl_deuda}"

        if metodo_pago == "Vender Colateral":
            st.info(f"""
            Has utilizado **{colateral_usado_pago:,.4f} {lbl_colateral}** para cancelar deuda. 
            \n🔹 **Situación Final:** Te quedan **{txt_col_restante}** y tu deuda ha bajado a **{txt_deuda_restante}**.
            """)
        else:
            st.info(f"""
            Has utilizado fondos externos. Tu colateral se mantiene intacto.
            \n🔹 **Situación Final:** Tienes **{txt_col_restante}** y tu deuda ha bajado a **{txt_deuda_restante}**.
            """)
            
        c_new_liq1, c_new_liq2 = st.columns(2)
        c_new_liq1.metric("Nuevo Precio Liquidación", f"${nuevo_liq_price:,.2f}")
        c_new_liq2.metric("Nuevo Precio Defensa", f"${nuevo_defensa_price:,.2f}")

    # --- SECCIÓN 3: RESULTADO FINAL (Lógica Intacta) ---
    st.markdown("---")
    st.subheader("3. Proyección a Futuro (Cierre Final)")
    
    if deuda_remanente_token <= 0 and accion == "Cerrar Íntegramente":
        st.success("La posición ya está cerrada. Ver resultados arriba.")
    else:
        precio_final = st.number_input(f"Precio futuro de cierre para {lbl_colateral if 'Largo' in tipo_posicion else 'Activo Deuda'}", value=precio_intermedio, step=100.0)
        
        valor_colateral_final_usd = 0
        coste_cierre_deuda_final_usd = 0
        
        if "Largo" in tipo_posicion:
            valor_colateral_final_usd = colateral_remanente_qty * precio_final
            coste_cierre_deuda_final_usd = deuda_remanente_token 
        else:
            valor_colateral_final_usd = colateral_remanente_qty 
            coste_cierre_deuda_final_usd = deuda_remanente_token * precio_final
            
        equity_final = valor_colateral_final_usd - coste_cierre_deuda_final_usd
        resultado_total_usd = equity_final - inversion_usdc - dinero_en_wallet_usado
        roi_total = (resultado_total_usd / inversion_usdc) * 100
        
        st.write("---")
        st.markdown(f"### Resultados Finales a precio ${precio_final:,.2f}")
        
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Valor Colateral Final", f"${valor_colateral_final_usd:,.2f}")
        kpi2.metric("Deuda Restante a Pagar", f"${coste_cierre_deuda_final_usd:,.2f}")
        kpi3.metric("Equity (Neto) Final", f"${equity_final:,.2f}")
        
        st.metric("Beneficio/Pérdida Total (PnL)", f"${resultado_total_usd:,.2f}", f"{roi_total:.2f}%")
        
        if resultado_total_usd < 0:
            st.error(f"Pérdida total: {resultado_total_usd:.2f} USD. (Incluyendo pagos intermedios).")
        else:
            st.success(f"Ganancia total: {resultado_total_usd:.2f} USD.")

        if "Largo" in tipo_posicion and precio_final > 0:
            resultado_en_tokens = resultado_total_usd / precio_final
            
            # [NUEVO] Cálculo de ROI en Tokens (Ganancia Tokens / (Tokens Iniciales + Tokens Añadidos))
            base_tokens_total = colateral_base_qty + qty_added_sec2
            roi_tokens_pct = (resultado_en_tokens / base_tokens_total) * 100 if base_tokens_total > 0 else 0
            
            st.write(f"Resultado medido en tokens: **{resultado_en_tokens:.4f} {lbl_colateral}** ({roi_tokens_pct:+.2f}%)")


# ==============================================================================
#  3. INTERFAZ DE USUARIO
# ==============================================================================

tab_home, tab_calc, tab_sim, tab_backtest, tab_dynamic_bt, tab_onchain = st.tabs([
    "🏠 Inicio", 
    "🧮 Calculadora",
    "💻 Simulación",
    "📉 Backtest (HODL)", 
    "🔄 Backtest Dinámico", 
    "📡 Escáner Real"
])

# ------------------------------------------------------------------------------
#  PESTAÑA 0: PORTADA (DISEÑO RECUPERADO 3 COLUMNAS)
# ------------------------------------------------------------------------------
with tab_home:
    # Título Principal Centrado
    st.markdown("# 🛡️ Looping Master Pro")
    st.markdown("#### Maximiza rendimientos, minimiza riesgos.")
    st.markdown("""
    Bienvenido a la suite definitiva para la gestión de posiciones apalancadas en DeFi.
    Esta herramienta te permite auditar, simular y proteger tus inversiones en Aave con precisión matemática.
    """)
    
    st.divider()

    # --- GRID DE 3 COLUMNAS (DISEÑO LIMPIO) ---
    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        st.info("🧮 **Calculadora**")
        st.markdown("Diseña tu estrategia **antes de invertir**.")
        st.markdown("- Proyecta tu precio de liquidación.")
        st.markdown("- Calcula tu ROI potencial.")
        st.markdown("- Planifica tu defensa en cascada.")

    with col_f2:
        st.warning("📉 **Backtesting**")
        st.markdown("Valida tu tesis con **datos históricos**.")
        st.markdown("- ¿Habría sobrevivido tu estrategia en 2022?")
        st.markdown("- Simula la volatilidad real.")
        st.markdown("- Calcula el capital necesario.")

    with col_f3:
        st.error("📡 **Escáner Real**")
        st.markdown("Conéctate a la **Blockchain en tiempo real**.")
        st.markdown("- Audita tu posición en Base, Arbitrum, etc.")
        st.markdown("- Detecta tu Salud (HF) real.")
        st.markdown("- Simula un crash de mercado.")

    st.divider()

    # --- LEAD MAGNET (INTEGRADO ABAJO) ---
    st.markdown("### 🎓 Aprende a dominar estas estrategias")
    
    col_lead_L, col_lead_R = st.columns([1.5, 1], gap="large")
    
    with col_lead_L:
        st.markdown("""
        Esta herramienta ha sido desarrollada por el equipo de **Campamento DeFi**.
        
        El *Looping Avanzado* es solo una de las múltiples estrategias que enseñamos para rentabilizar tus activos onchain de forma segura.
        
        **¿Quieres conocer más en detalle otras estrategias como esta? (3 pasos):**
        
        1.  📘 Rellena el formulario con tus datos.
        2.  🚨 Revisa tu bandeja de entrada (mira en spam).
        3.  🛠️ Te iremos informando de nuevas herramientas y estrategias.
        """)
    
    with col_lead_R:
        with st.container(border=True):
            st.markdown("#### 📩 Recibir Guía Gratuita")
            with st.form("lead_magnet_form_looping"):
                name_input = st.text_input("Nombre", placeholder="Tu nombre")
                email_input = st.text_input("Email", placeholder="tu@email.com")
                
                # Botón de acción principal
                submitted = st.form_submit_button("¡Quiero aprender!", type="primary", use_container_width=True)
                
                if submitted:
                    if email_input and "@" in email_input:
                        with st.spinner("Enviando solicitud..."):
                            ok, msg = add_subscriber_moosend(name_input, email_input)
                        
                            if ok:
                                st.success(f"¡Genial, {name_input}! Revisa tu correo ahora.")
                                st.balloons()
                            else:
                                st.error(f"Hubo un error técnico: {msg}")
                    else:
                        st.warning("Por favor, introduce un email válido.")
    
 

# ------------------------------------------------------------------------------
#  PESTAÑA 1: CALCULADORA ESTÁTICA (MEJORADA)
# ------------------------------------------------------------------------------
with tab_calc:
    st.markdown("### 🧮 Simulador Estático de Defensa")
    
    col_input1, col_input2, col_input3 = st.columns(3)
    with col_input1:
        selected_asset_calc = st.selectbox("Seleccionar Activo", list(ASSET_MAP.keys()), key="sel_asset_c")
        c_asset_name = st.text_input("Ticker", value="PEPE", key="c_asset_man") if ASSET_MAP[selected_asset_calc] == "MANUAL" else selected_asset_calc.split("(")[1].replace(")", "")
        c_price = st.number_input(f"Precio Actual {c_asset_name} ($)", value=100000.0, step=100.0, key="c_price")
        c_target = st.number_input(f"Precio Objetivo ($)", value=130000.0, step=100.0, key="c_target")
    with col_input2:
        c_capital = st.number_input("Capital Inicial ($)", value=10000.0, step=1000.0, key="c_capital")
        c_leverage = st.slider("Apalancamiento (x)", 1.1, 5.0, 2.0, 0.1, key="c_lev")
    with col_input3:
        c_ltv = st.slider("LTV Liquidación (%)", 50, 95, 78, 1, key="c_ltv") / 100.0
        c_threshold = st.number_input("Umbral Defensa (%)", value=15.0, step=1.0, key="c_th") / 100.0
        c_zones = st.slider("Zonas de Defensa", 1, 10, 5, key="c_zones")

    # Cálculos base
    c_collat_usd = c_capital * c_leverage
    c_debt_usd = c_collat_usd - c_capital
    c_collat_amt = c_collat_usd / c_price
    
    c_liq_price = 0
    c_hf_initial = 0
    c_target_ratio = 0
    
    if c_collat_amt > 0 and c_ltv > 0 and c_debt_usd > 0:
        c_liq_price = c_debt_usd / (c_collat_amt * c_ltv)
        c_hf_initial = (c_collat_usd * c_ltv) / c_debt_usd
        c_target_ratio = c_liq_price / c_price 
    elif c_debt_usd == 0:
        c_hf_initial = 999.0
        
    # --- PANEL DE MÉTRICAS (RECUPERADO) ---
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Salud Inicial (HF)", f"{c_hf_initial:.2f}", delta="OK" if c_hf_initial>1.1 else "Riesgo")
    m2.metric("Precio Liquidación", f"${c_liq_price:,.2f}")
    m3.metric("Colateral Total", f"${c_collat_usd:,.2f}")
    m4.metric("Deuda Total", f"${c_debt_usd:,.2f}")
    st.divider()

    # Generación de tabla en cascada
    cascade_data = []
    curr_collat = c_collat_amt
    curr_liq = c_liq_price
    cum_cost = 0.0
    
    for i in range(1, c_zones + 1):
        trig_p = curr_liq * (1 + c_threshold)
        drop_pct = (c_price - trig_p) / c_price
        targ_liq = trig_p * c_target_ratio
        
        # Estado en el momento del trigger (antes de defender)
        val_at_trigger = curr_collat * trig_p
        hf_at_trigger = (val_at_trigger * c_ltv) / c_debt_usd if c_debt_usd > 0 else 999
        
        # Apalancamiento en el momento del trigger
        equity_at_trigger = val_at_trigger - c_debt_usd
        lev_at_trigger = val_at_trigger / equity_at_trigger if equity_at_trigger > 0 else 999
        
        # Cálculo defensa
        if targ_liq > 0:
            need_col = c_debt_usd / (targ_liq * c_ltv)
            add_col = max(0, need_col - curr_collat)
        else:
            add_col = 0
            
        cost = add_col * trig_p
        cum_cost += cost
        curr_collat += add_col
        
        # Métricas financieras finales
        total_inv = c_capital + cum_cost
        final_val = curr_collat * c_target
        net_prof = (final_val - c_debt_usd) - total_inv
        roi = (net_prof / total_inv) * 100 if total_inv > 0 else 0
        ratio = roi / (drop_pct * 100) if drop_pct > 0 else 0
        
        # Nuevo HF tras defensa
        new_hf = ((curr_collat * trig_p) * c_ltv) / c_debt_usd if c_debt_usd > 0 else 999
        
        cascade_data.append({
            "Zona": f"#{i}", 
            "Precio Activación": trig_p, 
            "Caída (%)": drop_pct, 
            "Apalancamiento (x)": lev_at_trigger,  # <--- NUEVO
            "HF (Pre-Defensa)": hf_at_trigger,     # <--- NUEVO
            "Inversión Extra ($)": cost, 
            "Total Invertido ($)": total_inv, 
            "Nuevo P. Liq": targ_liq, 
            "Nuevo HF": new_hf,
            "Beneficio ($)": net_prof, 
            "ROI (%)": roi, 
            "Ratio": ratio
        })
        curr_liq = targ_liq

    st.subheader("🛡️ Plan de Defensa Escalonado")
    st.dataframe(
        pd.DataFrame(cascade_data).style.format({
            "Precio Activación": "${:,.2f}", 
            "Caída (%)": "{:.2%}", 
            "Apalancamiento (x)": "{:.2f}x",
            "HF (Pre-Defensa)": "{:.2f}",
            "Inversión Extra ($)": "${:,.0f}", 
            "Total Invertido ($)": "${:,.0f}", 
            "Nuevo P. Liq": "${:,.2f}", 
            "Nuevo HF": "{:.2f}",
            "Beneficio ($)": "${:,.0f}", 
            "ROI (%)": "{:.2f}%", 
            "Ratio": "{:.2f}"
        }).background_gradient(subset=["HF (Pre-Defensa)"], cmap="RdYlGn"), 
        use_container_width=True
    )
    
    if not pd.DataFrame(cascade_data).empty:
        st.divider()
        last_row = pd.DataFrame(cascade_data).iloc[-1]
        st.markdown(f"""
        ### 📝 Informe Ejecutivo
        **Escenario Extremo:** Si el mercado cae un **{last_row['Caída (%)']:.1%}**, necesitarás haber inyectado un total de **\${last_row['Total Invertido ($)']-c_capital:,.0f}** para sobrevivir. Si tras eso el precio recupera al objetivo, tu ROI sería del **{last_row['ROI (%)']:.2f}%**.
        """)

# ------------------------------------------------------------------------------
#  PESTAÑA 2: SIMULADOR (CORREGIDO)
# ------------------------------------------------------------------------------
with tab_sim:
    st.header("Simulador de Apalancamiento y Gestión de Riesgo")
    # AQUI LLAMAMOS A LA FUNCIÓN, INDENTADA DENTRO DEL WITH
    simulacion_seccion()

# ------------------------------------------------------------------------------
#  PESTAÑA 3: MOTOR DE BACKTESTING (VERSIÓN PRO RESTAURADA)
# ------------------------------------------------------------------------------
with tab_backtest:
    st.markdown("### 📉 Validación Histórica (Strategy vs HODL)")
    st.caption("Compara el rendimiento de la estrategia de Looping protegida contra simplemente haber comprado y mantenido (HODL).")
    
    # --- INPUTS ---
    col_bt1, col_bt2, col_bt3 = st.columns(3)
    with col_bt1:
        selected_asset_bt = st.selectbox("Seleccionar Activo Histórico", list(ASSET_MAP.keys()), key="sel_asset_bt")
        if ASSET_MAP[selected_asset_bt] == "MANUAL":
            bt_ticker = st.text_input("Ticker Yahoo (ej: BTC-USD)", value="BTC-USD", key="bt_t")
        else:
            bt_ticker = ASSET_MAP[selected_asset_bt]
        bt_capital = st.number_input("Capital Inicial ($)", value=10000.0, key="bt_c")
    
    with col_bt2:
        bt_start_date = st.date_input("Fecha Inicio", value=date.today() - timedelta(days=365*2))
        bt_leverage = st.slider("Apalancamiento Inicial", 1.1, 4.0, 2.0, key="bt_lev")
    
    with col_bt3:
        bt_threshold = st.number_input("Umbral Defensa (%)", value=15.0, step=1.0, key="bt_th") / 100.0
        run_bt = st.button("🚀 Ejecutar Backtest", type="primary")

    # --- LÓGICA ---
    if run_bt:
        with st.spinner(f"Descargando datos de {bt_ticker} y simulando escenarios..."):
            try:
                # 1. Descarga de datos
                df_hist = yf.download(bt_ticker, start=bt_start_date, end=date.today(), progress=False)
                
                if df_hist.empty:
                    st.error("No hay datos para este ticker/fechas.")
                    st.stop()
                
                # Limpieza de MultiIndex si existe
                if isinstance(df_hist.columns, pd.MultiIndex):
                    df_hist.columns = df_hist.columns.get_level_values(0)

                # 2. Variables Iniciales (T0)
                start_price = float(df_hist.iloc[0]['Close']) 
                
                # Estrategia Looping
                collateral_usd = bt_capital * bt_leverage
                debt_usd = collateral_usd - bt_capital 
                collateral_amt = collateral_usd / start_price 
                # Usamos un LTV estándar (80%) para el backtest si no se define otro
                ltv_sim = 0.80 
                liq_price = debt_usd / (collateral_amt * ltv_sim)
                
                # Estrategia HODL (Referencia)
                hodl_amt = bt_capital / start_price
                
                # Variables de Bucle
                history = []
                defense_log = []
                total_injected = 0.0
                is_liquidated = False
                
                # 3. Bucle Día a Día
                for date_idx, row in df_hist.iterrows():
                    if pd.isna(row['Close']): continue
                    
                    # Precios del día
                    open_val = float(row['Open'])
                    low_val = float(row['Low'])
                    close_val = float(row['Close'])
                    
                    trigger_price = liq_price * (1 + bt_threshold)
                    action = "Hold"
                    defense_cost = 0.0
                    
                    # A. Chequeo de Defensa / Liquidación
                    if low_val <= trigger_price and not is_liquidated:
                        # Asumimos que defendemos al precio de apertura si el gap bajista fue fuerte,
                        # o al trigger si fue intradía. Peor caso: Open.
                        defense_exec_price = min(open_val, trigger_price)
                        
                        # Si el precio de ejecución ya está por debajo de liquidación -> MUERTE
                        if defense_exec_price <= liq_price:
                            is_liquidated = True
                            action = "LIQUIDATED ☠️"
                        else:
                            # Ejecutar Defensa: Restaurar ratio original
                            # Nuevo Liq Objetivo para mantener la distancia relativa
                            # Ratio original = Liq_Inicial / Precio_Inicial. 
                            # Aquí simplificamos: Restaurar al mismo % de distancia que el trigger
                            # Target Liq = Defense_Price / (1 + Threshold)
                            
                            # Lógica más simple: Queremos bajar el Liq Price.
                            # ¿Cuánto? Digamos que queremos alejarlo otro 20%.
                            target_liq_new = defense_exec_price * 0.80 # Alejamos un 20%
                            
                            # Cálculo de aporte necesario
                            # Need_Col_Amt = Debt / (Target_Liq * LTV)
                            needed_collat_amt = debt_usd / (target_liq_new * ltv_sim)
                            add_collat_amt = needed_collat_amt - collateral_amt
                            
                            if add_collat_amt > 0:
                                defense_cost = add_collat_amt * defense_exec_price
                                total_injected += defense_cost
                                collateral_amt += add_collat_amt
                                liq_price = target_liq_new 
                                action = "DEFENSA 🛡️"
                                
                                defense_log.append({
                                    "Fecha": date_idx.strftime('%Y-%m-%d'),
                                    "Precio Activo": f"${defense_exec_price:,.2f}",
                                    "Inyección ($)": defense_cost,
                                    "Nuevo Precio Liq": target_liq_new
                                })
                    
                    # B. Chequeo Liquidación por mecha rápida
                    if low_val <= liq_price:
                        is_liquidated = True
                        action = "LIQUIDATED ☠️"
                        
                    # C. Valoración Diaria
                    if not is_liquidated:
                        strat_value = (collateral_amt * close_val) - debt_usd
                    else:
                        strat_value = 0
                        
                    hodl_value = hodl_amt * close_val
                    total_invested = bt_capital + total_injected
                    
                    history.append({
                        "Fecha": date_idx,
                        "Precio": close_val,
                        "Valor Estrategia": strat_value, 
                        "Valor HODL": hodl_value,
                        "Inversión Total": total_invested,
                        "Acción": action
                    })
                    
                    if is_liquidated: break
                
                # 4. Resultados Finales
                df_res = pd.DataFrame(history).set_index("Fecha")
                final_val = df_res.iloc[-1]['Valor Estrategia']
                final_invested = df_res.iloc[-1]['Inversión Total']
                
                profit = final_val - final_invested
                roi = (profit / final_invested) * 100
                
                # Métricas HODL
                hodl_final = df_res.iloc[-1]['Valor HODL']
                hodl_profit = hodl_final - bt_capital
                hodl_roi = (hodl_profit / bt_capital) * 100
                
                # --- VISUALIZACIÓN DE KPIS ---
                st.divider()
                k1, k2, k3, k4 = st.columns(4)
                
                k1.metric("Estado Final", "VIVO" if not is_liquidated else "LIQUIDADO", 
                          delta="Sobrevivió" if not is_liquidated else "Rekt", 
                          delta_color="normal" if not is_liquidated else "inverse")
                
                k2.metric("Capital Inyectado", f"${total_injected:,.0f}", help="Dinero extra añadido para no ser liquidado")
                
                k3.metric("Beneficio Neto (Estrategia)", f"${profit:,.0f}", delta=f"{roi:.2f}% ROI")
                
                k4.metric("Beneficio Neto (HODL)", f"${hodl_profit:,.0f}", delta=f"{hodl_roi:.2f}% ROI",
                          help="Lo que hubieras ganado comprando y manteniendo sin hacer nada.")

                # --- GRÁFICO COMPARATIVO ---
                st.subheader("📈 Evolución del Patrimonio")
                fig = go.Figure()
                
                # Área Estrategia
                fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Valor Estrategia"], 
                                         name='Estrategia Looping', mode='lines', 
                                         line=dict(color='#00CC96', width=2), fill='tozeroy', fillcolor='rgba(0, 204, 150, 0.1)'))
                
                # Línea HODL
                fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Valor HODL"], 
                                         name='Solo HODL', mode='lines', 
                                         line=dict(color='#636EFA', width=2, dash='dot')))
                
                # Línea Coste (Inversión)
                fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Inversión Total"], 
                                         name='Dinero de tu Bolsillo', mode='lines', 
                                         line=dict(color='#EF553B', width=1)))
                
                # Eventos de Defensa
                defense_events = df_res[df_res["Acción"].str.contains("DEFENSA")]
                if not defense_events.empty:
                    fig.add_trace(go.Scatter(x=defense_events.index, y=defense_events["Valor Estrategia"],
                                             mode='markers', name='Inyección Capital', 
                                             marker=dict(color='orange', size=10, symbol='diamond')))
                
                st.plotly_chart(fig, use_container_width=True)
                
                # --- DIARIO DE OPERACIONES ---
                if defense_log:
                    with st.expander("🛡️ Ver Diario de Defensas (Inyecciones de Capital)", expanded=True):
                        st.dataframe(pd.DataFrame(defense_log).style.format({
                            "Inyección ($)": "${:,.2f}", 
                            "Nuevo Precio Liq": "${:,.2f}"
                        }), use_container_width=True)
                else:
                    st.success("🎉 ¡Enhorabuena! La estrategia no necesitó ninguna defensa en este periodo.")
                    
            except Exception as e:
                st.error(f"Error en el cálculo: {e}")

# --- PESTAÑA 4: BACKTEST DINÁMICO (ESTRATEGIA DE ACUMULACIÓN) ---
with tab_dynamic_bt:
    st.markdown("### 🔄 Backtest Dinámico: 'Accumulator Mode'")
    st.info("""
    **Estrategia de Acumulación de Activos:**
    1. **Defensa:** Si cae, inyectamos capital para proteger.
    2. **Moonbag (x2):** Si la posición dobla el riesgo, **retiramos los tokens iniciales** a HODL y reiniciamos con las ganancias.
    """)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        dyn_ticker = st.text_input("Ticker", "BTC-USD", key="dy_t")
        dyn_capital = st.number_input("Capital Inicial ($)", 10000.0, key="dy_c")
    with c2:
        dyn_start = st.date_input("Inicio", date.today() - timedelta(days=365*4), key="dy_d")
        dyn_lev = st.slider("Apalancamiento Objetivo", 1.1, 4.0, 2.0, key="dy_l")
    with c3:
        dyn_th = st.number_input("Umbral Defensa (%)", 15.0, key="dy_th") / 100.0
        run_dyn = st.button("🚀 Simular Acumulación", type="primary")

    if run_dyn:
        with st.spinner("Simulando estrategia de acumulación..."):
            try:
                df = yf.download(dyn_ticker, start=dyn_start, progress=False)
                if df.empty: st.error("Sin datos"); st.stop()
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

                # --- ESTADO INICIAL ---
                wallet_usd = dyn_capital    # Dinero disponible para abrir
                accumulated_tokens = 0.0    # Tokens retirados (HODL)
                total_usd_injected = 0.0    # Métricas de rendimiento
                
                position = None 
                hist = []; events = []
                
                for d, r in df.iterrows():
                    if pd.isna(r['Close']): continue
                    op, lo, hi, cl = float(r['Open']), float(r['Low']), float(r['High']), float(r['Close'])
                    
                    # 1. ABRIR POSICIÓN
                    if position is None and wallet_usd > 0:
                        col_usd = wallet_usd * dyn_lev
                        debt = col_usd - wallet_usd
                        total_amt = col_usd / op
                        own_amt = wallet_usd / op 
                        liq = debt / (total_amt * 0.80)
                        
                        # risk_base: Valor USD de lo que arriesgo en este ciclo
                        position = {
                            "total_amt": total_amt, 
                            "debt_usd": debt, 
                            "liq": liq, 
                            "initial_stack": own_amt, 
                            "risk_base": wallet_usd, 
                            "defended": False
                        }
                        
                        wallet_usd = 0
                        events.append({
                            "Fecha": d.date(), "Evento": "🟢 APERTURA", 
                            "Precio": f"${op:,.0f}", 
                            "Detalle": f"Stack: {own_amt:.4f}", 
                            "Info Extra": f"Deuda: ${debt:,.0f}"
                        })

                    # 2. GESTIÓN
                    if position:
                        # A. LIQUIDACIÓN
                        if lo <= position["liq"]:
                            position = None; wallet_usd = 0
                            events.append({
                                "Fecha": d.date(), "Evento": "💀 LIQUIDACIÓN", 
                                "Precio": f"${lo:,.0f}", 
                                "Detalle": "Pérdida Total", "Info Extra": "-"
                            })
                        else:
                            # B. MOONBAG
                            curr_equity = (position["total_amt"] * cl) - position["debt_usd"]
                            val_initial = position["initial_stack"] * cl
                            
                            if position["risk_base"] > 0 and curr_equity >= (val_initial * 2):
                                # CORRECCIÓN FINAL DE SINTAXIS
                                tokens_out = position["initial_stack"]
                                accumulated_tokens += tokens_out
                                
                                remaining_equity = curr_equity - val_initial
                                wallet_usd = remaining_equity
                                position = None 
                                
                                events.append({
                                    "Fecha": d.date(), "Evento": "🚀 MOONBAG", 
                                    "Precio": f"${cl:,.0f}", 
                                    "Detalle": f"Retirados {tokens_out:.4f}", 
                                    "Info Extra": f"Reinvierte: ${wallet_usd:,.0f}"
                                })

                            # C. DEFENSA
                            elif position and lo <= (position["liq"] * (1 + dyn_th)):
                                trig = position["liq"] * (1 + dyn_th)
                                dp = min(op, trig)
                                nl = dp * 0.80
                                needed = position["debt_usd"] / (nl * 0.80)
                                add = needed - position["total_amt"]
                                
                                if add > 0:
                                    cost = add * dp
                                    total_usd_injected += cost
                                    position["total_amt"] += add
                                    position["initial_stack"] += add
                                    position["risk_base"] += cost
                                    position["liq"] = nl
                                    position["defended"] = True
                                    
                                    events.append({
                                        "Fecha": d.date(), "Evento": "🛡️ DEFENSA", 
                                        "Precio": f"${dp:,.0f}", 
                                        "Detalle": f"Inyección: ${cost:,.0f}", 
                                        "Info Extra": f"+{add:.4f} tokens"
                                    })

                    # Registro
                    val_hodl = accumulated_tokens * cl
                    val_strat = 0
                    if position:
                        val_strat = (position["total_amt"] * cl) - position["debt_usd"]
                    
                    total_wealth = val_hodl + val_strat + wallet_usd
                    total_inv = dyn_capital + total_usd_injected
                    val_static_hodl = (dyn_capital / df.iloc[0]['Close']) * cl
                    
                    hist.append({
                        "Fecha": d, 
                        "Riqueza Total ($)": total_wealth, 
                        "HODL Pasivo ($)": val_static_hodl, 
                        "Tokens Acumulados": accumulated_tokens, 
                        "Inversión Total ($)": total_inv
                    })

                df_r = pd.DataFrame(hist).set_index("Fecha")
                final_wealth = df_r.iloc[-1]["Riqueza Total ($)"]
                final_inv = df_r.iloc[-1]["Inversión Total ($)"]
                final_hodl = df_r.iloc[-1]["HODL Pasivo ($)"]
                
                roi = ((final_wealth - final_inv) / final_inv) * 100
                roi_hodl = ((final_hodl - dyn_capital) / dyn_capital) * 100
                
                st.divider()
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Patrimonio Final", f"${final_wealth:,.0f}", delta=f"{roi:.2f}% ROI")
                m2.metric("Tokens 'Risk Free'", f"{accumulated_tokens:.4f}")
                m3.metric("Vs HODL Pasivo", f"${final_hodl:,.0f}", delta=f"${final_wealth - final_hodl:,.0f}")
                m4.metric("Inversión Total", f"${final_inv:,.0f}")
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_r.index, y=df_r["Riqueza Total ($)"], name="Estrategia", line=dict(color="#00CC96", width=2)))
                fig.add_trace(go.Scatter(x=df_r.index, y=df_r["HODL Pasivo ($)"], name="HODL", line=dict(color="gray", dash="dot")))
                st.plotly_chart(fig, use_container_width=True)
                
                with st.expander("📜 Ver Diario de Operaciones", expanded=True):
                    if events:
                        st.dataframe(
                            pd.DataFrame(events), 
                            use_container_width=True, 
                            hide_index=True,
                            column_config={
                                "Precio": st.column_config.TextColumn("Precio Mercado"),
                                "Info Extra": st.column_config.TextColumn("Datos Adicionales")
                            }
                        )
                    else:
                        st.info("Sin operaciones.")

            except Exception as e: st.error(str(e))

# ------------------------------------------------------------------------------
#  PESTAÑA 5: ESCÁNER REAL (MODO SEGURO + MEMORIA)
# ------------------------------------------------------------------------------
with tab_onchain:
    st.markdown("### 📡 Escáner Aave V3 (Modo Seguro)")
    st.caption("Conexión ligera verificada. Elige tu modo de análisis abajo.")
    
    col_net1, col_net2 = st.columns([1, 3])
    with col_net1:
        net = st.selectbox("Red", list(NETWORKS.keys()))
    with col_net2:
        addr = st.text_input("Wallet Address (0x...)", placeholder="0x...")
    
    # --- GESTIÓN DE ESTADO (MEMORIA DE SESIÓN) ---
    if 'portfolio_data' not in st.session_state:
        st.session_state.portfolio_data = None

    if st.button("🔍 Analizar"):
        if not addr:
            st.warning("Falta dirección")
        else:
            with st.spinner(f"Conectando a {net}..."):
                w3, rpc_used, is_private = connect_robust(net)
                if not w3:
                    st.error("Error conexión RPC. Revisa tus Secrets."); st.stop()
                
                try:
                    # 1. Obtener Pool Real
                    prov_addr = w3.to_checksum_address(NETWORKS[net]["pool_provider"])
                    prov_contract = w3.eth.contract(address=prov_addr, abi=AAVE_ABI)
                    pool_addr = prov_contract.functions.getPool().call()
                    
                    # 2. Llamada Ligera (getUserAccountData)
                    pool = w3.eth.contract(address=pool_addr, abi=AAVE_ABI)
                    data = pool.functions.getUserAccountData(w3.to_checksum_address(addr)).call()
                    
                    # 3. Guardar en Memoria Session State
                    st.session_state.portfolio_data = {
                        "col_usd": data[0] / 10**8,
                        "debt_usd": data[1] / 10**8,
                        "lt_avg": data[3] / 10000,
                        "hf": data[5] / 10**18,
                        "status_msg": f"🔒 Privado" if is_private else f"🌍 Público ({rpc_used[:20]}...)"
                    }
                except Exception as e:
                    st.error(f"Error de lectura: {e}")

    # --- MOSTRAR DATOS DESDE MEMORIA ---
    if st.session_state.portfolio_data:
        d = st.session_state.portfolio_data
        
        st.success(f"✅ Datos recibidos. Conexión: {d['status_msg']}")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Salud (HF)", f"{d['hf']:.2f}", delta_color="normal" if d['hf']>1.1 else "inverse")
        m2.metric("Colateral Total", f"${d['col_usd']:,.2f}")
        m3.metric("Deuda Total", f"${d['debt_usd']:,.2f}")
        m4.metric("Liq. Threshold (Avg)", f"{d['lt_avg']:.2%}")
        
        if d['debt_usd'] > 0:
            st.divider()
            st.subheader("🛠️ Estrategia de Defensa")
            
            # SELECTOR DE MODO (Persistente)
            mode = st.radio("Tipo de Posición:", 
                            ["🛡️ Activo Único (Detallado con Precios)", 
                             "💼 Multi-Colateral (Plan Preventivo por Salud)"], 
                            horizontal=True)
            
            # ==================================================================
            # MODO A: ACTIVO ÚNICO
            # ==================================================================
            if "Activo Único" in mode:
                c_sel, c_par = st.columns(2)
                with c_sel:
                    sim_asset = st.selectbox("Activo Principal", list(ASSET_MAP.keys()), key="oc_a")
                    ticker = ASSET_MAP[sim_asset] if ASSET_MAP[sim_asset] != "MANUAL" else st.text_input("Ticker", "ETH-USD", key="oc_tick")
                with c_par:
                    def_th = st.number_input("Umbral %", 5.0, key="oc_th") / 100.0
                    zones = st.slider("Zonas", 1, 10, 5, key="oc_z")
                    
                try:
                    curr_p = yf.Ticker(ticker).history(period="1d")['Close'].iloc[-1]
                    st.metric(f"Precio Mercado ({ticker})", f"${curr_p:,.2f}")
                    
                    # Ingeniería inversa
                    implied_amt = d['col_usd'] / curr_p
                    liq_real = d['debt_usd'] / (implied_amt * d['lt_avg'])
                    cushion = (curr_p - liq_real) / curr_p
                    st.metric("Precio Liquidación Actual", f"${liq_real:,.2f}", f"{cushion:.2%} Colchón")
                    
                    ratio_target = liq_real / curr_p
                    s_data = []
                    s_curr_c, s_curr_l, s_cum = implied_amt, liq_real, 0.0
                    
                    for i in range(1, zones + 1):
                        trig = s_curr_l * (1 + def_th)
                        targ = trig * ratio_target
                        
                        # Cantidad necesaria
                        needed_amt = d['debt_usd'] / (targ * d['lt_avg'])
                        add_amt = max(0, needed_amt - s_curr_c)
                        
                        cost_usd = add_amt * trig
                        s_cum += cost_usd
                        s_curr_c += add_amt
                        
                        # Nuevo HF al inyectar
                        new_col_usd = s_curr_c * trig
                        new_hf = (new_col_usd * d['lt_avg']) / d['debt_usd']
                        
                        s_data.append({
                            "Zona": f"#{i}", 
                            "Precio Activación": trig, 
                            "Inyectar (Tokens)": add_amt, 
                            "Costo ($)": cost_usd, 
                            "Acumulado ($)": s_cum, 
                            "Nuevo Liq": targ, 
                            "Nuevo HF": new_hf
                        })
                        s_curr_l = targ
                        
                    st.dataframe(
                        pd.DataFrame(s_data).style.format({
                            "Precio Activación": "${:,.2f}", "Costo ($)": "${:,.0f}", 
                            "Acumulado ($)": "${:,.0f}", "Nuevo Liq": "${:,.2f}", 
                            "Nuevo HF": "{:.2f}", "Inyectar (Tokens)": "{:.4f}"
                        }), use_container_width=True
                    )
                    
                except Exception as ex:
                    st.error(f"Error al obtener precio: {ex}")

            # ==================================================================
            # MODO B: MULTI-COLATERAL (LÓGICA PREVENTIVA)
            # ==================================================================
            else:
                st.info("Planificación preventiva basada en caída de Salud (Health Factor).")
                
                col_opts, col_ref = st.columns(2)
                with col_opts:
                    num_defenses = st.slider("Número de Defensas", 1, 10, 5, key="mc_zones")
                with col_ref:
                    witness_asset = st.selectbox("Activo Testigo (Referencia Visual)", list(ASSET_MAP.keys()), key="mc_witness")
                    w_ticker = ASSET_MAP[witness_asset] if ASSET_MAP[witness_asset] != "MANUAL" else "ETH-USD"
                
                try:
                    w_price = yf.Ticker(w_ticker).history(period="1d")['Close'].iloc[-1]
                except: 
                    w_price = 0

                current_hf = d['hf']
                
                if current_hf <= 1.0:
                    st.error("La posición ya está en rango de liquidación (HF < 1.0)")
                else:
                    # Lógica de saltos de HF
                    hf_gap = current_hf - 1.0
                    hf_step = hf_gap / num_defenses
                    
                    mc_data = []
                    
                    for i in range(1, num_defenses + 1):
                        # Trigger HF
                        trigger_hf = current_hf - (hf_step * i)
                        if trigger_hf <= 1.001: trigger_hf = 1.001
                        
                        # Caída necesaria
                        drop_pct = 1 - (trigger_hf / current_hf)
                        
                        # Cálculos de restauración
                        shocked_col = d['col_usd'] * (1 - drop_pct)
                        # Valor base LT ponderado ajustado a la caída
                        shocked_lt_val = (d['col_usd'] * d['lt_avg']) * (1 - drop_pct)
                        
                        # Capital necesario para volver al HF Original
                        needed_capital = d['debt_usd'] - (shocked_lt_val / current_hf)
                        if needed_capital < 0: needed_capital = 0
                        
                        w_price_shock = w_price * (1 - drop_pct)
                        
                        # Nuevo HF real tras inyección
                        final_debt = d['debt_usd'] - needed_capital
                        if final_debt > 0:
                            final_hf = (shocked_col * d['lt_avg']) / final_debt
                        else:
                            final_hf = 999.0
                        
                        mc_data.append({
                            "Trigger HF": f"{trigger_hf:.2f}",
                            "Caída Mercado": f"-{drop_pct:.2%}",
                            f"Precio {w_ticker}": w_price_shock,
                            "Capital a Restaurar ($)": needed_capital,
                            "Nuevo HF": f"{final_hf:.2f}"
                        })
                    
                    st.dataframe(
                        pd.DataFrame(mc_data).style.format({
                            "Capital a Restaurar ($)": "${:,.2f}",
                            f"Precio {w_ticker}": "${:,.2f}"
                        }).background_gradient(subset=["Capital a Restaurar ($)"], cmap="Reds"), 
                        use_container_width=True
                    )
        else:
            st.success("Sin deuda activa.")

# ==============================================================================
#  GLOBAL FOOTER (Pie de página común para todas las pestañas)
# ==============================================================================
st.divider()
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        Desarrollado con ❤️ por <a href='https://lab.campamentodefi.com' target='_blank' style='text-decoration: none; color: #FF4B4B;'>Campamento DeFi</a>, 
        el lugar de reunión de los seres <a href='https://link.soypepediaz.com/labinconfiscable' target='_blank' style='text-decoration: none; color: #FF4B4B;'>Inconfiscables</a>
    </div>
    """, 
    unsafe_allow_html=True
)
