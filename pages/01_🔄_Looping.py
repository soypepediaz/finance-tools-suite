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

tab_home, tab_calc, tab_backtest, tab_onchain = st.tabs([
    "🏠 Inicio", 
    "🧮 Calculadora", 
    "📉 Backtest", 
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
#  PESTAÑA 1: CALCULADORA ESTÁTICA
# ------------------------------------------------------------------------------
with tab_calc:
    st.markdown("### 🧮 Simulador Estático de Defensa")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        selected_asset_calc = st.selectbox("Seleccionar Activo", list(ASSET_MAP.keys()), key="sel_asset_c")
        if ASSET_MAP[selected_asset_calc] == "MANUAL":
            c_asset_name = st.text_input("Ticker", value="PEPE", key="c_asset_man")
        else:
            c_asset_name = selected_asset_calc.split("(")[1].replace(")", "")
            
        c_price = st.number_input(f"Precio Actual {c_asset_name} ($)", value=100000.0, step=100.0, key="c_price")
        c_target = st.number_input(f"Precio Objetivo ($)", value=130000.0, step=100.0, key="c_target")
        
    with col2:
        c_capital = st.number_input("Capital Inicial ($)", value=10000.0, step=1000.0, key="c_capital")
        c_leverage = st.slider("Apalancamiento (x)", 1.1, 5.0, 2.0, 0.1, key="c_lev")
        
    with col3:
        c_ltv = st.slider("LTV Liquidación (%)", 50, 95, 78, 1, key="c_ltv") / 100.0
        c_threshold = st.number_input("Umbral Defensa (%)", value=15.0, step=1.0, key="c_th") / 100.0
        c_zones = st.slider("Zonas de Defensa", 1, 10, 5, key="c_zones")

    # Cálculos base
    c_collat_usd = c_capital * c_leverage
    c_debt_usd = c_collat_usd - c_capital
    c_collat_amt = c_collat_usd / c_price
    
    if c_collat_amt > 0 and c_ltv > 0:
        c_liq_price = c_debt_usd / (c_collat_amt * c_ltv)
        c_target_ratio = c_liq_price / c_price 
        c_cushion_pct = (c_price - c_liq_price) / c_price
    else:
        c_liq_price = 0
        c_target_ratio = 0
        c_cushion_pct = 0
    
    # Generación de tabla en cascada
    cascade_data = []
    curr_collat = c_collat_amt
    curr_liq = c_liq_price
    cum_cost = 0.0
    
    for i in range(1, c_zones + 1):
        trig_p = curr_liq * (1 + c_threshold)
        drop_pct = (c_price - trig_p) / c_price
        targ_liq = trig_p * c_target_ratio
        
        if targ_liq > 0:
            need_col = c_debt_usd / (targ_liq * c_ltv)
            add_col = need_col - curr_collat
        else:
            add_col = 0
            
        add_col = max(0, add_col)
        
        cost = add_col * trig_p
        cum_cost += cost
        curr_collat += add_col
        
        # Métricas financieras
        total_inv = c_capital + cum_cost
        final_val = curr_collat * c_target
        net_prof = (final_val - c_debt_usd) - total_inv
        
        if total_inv > 0:
            roi = (net_prof / total_inv) * 100
        else:
            roi = 0
            
        if drop_pct > 0:
            ratio = roi / (drop_pct * 100)
        else:
            ratio = 0
        
        # Nuevo HF
        if c_debt_usd > 0:
            new_hf = ((curr_collat * trig_p) * c_ltv) / c_debt_usd
        else:
            new_hf = 999
        
        cascade_data.append({
            "Zona": f"#{i}", 
            "Precio Activación": trig_p, 
            "Caída (%)": drop_pct, 
            "Inversión Extra ($)": cost, 
            "Total Invertido ($)": total_inv, 
            "Nuevo P. Liq": targ_liq, 
            "Nuevo HF": new_hf,
            "Beneficio ($)": net_prof, 
            "ROI (%)": roi, 
            "Ratio": ratio
        })
        curr_liq = targ_liq

    st.divider()
    st.dataframe(
        pd.DataFrame(cascade_data).style.format({
            "Precio Activación": "${:,.2f}", 
            "Caída (%)": "{:.2%}", 
            "Inversión Extra ($)": "${:,.0f}", 
            "Total Invertido ($)": "${:,.0f}", 
            "Nuevo P. Liq": "${:,.2f}", 
            "Nuevo HF": "{:.2f}",
            "Beneficio ($)": "${:,.0f}", 
            "ROI (%)": "{:.2f}%", 
            "Ratio": "{:.2f}"
        }), 
        use_container_width=True
    )
    
    if not pd.DataFrame(cascade_data).empty:
        st.divider()
        last_row = pd.DataFrame(cascade_data).iloc[-1]
        st.markdown(f"""
        ### 📝 Informe Ejecutivo
        **Configuración Inicial:** Capital: **\${c_capital:,.0f}** | Apalancamiento: **{c_leverage}x** | Precio Liq. Inicial: **\${c_liq_price:,.2f}**.
        
        **Escenario Extremo:** Si el mercado cae un **{last_row['Caída (%)']:.1%}**, necesitarás haber inyectado un total de **\${last_row['Total Invertido ($)']-c_capital:,.0f}** para sobrevivir. Si tras eso el precio recupera al objetivo, tu ROI sería del **{last_row['ROI (%)']:.2f}%**.
        """)

# ------------------------------------------------------------------------------
#  PESTAÑA 2: MOTOR DE BACKTESTING
# ------------------------------------------------------------------------------
with tab_backtest:
    st.markdown("### 📉 Validación Histórica")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_asset_bt = st.selectbox("Seleccionar Activo Histórico", list(ASSET_MAP.keys()), key="sel_asset_bt")
        if ASSET_MAP[selected_asset_bt] == "MANUAL":
            bt_ticker = st.text_input("Ticker Yahoo", value="DOT-USD", key="bt_t")
        else:
            bt_ticker = ASSET_MAP[selected_asset_bt]
        bt_capital = st.number_input("Capital Inicial ($)", value=10000.0, key="bt_cap")
    
    with col2:
        bt_start_date = st.date_input("Fecha Inicio", value=date.today() - timedelta(days=365*2))
        bt_leverage = st.slider("Apalancamiento Inicial", 1.1, 4.0, 2.0, 0.1, key="bt_lev")
    
    with col3:
        bt_threshold = st.number_input("Umbral Defensa (%)", value=15.0, step=1.0, key="bt_th") / 100.0
        run_bt = st.button("🚀 Ejecutar Backtest", type="primary")

    if run_bt:
        with st.spinner(f"Simulando {bt_ticker}..."):
            try:
                df_hist = yf.download(bt_ticker, start=bt_start_date, end=date.today(), progress=False)
                
                if df_hist.empty:
                    st.error("Sin datos.")
                    st.stop()
                
                if isinstance(df_hist.columns, pd.MultiIndex):
                    df_hist.columns = df_hist.columns.get_level_values(0)

                start_date_actual = df_hist.index[0].date()
                start_price = float(df_hist.iloc[0]['Close']) 
                
                # Variables iniciales
                collateral_usd = bt_capital * bt_leverage
                debt_usd = collateral_usd - bt_capital 
                collateral_amt = collateral_usd / start_price 
                
                ltv_liq = c_ltv # Usamos el LTV de la pestaña 1
                liq_price = debt_usd / (collateral_amt * ltv_liq)
                target_ratio = liq_price / start_price 
                
                history = []
                total_injected = 0.0
                is_liquidated = False
                
                for date_idx, row in df_hist.iterrows():
                    if pd.isna(row['Close']): continue
                    
                    low_val = float(row['Low'])
                    close_val = float(row['Close'])
                    open_val = float(row['Open'])
                    
                    trigger_price = liq_price * (1 + bt_threshold)
                    action = "Hold"
                    
                    if low_val <= trigger_price and not is_liquidated:
                        defense_price = min(float(row['Open']), trigger_price) 
                        
                        if defense_price <= liq_price:
                            is_liquidated = True
                            action = "LIQUIDATED ☠️"
                        else:
                            # Defensa
                            target_liq_new = defense_price * (liq_price / start_price)
                            needed_collat_amt = debt_usd / (target_liq_new * ltv_liq)
                            add_collat_amt = needed_collat_amt - collateral_amt
                            
                            if add_collat_amt > 0:
                                total_injected += add_collat_amt * defense_price
                                collateral_amt += add_collat_amt
                                liq_price = target_liq_new 
                                action = "DEFENSA 🛡️"
                    
                    if low_val <= liq_price and not is_liquidated:
                        is_liquidated = True
                        
                    if not is_liquidated:
                        pos_value = (collateral_amt * close_val) - debt_usd
                    else:
                        pos_value = 0
                        
                    history.append({
                        "Fecha": date_idx, 
                        "Acción": action, 
                        "Liq Price": liq_price if not is_liquidated else 0,
                        "Inversión Acumulada": bt_capital + total_injected, 
                        "Valor Estrategia": pos_value if not is_liquidated else 0, 
                        "Valor HODL": (bt_capital / start_price) * close_val 
                    })
                    
                    if is_liquidated: break
                
                df_res = pd.DataFrame(history).set_index("Fecha")
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Resultado", "LIQUIDADO" if is_liquidated else "VIVO")
                c2.metric("Inyectado Total", f"${total_injected:,.0f}")
                if not df_res.empty:
                    c3.metric("Valor Final", f"${df_res.iloc[-1]['Valor Estrategia']:,.0f}")
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Valor Estrategia"], name='Estrategia', fill='tozeroy', line=dict(color='green')))
                fig.add_trace(go.Scatter(x=df_res.index, y=df_res["Inversión Acumulada"], name='Inversión', line=dict(color='red', dash='dash')))
                
                events = df_res[df_res["Acción"].str.contains("DEFENSA", na=False)]
                if not events.empty:
                    fig.add_trace(go.Scatter(x=events.index, y=events["Valor Estrategia"], mode='markers', name='Defensa', marker=dict(color='orange', size=10, symbol='diamond')))
                
                st.plotly_chart(fig, use_container_width=True)
                
                st.divider()
                st.subheader("🏁 Datos de Entrada")
                st.write(f"Inicio: {start_date_actual} | Precio Entrada: ${start_price:,.2f} | Deuda Inicial: ${debt_usd:,.0f}")

            except Exception as e:
                st.error(f"Error: {e}")

# ------------------------------------------------------------------------------
#  PESTAÑA 3: ESCÁNER REAL (MODO SEGURO + MEMORIA)
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
