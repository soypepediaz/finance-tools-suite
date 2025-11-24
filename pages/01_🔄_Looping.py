import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from datetime import date, timedelta
from web3 import Web3
import requests
import os

# ==============================================================================
#  CONFIGURACIÓN DE LA PÁGINA
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
            
            div[data-testid="stMetric"] {
                background-color: #F0F2F6;
                border: 1px solid #E0E0E0;
                border-radius: 10px;
                padding: 10px;
            }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

st.title("🛡️ Looping Master: Calculadora, Backtest & On-Chain")

# ==============================================================================
#  0. GESTIÓN DE SECRETOS Y MARKETING
# ==============================================================================

def get_secret(key):
    """Busca primero en Secrets (Local) y luego en Environment (Railway)"""
    if key in st.secrets:
        return st.secrets[key]
    if key in os.environ:
        return os.environ[key]
    return None

MOOSEND_LIST_ID = "75c61863-63dc-4fd3-9ed8-856aee90d04a"

def add_subscriber_moosend(name, email):
    """Envía el suscriptor a la lista de Moosend vía API"""
    try:
        api_key = get_secret("MOOSEND_API_KEY")
        if not api_key:
            return False, "Falta configuración de API Key."
            
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
                error_resp = response.json()
                error_msg = error_resp.get("Error", "Unknown Error")
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

# ABI LIGERO (AddressProvider + UserData)
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
    return Web3(Web3.HTTPProvider(rpc_url, session=s, request_kwargs={'timeout': 30}))

def connect_robust(network_name):
    config = NETWORKS[network_name]
    rpcs = config["rpcs"][:]
    
    secret_key = f"{network_name.upper()}_RPC_URL"
    private_rpc = get_secret(secret_key)
    used_private = False
    
    if private_rpc:
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
#  3. INTERFAZ DE USUARIO (PESTAÑAS)
# ==============================================================================

tab_home, tab_calc, tab_backtest, tab_onchain = st.tabs([
    "🏠 Inicio", 
    "🧮 Calculadora", 
    "📉 Backtest", 
    "📡 Escáner Real"
])

# --- PESTAÑA 0: PORTADA ---
with tab_home:
    col_hero_L, col_hero_R = st.columns([2, 1])
    
    with col_hero_L:
        st.markdown("# 🛡️ Domina el Looping en DeFi")
        st.markdown("#### Maximiza tus rendimientos sin morir en el intento.")
        st.markdown("Bienvenido a **Looping Master**, la herramienta definitiva para analizar, proyectar y defender tus posiciones.")
        st.info("💡 **Tip:** Navega por las pestañas superiores para usar las herramientas.")

    with col_hero_R:
        st.markdown("### ⛺ Campamento DeFi")
        st.metric("Riesgo", "Gestionado", delta="Alto Rendimiento")

    st.divider()
    st.markdown("### 🚀 ¿Quieres recibir más estrategias como esta?")
    
    c_form_1, c_form_2 = st.columns([3, 2])
    
    with c_form_1:
        st.markdown("""
        Esta herramienta es solo la punta del iceberg. En el **Campamento DeFi** compartimos:
        - Estrategias de Yield Farming avanzadas.
        - Alertas de seguridad y gestión de riesgo.
        
        **Únete gratis a nuestra Newsletter y recibe el 'Manual de Supervivencia DeFi'.**
        """)
        
    with c_form_2:
        with st.form("lead_magnet_form"):
            name_input = st.text_input("Nombre", placeholder="Tu nombre")
            email_input = st.text_input("Email", placeholder="tu@email.com")
            
            submitted = st.form_submit_button("📩 Unirme y Recibir Manual", type="primary")
            
            if submitted:
                if email_input and "@" in email_input:
                    with st.spinner("Enviando..."):
                        ok, msg = add_subscriber_moosend(name_input, email_input)
                        
                    if ok:
                        st.success("¡Bienvenido! Revisa tu correo.")
                        st.balloons()
                    else:
                        st.error(f"Error: {msg}")
                else:
                    st.error("Email inválido.")
    
    st.divider()
    st.caption("Desarrollado con ❤️ por Campamento DeFi.")

