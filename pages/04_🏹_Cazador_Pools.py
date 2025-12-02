import streamlit as st
import pandas as pd
import plotly.express as px
from uni_v3_kit.analyzer import MarketScanner
from uni_v3_kit.data_provider import DataProvider
from uni_v3_kit.backtester import Backtester
from auth_module import require_nft_authentication

# Verificar autenticación
require_nft_authentication()

st.set_page_config(page_title="Cazador V3 Lab", layout="wide", initial_sidebar_state="collapsed")

# --- ESTILOS CSS ---
st.markdown("""
<style>
    [data-testid="stSidebar"] {display: none;}
    .main .block-container {padding-top: 2rem;}
    h1 {text-align: center; color: #FF4B4B;}
    .stButton button {width: 100%; border-radius: 8px; font-weight: bold;}
    div[data-testid="stMetricValue"] {font-size: 1.4rem;}
</style>
""", unsafe_allow_html=True)

# --- GESTIÓN DE NAVEGACIÓN ---
if 'step' not in st.session_state: st.session_state.step = 'home'
if 'scan_params' not in st.session_state: st.session_state.scan_params = {}
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'selected_pool' not in st.session_state: st.session_state.selected_pool = None

def go_home():
    st.session_state.step = 'home'
    st.session_state.scan_results = None

def go_to_results(df):
    st.session_state.scan_results = df
    st.session_state.step = 'results'

def go_to_lab(pool_row):
    st.session_state.selected_pool = pool_row
    st.session_state.step = 'lab'

# ==========================================
# 1. INICIO
# ==========================================
if st.session_state.step == 'home':
    st.title("🏹 Cazador de Oportunidades en (mucho)pools")
    st.markdown("---")
    
    c1, c2, c3 = st.columns([1, 3, 1])
    with c2:
        st.subheader("¿Qué quieres hacer hoy?")
        modo = st.radio("", ["🔍 Escanear Mercado (Búsqueda Avanzada)", "🎯 Analizar un Pool Específico (por contrato)"], label_visibility="collapsed")
        st.write("") 
        
        if modo == "🔍 Escanear Mercado (Búsqueda Avanzada)":
            with st.form("scanner_form"):
                st.markdown("### ⚙️ Configuración del Escáner")
                
                @st.cache_data(ttl=3600)
                def get_chains():
                    p = DataProvider(); 
                    try: return sorted(list({x.get('ChainId') for x in p.get_all_pools() if x.get('ChainId')}))
                    except: return ["ethereum", "arbitrum", "base", "bsc"]
                
                chains = st.multiselect("Redes (Deja vacío para todas)", get_chains(), default=[])
                
                c_a, c_b = st.columns(2)
                with c_a:
                    min_tvl = st.number_input("TVL Mínimo ($)", value=250000, step=50000)
                    dias_window = st.slider("Ventana Análisis (Días)", 3, 30, 7, help="Días para calcular medias.")
                
                with c_b:
                    min_apr = st.number_input("APR Mínimo (%)", value=10.0, step=1.0)
                    sd_mult = st.slider("Factor Rango (SD)", 0.1, 3.0, 1.0, step=0.1, help="Amplitud para calcular el IL de salida.")

                st.markdown("**Filtrar por Activos:**")
                assets = ["BTC", "ETH", "SOL", "HYPE", "BNB", "Otro"]
                selected_assets = []
                
                cols_assets = st.columns(6)
                for i, asset in enumerate(assets):
                    if cols_assets[i].checkbox(asset):
                        selected_assets.append(asset)
                
                custom_asset = None
                if "Otro" in selected_assets:
                    custom_asset = st.text_input("Escribe el símbolo (ej: PEPE, USDC):")

                st.markdown("---")
                submitted = st.form_submit_button("🚀 Escanear Mercado")
                
                if submitted:
                    scanner = MarketScanner()
                    with st.spinner("Analizando pools... esto puede tardar unos segundos"):
                        target_chains = chains if chains else None
                        
                        df = scanner.scan(
                            target_chains=target_chains,
                            min_tvl=min_tvl,
                            days_window=dias_window,
                            sd_multiplier=sd_mult,
                            min_apr=min_apr,
                            selected_assets=selected_assets,
                            custom_asset=custom_asset
                        )
                        
                        if not df.empty:
                            st.session_state.scan_params = {'dias': dias_window, 'sd': sd_mult}
                            go_to_results(df)
                            st.rerun()
                        else:
                            st.error("No se encontraron pools con esos criterios.")

        else: 
            with st.form("manual_form"):
                st.markdown("### 🎯 Análisis Directo")
                address = st.text_input("Dirección del Contrato (0x...):")
                
                c_a, c_b = st.columns(2)
                with c_a:
                    dias_window = st.slider("Ventana Análisis (Días)", 3, 30, 7)
                with c_b:
                    sd_mult = st.slider("Factor Rango (SD)", 0.1, 3.0, 1.0, step=0.1)
                
                submitted_manual = st.form_submit_button("🔎 Analizar Pool")
                
                if submitted_manual:
                    if not address:
                        st.error("Introduce una dirección.")
                    else:
                        scanner = MarketScanner()
                        with st.spinner("Buscando datos..."):
                            df = scanner.analyze_single_pool(address, days_window=dias_window, sd_multiplier=sd_mult)
                            if not df.empty:
                                st.session_state.scan_params = {'dias': dias_window, 'sd': sd_mult}
                                go_to_results(df)
                                st.rerun()
                            else:
                                st.error("No se encontraron datos para esa dirección.")

