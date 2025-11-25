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
    # .get() devuelve None si no existe, NO da error.
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

# ==============================================================================
#  3. INTERFAZ DE USUARIO
# ==============================================================================

tab_home, tab_calc, tab_backtest, tab_dynamic_bt, tab_onchain = st.tabs([
    "🏠 Inicio", 
    "🧮 Calculadora", 
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
    
    st.caption("Desarrollado con ❤️ por Campamento DeFi. DYOR.")

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
#  PESTAÑA 2: MOTOR DE BACKTESTING (VERSIÓN PRO RESTAURADA)
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

# ------------------------------------------------------------------------------
#  PESTAÑA 3: BACKTEST DINÁMICO (ACUMULACIÓN DE ACTIVOS REALE)
# ------------------------------------------------------------------------------
with tab_dynamic_bt:
    st.markdown("### 🔄 Backtest Dinámico: 'Accumulator Mode'")
    st.info("""
    **Estrategia de Acumulación Real:**
    1. **Defensa:** Si cae, inyectamos capital (USD) para salvar la posición.
    2. **Moonbag (x2):** Si el valor neto dobla el riesgo, **retiramos los tokens equivalentes a la inversión inicial** a una billetera fría (HODL).
    3. **Compounding:** El beneficio restante se usa para abrir una nueva posición apalancada automáticamente.
    """)
    
    col_dyn1, col_dyn2, col_dyn3 = st.columns(3)
    with col_dyn1:
        dyn_ticker = st.text_input("Ticker", "BTC-USD", key="dy_t")
        dyn_capital = st.number_input("Capital Inicial ($)", 10000.0, key="dy_c")
    with col_dyn2:
        dyn_start = st.date_input("Inicio", date.today() - timedelta(days=365*2), key="dy_d")
        dyn_lev = st.slider("Lev Objetivo", 1.1, 4.0, 2.0, key="dy_l")
    with col_dyn3:
        dyn_th = st.number_input("Umbral Defensa (%)", 15.0, key="dy_th") / 100.0
        run_dyn = st.button("🚀 Simular Acumulación", type="primary")

    if run_dyn:
        with st.spinner("Simulando estrategia de acumulación..."):
            try:
                df = yf.download(dyn_ticker, start=dyn_start, progress=False)
                if df.empty: st.error("Sin datos"); st.stop()
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

                # --- ESTADO INICIAL ---
                wallet_usd = dyn_capital    # Dinero disponible para abrir posiciones
                
                # AQUÍ ESTÁ EL CAMBIO: Guardamos tokens, no dólares
                accumulated_tokens = 0.0    
                
                position = None 
                risk_basis = dyn_capital    # Base de riesgo para calcular el x2
                
                hist = []
                events = []
                ext_inj = 0.0               # Inyecciones externas totales
                
                for d, r in df.iterrows():
                    if pd.isna(r['Close']): continue
                    op, lo, hi, cl = float(r['Open']), float(r['Low']), float(r['High']), float(r['Close'])
                    act = "Hold"
                    
                    # 1. ABRIR POSICIÓN (Si tenemos cash)
                    if position is None and wallet_usd > 0:
                        col = wallet_usd * dyn_lev
                        debt = col - wallet_usd
                        amt = col / op
                        liq = debt / (amt * 0.80)
                        
                        # Al abrir, reseteamos la base de riesgo al dinero que acabamos de poner
                        risk_basis = wallet_usd 
                        
                        position = {"amt": amt, "debt": debt, "liq": liq, "ent": op, "def": False}
                        wallet_usd = 0
                        act = "OPEN"
                        events.append({"Fecha": d.date(), "Evento": "🟢 APERTURA", "Precio": f"${op:,.0f}", "Detalle": f"Tokens: {amt:.4f}", "Info Extra": f"Deuda: ${debt:,.0f}"})
                    
                    # 2. GESTIÓN
                    if position:
                        # A. LIQUIDACIÓN
                        if lo <= position["liq"]:
                            position = None; wallet_usd = 0; act = "LIQUIDATED"
                            events.append({"Fecha": d.date(), "Evento": "💀 LIQUIDACIÓN", "Precio": f"${lo:,.0f}", "Detalle": "Pérdida Total Posición", "Info Extra": "-"})
                        
                        else:
                            # B. MOONBAG (ACUMULACIÓN DE TOKENS)
                            # Calculamos Equity actual
                            curr_equity_usd = (position["amt"] * cl) - position["debt"]
                            
                            # Si doblamos la base de riesgo (x2)
                            if curr_equity_usd >= (risk_basis * 2) and risk_basis > 0:
                                # 1. Calculamos cuántos tokens equivalen a mi inversión inicial (Risk Basis)
                                #    Estos son los que quiero "salvar"
                                tokens_to_withdraw = risk_basis / cl
                                
                                # 2. Los sacamos de la estrategia
                                accumulated_tokens += tokens_to_withdraw
                                
                                # 3. El resto del Equity (Beneficios) se queda para reabrir
                                remaining_equity = curr_equity_usd - risk_basis
                                
                                # 4. Cerramos y Reabrimos (Rebalanceo virtual)
                                #    Usamos el remaining_equity para abrir una nueva posición limpia al apalancamiento objetivo
                                wallet_usd = remaining_equity
                                position = None # Forzamos reapertura en la siguiente iteración o lógica inmediata
                                
                                # Marcamos que ya no hay riesgo de mi bolsillo en la siguiente jugada
                                # (Opcional: Si quieres que el siguiente x2 sea sobre el nuevo capital, descomenta abajo)
                                # risk_basis = remaining_equity 
                                
                                act = "MOONBAG 🚀"
                                events.append({
                                    "Fecha": d.date(), "Evento": "🚀 MOONBAG", 
                                    "Precio": f"${cl:,.0f}", 
                                    "Detalle": f"Retirados {tokens_to_withdraw:.4f} tokens", 
                                    "Info Extra": f"Valor Retirado: ${risk_basis:,.0f}"
                                })
                                
                                # NOTA: Como position=None, en la siguiente línea del bucle (o siguiente día) se reabrirá.

                            # C. DEFENSA
                            elif position and lo <= (position["liq"] * (1 + dyn_th)):
                                trig = position["liq"] * (1 + dyn_th)
                                dp = min(op, trig); nl = dp * 0.80
                                # Para bajar liquidación, necesitamos menos deuda o más colateral. 
                                # Aquí añadimos colateral.
                                needed_amt_total = position["debt"] / (nl * 0.80)
                                add = needed_amt_total - position["amt"]
                                
                                if add > 0:
                                    cost = add * dp
                                    ext_inj += cost
                                    # Si inyectamos dinero, aumentamos nuestra base de riesgo
                                    risk_basis += cost
                                    
                                    position["amt"] += add; position["liq"] = nl
                                    position["def"] = True; act = "DEFENDED"
                                    events.append({"Fecha": d.date(), "Evento": "🛡️ DEFENSA", "Precio": f"${dp:,.0f}", "Detalle": f"Inyección: ${cost:,.0f}", "Info Extra": f"+{add:.4f} tokens"})

                            # D. RESET (TAKE PROFIT TRAS DEFENSA)
                            # Si defendimos y recuperamos entrada, cerramos para limpiar deuda
                            elif position and position["def"] and hi >= position["ent"]:
                                ep = position["ent"]
                                gross = position["amt"] * ep
                                net = gross - position["debt"]
                                wallet_usd = net
                                position = None
                                act = "RESET"
                                events.append({"Fecha": d.date(), "Evento": "💰 RESET", "Precio": f"${ep:,.0f}", "Detalle": "Cierre Táctico", "Info Extra": f"Cash: ${net:,.0f}"})

                    # --- REGISTRO DIARIO ---
                    # Valor Total = (Equity en Estrategia) + (Valor de Tokens Acumulados) + (Cash en mano)
                    strat_equity = 0
                    if position:
                        strat_equity = (position["amt"] * cl) - position["debt"]
                    
                    hodl_bag_val = accumulated_tokens * cl
                    
                    total_wealth = strat_equity + hodl_bag_val + wallet_usd
                    
                    # Inversión Total Real = Capital Inicial + Inyecciones Externas
                    real_investment = dyn_capital + ext_inj
                    
                    # Comparativa: Si hubiera hecho HODL desde el día 1 con el capital inicial
                    # (Sin contar inyecciones posteriores para ser justos con el coste de oportunidad inicial)
                    hodl_only_val = (dyn_capital / df.iloc[0]['Close']) * cl
                    
                    hist.append({
                        "Fecha": d,
                        "Riqueza Total ($)": total_wealth,
                        "HODL Pasivo ($)": hodl_only_val,
                        "Tokens HODL": accumulated_tokens,
                        "Inversión Total ($)": real_investment
                    })

                # --- INFORME FINAL ---
                df_r = pd.DataFrame(hist).set_index("Fecha")
                final_wealth = df_r.iloc[-1]["Riqueza Total ($)"]
                final_inv = df_r.iloc[-1]["Inversión Total ($)"]
                final_hodl = df_r.iloc[-1]["HODL Pasivo ($)"]
                
                roi = ((final_wealth - final_inv) / final_inv) * 100
                roi_hodl = ((final_hodl - dyn_capital) / dyn_capital) * 100

                st.divider()
                st.subheader(f"📊 Informe de Acumulación: {dyn_ticker}")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Patrimonio Final", f"${final_wealth:,.0f}", delta=f"{roi:.2f}% ROI")
                m2.metric("Vs HODL Pasivo", f"${final_hodl:,.0f}", delta=f"{roi - roi_hodl:.2f}% Diff")
                m3.metric("Tokens 'Gratis' (HODL)", f"{accumulated_tokens:.4f}", help="Tokens retirados de la estrategia y asegurados")
                m4.metric("Inversión (Cap + Def)", f"${final_inv:,.0f}")
                
                # Gráfica
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_r.index, y=df_r["Riqueza Total ($)"], name="Estrategia (Acumulación)", line=dict(color="#00CC96", width=2)))
                fig.add_trace(go.Scatter(x=df_r.index, y=df_r["HODL Pasivo ($)"], name="HODL Pasivo", line=dict(color="gray", dash="dot")))
                st.plotly_chart(fig, use_container_width=True)
                
                with st.expander("📜 Ver Diario de Operaciones", expanded=True):
                    if events:
                        st.dataframe(
                            pd.DataFrame(events), 
                            use_container_width=True, 
                            hide_index=True,
                            column_config={
                                "Precio": st.column_config.TextColumn("Precio Mercado"),
                                "Info Extra": st.column_config.TextColumn("Info Adicional")
                            }
                        )
                    else:
                        st.info("Sin operaciones.")

            except Exception as e: st.error(f"Error en simulación: {e}")

# ------------------------------------------------------------------------------
#  PESTAÑA 4: ESCÁNER REAL (MODO SEGURO + MEMORIA)
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