# --- PESTAÑA 1: CALCULADORA ---
with tab_calc:
    st.markdown("### 🧮 Simulador Estático")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        selected_asset_calc = st.selectbox("Activo", list(ASSET_MAP.keys()), key="c_s")
        if ASSET_MAP[selected_asset_calc] == "MANUAL":
            c_asset_name = st.text_input("Ticker", value="PEPE", key="c_t")
        else:
            c_asset_name = selected_asset_calc.split("(")[1].replace(")", "")
            
        c_price = st.number_input(f"Precio {c_asset_name}", 100000.0, step=100.0, key="c_p")
        c_target = st.number_input("Objetivo", 130000.0, step=100.0, key="c_target")
        
    with col2:
        c_capital = st.number_input("Capital", 10000.0, step=1000.0, key="c_cap")
        c_leverage = st.slider("Leverage", 1.1, 5.0, 2.0, key="c_lev")
        
    with col3:
        c_ltv = st.slider("LTV Liq %", 50, 95, 78, key="c_ltv") / 100.0
        c_threshold = st.number_input("Umbral %", 15.0, key="c_th") / 100.0
        c_zones = st.slider("Zonas", 1, 10, 5, key="c_z")

    # Cálculos Expandidos
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
    
    # Tabla Cascada Expandida
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
        
        # Nuevo HF
        if c_debt_usd > 0:
            new_hf = ((curr_collat * trig_p) * c_ltv) / c_debt_usd
        else:
            new_hf = 999
            
        # ROI
        total_inv = c_capital + cum_cost
        final_val = curr_collat * c_target
        net_prof = (final_val - c_debt_usd) - total_inv
        roi = (net_prof / total_inv) * 100 if total_inv > 0 else 0
        ratio = roi / (drop_pct * 100) if drop_pct > 0 else 0
        
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

# --- PESTAÑA 2: BACKTEST ---
with tab_backtest:
    st.markdown("### 📉 Validación Histórica")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        sel_bt = st.selectbox("Activo", list(ASSET_MAP.keys()), key="bt_s")
        if ASSET_MAP[sel_bt] == "MANUAL":
            bt_ticker = st.text_input("Ticker Yahoo", value="DOT-USD", key="bt_t")
        else:
            bt_ticker = ASSET_MAP[sel_bt]
        bt_capital = st.number_input("Capital", 10000.0, key="bt_c")
        
    with col2:
        bt_start = st.date_input("Inicio", date.today() - timedelta(days=365*2))
        bt_lev = st.slider("Lev Inicial", 1.1, 4.0, 2.0, key="bt_l")
        
    with col3:
        bt_th = st.number_input("Umbral %", 15.0, key="bt_th") / 100.0
        run_bt = st.button("🚀 Backtest")

    if run_bt:
        with st.spinner(f"Simulando {bt_ticker}..."):
            try:
                df = yf.download(bt_ticker, start=bt_start, progress=False)
                
                if df.empty:
                    st.error("Sin datos.")
                    st.stop()
                
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                p0 = float(df.iloc[0]['Close'])
                col_usd = bt_capital * bt_lev
                debt_usd = col_usd - bt_capital
                amt = col_usd / p0
                liq = debt_usd / (amt * c_ltv) # Usa LTV de la Pestaña 1
                
                hist = []
                inj = 0.0
                dead = False
                
                for d, r in df.iterrows():
                    if pd.isna(r['Close']): continue
                    
                    trig = liq * (1 + bt_th)
                    action = "Hold"
                    
                    if r['Low'] <= trig and not dead:
                        def_p = min(float(r['Open']), trig)
                        
                        if def_p <= liq:
                            dead = True
                            action = "LIQUIDADO"
                        else:
                            # Defensa
                            new_targ = def_p * (liq/p0)
                            need_amt = debt_usd / (new_targ * c_ltv)
                            add = need_amt - amt
                            
                            if add > 0:
                                inj += add * def_p
                                amt += add
                                liq = new_targ
                                action = "DEFENSA"
                    
                    if r['Low'] <= liq:
                        dead = True
                        
                    val = (amt * r['Close']) - debt_usd if not dead else 0
                    
                    hist.append({
                        "Fecha": d, 
                        "Valor": val, 
                        "Inversión": bt_capital + inj,
                        "Acción": action
                    })
                    
                    if dead: break
                
                res_df = pd.DataFrame(hist).set_index("Fecha")
                
                st.metric("Resultado", "LIQUIDADO" if dead else "VIVO", f"Inyectado: ${inj:,.0f}")
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=res_df.index, y=res_df["Valor"], name='Valor Estrategia', line=dict(color='green')))
                fig.add_trace(go.Scatter(x=res_df.index, y=res_df["Inversión"], name='Inversión Total', line=dict(color='red', dash='dash')))
                st.plotly_chart(fig, use_container_width=True)
                
            except Exception as e:
                st.error(f"Error: {e}")
                # ------------------------------------------------------------------------------