# ==========================================
# 2. RESULTADOS
# ==========================================
elif st.session_state.step == 'results':
    c_back, c_title = st.columns([1, 6])
    c_back.button("⬅️ Inicio", on_click=go_home)
    c_title.subheader("📊 Resultados del Análisis")
    
    df = st.session_state.scan_results
    dias = st.session_state.scan_params.get('dias', 7)
    sd = st.session_state.scan_params.get('sd', 1.0)
    
    st.info(f"""
    **Top {len(df)} Oportunidades.** Ordenado por **Ratio F/IL**.
    Criterio: Fees Probables ({dias}d) vs Riesgo Salida ({sd} SD).
    """)
    
    df_display = df.copy()
    col_apr = [c for c in df_display.columns if "APR (" in c][0]
    df_display[col_apr] = df_display[col_apr] * 100
    
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Address": None, 
            "TVL": st.column_config.NumberColumn(format="$%d"),
            col_apr: st.column_config.NumberColumn(format="%.1f%%"),
            "Volatilidad": st.column_config.NumberColumn(format="%.1f%%"),
            "Rango Est.": st.column_config.NumberColumn("Rango (±%)", format="%.1f%%"),
            "Est. Fees": st.column_config.NumberColumn(f"Fees Prob.", format="%.2f%%"),
            "IL": st.column_config.NumberColumn("IL (Riesgo)", format="%.2f%%"),
            "Ratio F/IL": st.column_config.NumberColumn("Ratio F/IL", format="%.2f", help="Mayor es mejor"),
            "Margen": None 
        }
    )
    
    st.subheader("🧪 Seleccionar para Laboratorio")
    c1, c2 = st.columns([3, 1])
    with c1:
        df_display = df.reset_index(drop=True)
        def format_option(idx):
            row = df_display.iloc[idx]
            return f"{row['Par']} ({row['DEX']} - {row['Red']}) | Ratio: {row['Ratio F/IL']:.2f}"
        sel_idx = st.selectbox("Pool:", options=df_display.index, format_func=format_option)
    with c2:
        st.write(""); st.write("")
        if st.button("Ir al Laboratorio ➡️", use_container_width=True):
            row = df.iloc[sel_idx]
            go_to_lab(row)
            st.rerun()

# ==========================================
# 3. LABORATORIO
# ==========================================
elif st.session_state.step == 'lab':
    pool = st.session_state.selected_pool
    st.button("⬅️ Volver", on_click=lambda: setattr(st.session_state, 'step', 'results'))
    
    st.title(f"🧪 Lab: {pool['Par']}")
    col_apr_lab = [c for c in pool.index if "APR (" in c][0]
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("DEX", f"{pool['DEX']} ({pool['Red']})") 
    c2.metric("TVL", f"${pool['TVL']:,.0f}")
    val_apr = pool[col_apr_lab] * 100 
    c3.metric("APR Medio", f"{val_apr:.1f}%")
    c4.metric("Ratio F/IL", f"{pool.get('Ratio F/IL', 0):.2f}")
    
    st.markdown("---")
    
    with st.container():
        c_conf1, c_conf2 = st.columns(2)
        with c_conf1:
            st.subheader("⚙️ Simulación")
            inversion = st.number_input("Inversión ($)", 1000, 1000000, 10000)
            dias_sim = st.slider("Días a Simular", 7, 180, 30)
            vol_days = st.sidebar.slider("Ventana Volatilidad", 3, 30, 7) if 'vol_days' not in st.session_state else st.session_state.vol_days # FIX: Mover sliders al main
            # Muevo los sliders de estrategia aquí abajo para que estén juntos
            
        with c_conf2:
            st.subheader("🎯 Estrategia")
            sd_def = st.session_state.scan_params.get('sd', 1.0)
            vol_def = st.session_state.scan_params.get('dias', 7)
            
            sd_mult_lab = st.slider("Amplitud Rango (SD)", 0.1, 3.0, sd_def, step=0.1)
            vol_days_lab = st.slider("Ventana Volatilidad (Lookback)", 3, 30, vol_def)
            auto_rebalance = st.checkbox("Auto-Rebalancear (Coste 0.3%)", value=False)
    
    if st.button("🚀 Ejecutar Simulación Histórica", use_container_width=True):
        address = pool.get('Address')
        if not address: st.error("Error: Falta dirección.")
        else:
            with st.spinner("Simulando..."):
                provider = DataProvider()
                tester = Backtester()
                history_data = provider.get_pool_history(address).get('history', [])
                
                fee_est = 0.003 
                if "0.05%" in str(pool['Par']): fee_est = 0.0005
                elif "0.01%" in str(pool['Par']): fee_est = 0.0001
                elif "1%" in str(pool['Par']): fee_est = 0.01

                df_res, min_p, max_p, meta = tester.run_simulation(
                    history_data, inversion, sd_mult_lab, 
                    sim_days=dias_sim, vol_days=vol_days_lab, 
                    fee_tier=fee_est, auto_rebalance=auto_rebalance
                )
                
                if df_res is not None and not df_res.empty:
                    last = df_res.iloc[-1]
                    roi_v3 = (last['Valor Total'] - inversion) / inversion
                    roi_hodl = (last['HODL Value'] - inversion) / inversion
                    
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Valor Final V3", f"${last['Valor Total']:,.0f}", delta=f"{roi_v3*100:.2f}%")
                    k2.metric("Valor HODL", f"${last['HODL Value']:,.0f}", delta=f"{roi_hodl*100:.2f}%")
                    k3.metric("Fees Totales", f"${last['Fees Acum']:,.2f}")
                    
                    if auto_rebalance: st.info(f"🔄 **{meta['rebalances']} rebalanceos** realizados.")
                    
                    p_ini = df_res.iloc[0]['Price']
                    w_pct = meta['initial_range_width_pct'] * 100
                    st.info(f"**Rango Inicial:** ±{w_pct:.1f}%. Entrada: {p_ini:.4f}. Límites: {min_p:.4f} - {max_p:.4f}")
                    
                    # Gráficos
                    st.subheader("💰 Rendimiento")
                    fig1 = px.line(df_res, x='Date', y=['Valor Total', 'HODL Value'], 
                                   color_discrete_map={"Valor Total": "#00CC96", "HODL Value": "#EF553B"})
                    st.plotly_chart(fig1, use_container_width=True)
                    
                    st.subheader("📊 Precio y Rangos")
                    df_res['Estado'] = df_res['In Range'].apply(lambda x: '🟢 En Rango' if x else '🔴 Fuera')
                    df_res['Ancho Rango'] = df_res['Range Width %'].apply(lambda x: f"±{x:.1f}%")

                    fig_price = px.scatter(df_res, x='Date', y='Price', color='Estado',
                                           color_discrete_map={'🟢 En Rango': 'green', '🔴 Fuera': 'red'},
                                           hover_data={'Ancho Rango': True})
                    fig_price.add_traces(px.line(df_res, x='Date', y='Price').update_traces(line=dict(color='lightgray', width=1)).data[0])
                    
                    if not auto_rebalance:
                        fig_price.add_hline(y=min_p, line_dash="dash", line_color="red")
                        fig_price.add_hline(y=max_p, line_dash="dash", line_color="green")
                    else:
                        fig_price.add_traces(px.line(df_res, x='Date', y='Range Min').update_traces(line=dict(color='red', dash='dash')).data[0])
                        fig_price.add_traces(px.line(df_res, x='Date', y='Range Max').update_traces(line=dict(color='green', dash='dash')).data[0])
                        
                    st.plotly_chart(fig_price, use_container_width=True)
                    
                    with st.expander("Ver Tabla Detallada ({} registros)".format(len(df_res)), expanded=True):
                        cols = ["Date", "Price", "Range Min", "Range Max", "Range Width %", "APR Period", "Fees Period", "Valor Total"]
                        
                        st.dataframe(
                            df_res[cols],
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Date": st.column_config.DatetimeColumn("Fecha", format="DD/MM/YYYY HH:mm"),
                                "Price": st.column_config.NumberColumn("Precio", format="%.4f"),
                                "Range Min": st.column_config.NumberColumn("Min", format="%.4f"),
                                "Range Max": st.column_config.NumberColumn("Max", format="%.4f"),
                                "Range Width %": st.column_config.NumberColumn("Ancho (±%)", format="%.2f %%"),
                                "APR Period": st.column_config.NumberColumn("APR Anual (Inst.)", format="%.2f%%"),
                                "Fees Period": st.column_config.NumberColumn("Fees (8h)", format="$%.2f"),
                                "Valor Total": st.column_config.NumberColumn("Total", format="$%.2f"),
                            }
                        )
                else: st.error("Datos insuficientes.")

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