#  PESTAÑA 3: ESCÁNER REAL (MODO BLINDADO + MEMORIA)
# ------------------------------------------------------------------------------
with tab_onchain:
    st.markdown("### 📡 Escáner Aave V3 (Modo Seguro)")
    
    col_net, col_addr = st.columns([1, 3])
    
    with col_net:
        net = st.selectbox("Red", list(NETWORKS.keys()))
        
    with col_addr:
        addr = st.text_input("Wallet Address (0x...)", placeholder="0x...")
    
    # Inicializar Memoria
    if 'portfolio_data' not in st.session_state:
        st.session_state.portfolio_data = None

    if st.button("🔍 Analizar"):
        if not addr:
            st.warning("Falta dirección")
        else:
            with st.spinner(f"Conectando a {net}..."):
                w3, rpc, priv = connect_robust(net)
                
                if not w3:
                    st.error("Error de conexión RPC. Revisa tus Secrets.")
                    st.stop()
                
                try:
                    # 1. Obtener Pool Real
                    prov_addr = w3.to_checksum_address(NETWORKS[net]["pool_provider"])
                    prov_contract = w3.eth.contract(address=prov_addr, abi=AAVE_ABI)
                    pool_addr = prov_contract.functions.getPool().call()
                    
                    # 2. Llamada Ligera
                    pool = w3.eth.contract(address=pool_addr, abi=AAVE_ABI)
                    data = pool.functions.getUserAccountData(w3.to_checksum_address(addr)).call()
                    
                    # 3. Guardar
                    st.session_state.portfolio_data = {
                        "col_usd": data[0] / 10**8,
                        "debt_usd": data[1] / 10**8,
                        "lt_avg": data[3] / 10000,
                        "hf": data[5] / 10**18,
                        "status_msg": f"🔒 Privado" if priv else f"🌍 Público"
                    }
                    
                except Exception as e:
                    st.error(f"Error: {e}")

    # Mostrar Resultados
    if st.session_state.portfolio_data:
        d = st.session_state.portfolio_data
        
        st.success(f"✅ Conectado: {d['status_msg']}")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("HF", f"{d['hf']:.2f}", delta_color="normal" if d['hf']>1.1 else "inverse")
        m2.metric("Colateral", f"${d['col_usd']:,.2f}")
        m3.metric("Deuda", f"${d['debt_usd']:,.2f}")
        m4.metric("LT Avg", f"{d['lt_avg']:.2%}")
        
        if d['debt_usd'] > 0:
            st.divider()
            st.subheader("🛠️ Estrategia")
            
            mode = st.radio("Modo:", ["🛡️ Activo Único", "💼 Multi-Colateral"], horizontal=True)
            
            # MODO A: ACTIVO ÚNICO
            if "Activo Único" in mode:
                c_sel, c_par = st.columns(2)
                with c_sel:
                    sim_asset = st.selectbox("Activo Principal", list(ASSET_MAP.keys()), key="oc_a")
                    if ASSET_MAP[sim_asset] == "MANUAL":
                        ticker = st.text_input("Ticker", "ETH-USD", key="oc_t")
                    else:
                        ticker = ASSET_MAP[sim_asset]
                with c_par:
                    def_th = st.number_input("Umbral %", 5.0, key="oc_th") / 100.0
                    zones = st.slider("Zonas", 1, 10, 5, key="oc_z")
                
                try:
                    curr_p = yf.Ticker(ticker).history(period="1d")['Close'].iloc[-1]
                    st.metric(f"Precio {ticker}", f"${curr_p:,.2f}")
                    
                    implied_amt = d['col_usd'] / curr_p
                    liq_real = d['debt_usd'] / (implied_amt * d['lt_avg'])
                    st.metric("Liq Actual", f"${liq_real:,.2f}")
                    
                    ratio_t = liq_real / curr_p
                    s_curr_c = implied_amt
                    s_cum = 0.0
                    s_data = []
                    
                    for i in range(1, zones + 1):
                        if i == 1:
                            trig = liq_real * (1 + def_th)
                        else:
                            trig = s_data[-1]["Activación"] * (1 + def_th)
                            
                        targ = trig * ratio_t
                        need = d['debt_usd'] / (targ * d['lt_avg'])
                        add = max(0, need - s_curr_c)
                        
                        cost = add * trig
                        s_cum += cost
                        s_curr_c += add
                        
                        new_hf = (s_curr_c * trig * d['lt_avg']) / d['debt_usd']
                        
                        s_data.append({
                            "Zona": i, 
                            "Activación": trig, 
                            "Inyectar": add, 
                            "Costo": cost, 
                            "Nuevo Liq": targ, 
                            "Nuevo HF": new_hf
                        })
                    
                    st.dataframe(pd.DataFrame(s_data).style.format({
                        "Activación": "${:,.2f}", "Costo": "${:,.0f}", 
                        "Nuevo Liq": "${:,.2f}", "Nuevo HF": "{:.2f}", "Inyectar": "{:.4f}"
                    }), use_container_width=True)
                    
                except:
                    st.error("Error obteniendo precio.")

            # MODO B: MULTI-COLATERAL
            else:
                if (d['col_usd'] * d['lt_avg']) > 0:
                    max_drop = 1 - (d['debt_usd'] / (d['col_usd'] * d['lt_avg']))
                else:
                    max_drop = 0
                    
                st.metric("Margen Caída", f"{max_drop:.2%}")
                
                thf = st.number_input("HF Objetivo", 1.05, key="oc_hf")
                
                c_w, _ = st.columns(2)
                with c_w:
                    wa = st.selectbox("Testigo", list(ASSET_MAP.keys()), key="wa")
                    wt = ASSET_MAP[wa] if ASSET_MAP[wa] != "MANUAL" else "ETH-USD"
                
                try:
                    wp = yf.Ticker(wt).history(period="1d")['Close'].iloc[-1]
                except:
                    wp = 0

                sim = []
                
                if d['hf'] > 1.0:
                    gap = d['hf'] - 1.0
                    step = gap / 5
                    
                    for i in range(1, 6):
                        trig_hf = d['hf'] - (step * i)
                        if trig_hf <= 1.001: trig_hf = 1.001
                        
                        drop = 1 - (trig_hf / d['hf'])
                        
                        # Colateral tras caída
                        s_col = d['col_usd'] * (1 - drop)
                        
                        # LT valor tras caída
                        s_lt = (d['col_usd'] * d['lt_avg']) * (1 - drop)
                        
                        # Necesidad para restaurar HF
                        need = d['debt_usd'] - (s_lt / d['hf'])
                        if need < 0: need = 0
                        
                        nd = d['debt_usd'] - need
                        
                        if nd > 0:
                            fhf = (s_col * d['lt_avg']) / nd
                        else:
                            fhf = 999.0
                        
                        sim.append({
                            "HF Riesgo": f"{trig_hf:.2f}", 
                            "Caída": f"-{drop:.2%}", 
                            f"Precio {wt}": wp * (1-drop), 
                            "Inyectar ($)": need, 
                            "Nuevo HF": f"{fhf:.2f}"
                        })
                        
                    st.dataframe(
                        pd.DataFrame(sim).style.format({
                            "Inyectar ($)": "${:,.2f}", 
                            f"Precio {wt}": "${:,.2f}"
                        }).background_gradient(subset=["Inyectar ($)"], cmap="Reds"), 
                        use_container_width=True
                    )
                else:
                    st.error("Ya estás en liquidación.")
        else:
            st.success("Sin deuda.")
