import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Liquidity Pro Calc", layout="wide")
st.title("🧪 Laboratorio de Liquidez: Simulación & Backtest")
st.markdown("---")

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("1. Configuración de Estrategia")
    
    capital_inicial = st.number_input("Capital Inicial ($)", value=10000.0)
    
    st.subheader("Estrategia ESTÁTICA")
    col_bb1, col_bb2 = st.columns(2)
    with col_bb1:
        bb_window = st.number_input("Ventana (Días)", value=30, min_value=1, max_value=90, help="Días para cálculo de volatilidad.")
    with col_bb2:
        std_estatica = st.number_input("Ancho (SD)", value=2.0, step=0.1, min_value=0.5, max_value=5.0)
    apr_base_estatica = st.number_input("APR Base Estática (%)", value=15.0) / 100
    
    st.subheader("Estrategia DINÁMICA")
    pct_ancho_dinamico = st.slider("% del Ancho Estático", 5, 100, 25, step=5)
    
    st.subheader("Costes Operativos")
    gas_rebalanceo = st.number_input("Gas por Rebalanceo ($)", value=5.0)
    swap_fee = st.number_input("Swap Fee del Pool (%)", value=0.30, step=0.01, format="%.2f") / 100
    
    factor_concentracion = 1 / (pct_ancho_dinamico / 100)
    st.markdown("---")
    st.info(f"⚡ **Multiplicador APR:** {factor_concentracion:.1f}x ({(apr_base_estatica * factor_concentracion)*100:.1f}%)")

# --- 3. FUNCIONES DEL NÚCLEO ---

def generar_montecarlo_precios(precio, vol, tendencia, dias, n_sims):
    dt = 1/365
    shocks = np.random.normal(0, 1, (dias, n_sims))
    drift = (tendencia - 0.5 * vol**2) * dt
    diffusion = vol * np.sqrt(dt) * shocks
    log_retornos = np.cumsum(drift + diffusion, axis=0)
    precios = precio * np.exp(log_retornos)
    fila_cero = np.full((1, n_sims), precio)
    precios = np.vstack([fila_cero, precios])
    return precios

def calcular_valor_v3_exacto(cap_entrada, p_entry, p_exit, p_min, p_max):
    if p_exit >= p_max: 
        precio_promedio = np.sqrt(p_entry * p_max)
        return (cap_entrada * 0.5) + ((cap_entrada * 0.5 / p_entry) * precio_promedio)
    elif p_exit <= p_min:
        precio_promedio = np.sqrt(p_entry * p_min)
        tokens = (cap_entrada * 0.5 / p_entry) + (cap_entrada * 0.5 / precio_promedio)
        return tokens * p_exit
    return cap_entrada

def ejecutar_analisis_operaciones(precios_matrix, cap_inicial, apr_base, std_st, pct_dyn, gas, fee_swap, vol_anual, window_days):
    filas, columnas = precios_matrix.shape
    factor_concentracion = 1 / (pct_dyn / 100)
    fee_diario_st = apr_base / 365
    fee_diario_dyn = (apr_base * factor_concentracion) / 365 
    
    res_st_final = []
    res_dyn_final = []
    stats_rebalanceos = []
    
    # Logs
    log_operaciones_dyn = [] 
    log_diario_estatica = []
    
    # Historial de rangos (para gráfico)
    hist_dyn_upper = []
    hist_dyn_lower = []

    show_progress = columnas > 1
    if show_progress:
        progress_bar = st.progress(0)

    for sim_idx in range(columnas):
        if show_progress and sim_idx % (columnas // 10 + 1) == 0:
            progress_bar.progress(sim_idx / columnas)
            
        serie_precios = precios_matrix[:, sim_idx]
        p_inicial = serie_precios[0]
        
        # --- ESTÁTICA ---
        vol_periodo = vol_anual * np.sqrt(window_days/365)
        delta_st = p_inicial * vol_periodo * std_st
        p_min_st = p_inicial - delta_st
        p_max_st = p_inicial + delta_st
        
        # Estática Final
        p_final = serie_precios[-1]
        val_estatico = calcular_valor_v3_exacto(cap_inicial, p_inicial, p_final, p_min_st, p_max_st)
        in_range_mask = (serie_precios >= p_min_st) & (serie_precios <= p_max_st)
        dias_in_st = np.sum(in_range_mask)
        fees_st = dias_in_st * (cap_inicial * fee_diario_st)
        res_st_final.append(val_estatico + fees_st)
        
        # --- DINÁMICA ---
        cap_dyn = cap_inicial
        delta_dyn = delta_st * (pct_dyn / 100)
        p_min_dyn = p_inicial - delta_dyn
        p_max_dyn = p_inicial + delta_dyn
        
        fees_acumulados_operacion = 0
        num_rebalanceos = 0
        ratio_width = delta_dyn / p_inicial
        
        # Guardar estado inicial para gráficos (día 0)
        if sim_idx == 0:
            hist_dyn_upper.append(p_max_dyn)
            hist_dyn_lower.append(p_min_dyn)
        
        # Bucle diario
        for dia in range(1, filas):
            p_hoy = serie_precios[dia]
            
            # Gráficos y Log Estática (Solo simulación 0)
            if sim_idx == 0:
                hist_dyn_upper.append(p_max_dyn)
                hist_dyn_lower.append(p_min_dyn)
                
                en_rango_st = p_min_st <= p_hoy <= p_max_st
                log_diario_estatica.append({
                    "Día Índice": dia,
                    "Precio": p_hoy,
                    "En Rango": "✅" if en_rango_st else "❌"
                })

            # Lógica Dinámica
            if p_min_dyn <= p_hoy <= p_max_dyn:
                fees_acumulados_operacion += cap_dyn * fee_diario_dyn
            else:
                # --- RUPTURA DE RANGO (Rebalanceo) ---
                num_rebalanceos += 1
                
                evento = "Ruptura Superior ⬆️" if p_hoy > p_max_dyn else "Ruptura Inferior ⬇️"
                rango_previo_str = f"{p_min_dyn:.2f} - {p_max_dyn:.2f}"
                
                p_ref_anterior = (p_max_dyn + p_min_dyn) / 2
                val_salida_pool = calcular_valor_v3_exacto(cap_dyn, p_ref_anterior, p_hoy, p_min_dyn, p_max_dyn)
                
                # IL Realizado
                val_hold = (cap_dyn * 0.5) + ((cap_dyn * 0.5 / p_ref_anterior) * p_hoy)
                il_realizado = max(0, val_hold - val_salida_pool)
                
                # Costes
                coste_swap = val_salida_pool * 0.50 * fee_swap
                costes_totales = coste_swap + gas
                
                # Capital Final Operación
                cap_nuevo = val_salida_pool + fees_acumulados_operacion - costes_totales
                
                if sim_idx == 0:
                    log_operaciones_dyn.append({
                        "Operación": num_rebalanceos,
                        "Día Índice": dia,
                        "Rango Activo": rango_previo_str,
                        "Precio Ejecución": p_hoy,
                        "Evento": evento,
                        "Fees Generados": fees_acumulados_operacion,
                        "Pérdida IL (Info)": il_realizado,
                        "Costes (Swap+Gas)": costes_totales,
                        "Capital Final": cap_nuevo
                    })
                
                # Reset
                cap_dyn = cap_nuevo
                fees_acumulados_operacion = 0
                nuevo_delta = p_hoy * ratio_width
                p_min_dyn = p_hoy - nuevo_delta
                p_max_dyn = p_hoy + nuevo_delta

        # --- AL SALIR DEL BUCLE (FIN DEL PERIODO) ---
        # Si la operación sigue abierta, hay que registrarla
        if sim_idx == 0:
            # Calculamos valor final 'Mark to Market'
            p_cierre = serie_precios[-1]
            p_ref_final = (p_max_dyn + p_min_dyn) / 2
            
            # Valor actual de la posición (puede tener IL latente)
            val_final_pool = calcular_valor_v3_exacto(cap_dyn, p_ref_final, p_cierre, p_min_dyn, p_max_dyn)
            
            # IL Latente (solo informativo)
            val_hold_final = (cap_dyn * 0.5) + ((cap_dyn * 0.5 / p_ref_final) * p_cierre)
            il_latente = max(0, val_hold_final - val_final_pool)
            
            log_operaciones_dyn.append({
                "Operación": num_rebalanceos + 1, # Es la siguiente a la última cerrada
                "Día Índice": filas - 1,
                "Rango Activo": f"{p_min_dyn:.2f} - {p_max_dyn:.2f}",
                "Precio Ejecución": p_cierre,
                "Evento": "Cierre Fin Periodo 🏁",
                "Fees Generados": fees_acumulados_operacion,
                "Pérdida IL (Info)": il_latente, # Aquí es latente, no realizado por venta
                "Costes (Swap+Gas)": 0.0, # No hay coste porque no rebalanceamos, solo cerramos contabilidad
                "Capital Final": val_final_pool + fees_acumulados_operacion
            })

        # Resultado final total acumulado
        val_final_dyn_total = cap_dyn + fees_acumulados_operacion
        # Ajuste: Si cerramos fuera de rango, el valor ya refleja la conversión, si cerramos dentro, refleja el valor mixto
        # En la lógica anterior 'val_final_pool' ya hace esto. 
        # Para mantener coherencia con el array de montecarlo:
        p_cierre_loop = serie_precios[-1]
        p_ref_loop = (p_max_dyn + p_min_dyn) / 2
        val_cierre_loop = calcular_valor_v3_exacto(cap_dyn, p_ref_loop, p_cierre_loop, p_min_dyn, p_max_dyn)
        
        res_dyn_final.append(val_cierre_loop + fees_acumulados_operacion)
        stats_rebalanceos.append(num_rebalanceos)

    if show_progress:
        progress_bar.empty()
        
    return (np.array(res_st_final), np.array(res_dyn_final), 
            log_operaciones_dyn, log_diario_estatica,
            hist_dyn_upper, hist_dyn_lower,
            dias_in_st, delta_st)

# --- 4. INTERFAZ ---

tab1, tab2 = st.tabs(["🎲 Simulación Montecarlo", "📉 Backtesting Histórico"])

# ==========================================
# PESTAÑA 1: MONTECARLO
# ==========================================
with tab1:
    col_inp1, col_inp2, col_inp3 = st.columns(3)
    with col_inp1: precio_actual = st.number_input("Precio Inicial ($)", value=65000.0)
    with col_inp2: volatilidad_anual = st.slider("Volatilidad (%)", 10, 200, 60) / 100
    with col_inp3: tendencia_anual = st.slider("Tendencia (%)", -50, 150, 0) / 100
    
    col_s1, col_s2 = st.columns(2)
    with col_s1: n_simulaciones = st.slider("Simulaciones", 50, 1000, 200, step=50)
    with col_s2: dias_analisis = st.slider("Días Proyección", 7, 365, 30)
    
    if st.button("🚀 Ejecutar Montecarlo"):
        matriz = generar_montecarlo_precios(precio_actual, volatilidad_anual, tendencia_anual, dias_analisis, n_simulaciones)
        
        # Ejecutamos
        res_st, res_dyn, log_ops, log_st, h_up, h_low, dias_in_st, delta_viz = ejecutar_analisis_operaciones(
            matriz, capital_inicial, apr_base_estatica, std_estatica, pct_ancho_dinamico, 
            gas_rebalanceo, swap_fee, volatilidad_anual, bb_window
        )
        
        # Resultados
        m_st, m_dyn = np.mean(res_st), np.mean(res_dyn)
        c1, c2, c3 = st.columns(3)
        c1.metric("Estática (Media)", f"${m_st:,.0f}", f"{m_st-capital_inicial:+.0f} $")
        c2.metric("Dinámica (Media)", f"${m_dyn:,.0f}", f"{m_dyn-capital_inicial:+.0f} $")
        c3.metric("Diferencia", f"${m_dyn-m_st:,.0f}", delta_color="normal")
        
        # Gráfico Cono
        p10, p50, p90 = np.percentile(matriz, 10, axis=1), np.percentile(matriz, 50, axis=1), np.percentile(matriz, 90, axis=1)
        x = np.arange(len(p50))
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=np.concatenate([x, x[::-1]]), y=np.concatenate([p90, p10[::-1]]), fill='toself', fillcolor='rgba(0,150,255,0.15)', line=dict(width=0), name='80% Prob.'))
        fig.add_trace(go.Scatter(x=x, y=p50, mode='lines', line=dict(color='white'), name='Mediana'))
        fig.add_hline(y=precio_actual+delta_viz, line_dash="dash", line_color="#2ecc71")
        fig.add_hline(y=precio_actual-delta_viz, line_dash="dash", line_color="#2ecc71")
        fig.update_layout(template="plotly_dark", height=350, margin=dict(t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)

        # Histograma
        fig2 = go.Figure()
        fig2.add_trace(go.Histogram(x=res_st, name='Estática', marker_color='#2ecc71', opacity=0.7))
        fig2.add_trace(go.Histogram(x=res_dyn, name='Dinámica', marker_color='#e74c3c', opacity=0.7))
        fig2.update_layout(template="plotly_dark", height=300, margin=dict(t=10,b=10), barmode='overlay')
        st.plotly_chart(fig2, use_container_width=True)


# ==========================================
# PESTAÑA 2: BACKTESTING
# ==========================================
with tab2:
    st.header("Validación con Datos Reales")
    c_b1, c_b2, c_b3 = st.columns(3)
    with c_b1: ticker = st.text_input("Ticker", value="BTC-USD")
    with c_b2: start_date = st.date_input("Inicio", value=pd.to_datetime("2024-01-01"))
    with c_b3: end_date = st.date_input("Fin", value=pd.to_datetime("today"))
    
    if st.button("📉 Ejecutar Backtest", type="primary"):
        with st.spinner(f"Analizando {ticker}..."):
            try:
                data = yf.download(ticker, start=start_date, end=end_date, progress=False)
                if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
                
                if len(data) < 7:
                    st.error("Datos insuficientes.")
                else:
                    precios_real = data['Close'].values.reshape(-1, 1)
                    fechas_real = data.index
                    log_rets = np.log(data['Close'] / data['Close'].shift(1))
                    vol_real = log_rets.std() * np.sqrt(365)
                    st.info(f"Volatilidad Real: **{vol_real*100:.1f}%**")
                    
                    # Ejecutar Motor
                    res_st, res_dyn, log_ops, log_st, h_up, h_low, dias_in_st, delta_viz = ejecutar_analisis_operaciones(
                        precios_real, capital_inicial, apr_base_estatica, std_estatica, 
                        pct_ancho_dinamico, gas_rebalanceo, swap_fee, vol_real, bb_window
                    )
                    
                    # Resultados KPIs
                    val_st, val_dyn = res_st[0], res_dyn[0]
                    k1, k2, k3 = st.columns(3)
                    
                    pct_in = (dias_in_st / len(precios_real)) * 100
                    k1.metric("Estática (Final)", f"${val_st:,.0f}", f"{val_st-capital_inicial:+.0f} $")
                    k1.caption(f"✅ En Rango: {dias_in_st} días ({pct_in:.1f}%)")
                    
                    k2.metric("Dinámica (Final)", f"${val_dyn:,.0f}", f"{val_dyn-capital_inicial:+.0f} $")
                    k3.metric("Diferencia", f"${val_dyn-val_st:,.0f}", delta_color="normal")
                    
                    # --- GRÁFICO ---
                    st.subheader("Visualización de Estrategias")
                    fig_back = go.Figure()
                    
                    # 1. Rango Dinámico (Banda Azul)
                    fig_back.add_trace(go.Scatter(
                        x=fechas_real, y=h_low, mode='lines', line=dict(width=0), showlegend=False, hoverinfo='skip'
                    ))
                    fig_back.add_trace(go.Scatter(
                        x=fechas_real, y=h_up, mode='lines', line=dict(width=0), 
                        fill='tonexty', fillcolor='rgba(0, 100, 255, 0.2)',
                        name='Rango Dinámico'
                    ))
                    
                    # 2. Precio Activo (AHORA EN NEGRO)
                    fig_back.add_trace(go.Scatter(
                        x=fechas_real, y=data['Close'], mode='lines', 
                        name='Precio BTC', 
                        line=dict(color='black', width=2) # <--- CAMBIO DE COLOR AQUÍ
                    ))
                    
                    # 3. Rango Estático
                    p_start = precios_real[0][0]
                    r_sup = p_start + (p_start * (vol_real * np.sqrt(bb_window/365) * std_estatica))
                    r_inf = p_start - (p_start * (vol_real * np.sqrt(bb_window/365) * std_estatica))
                    fig_back.add_hline(y=r_sup, line_dash="dash", line_color="#2ecc71", annotation_text="Estático Sup")
                    fig_back.add_hline(y=r_inf, line_dash="dash", line_color="#2ecc71", annotation_text="Estático Inf")
                    
                    # 4. Marcadores de Rebalanceo
                    if len(log_ops) > 0:
                        df_log_temp = pd.DataFrame(log_ops)
                        # Filtramos solo los eventos de ruptura para pintar las X, no el cierre final
                        df_log_events = df_log_temp[df_log_temp["Evento"].str.contains("Ruptura")]
                        
                        if not df_log_events.empty:
                            f_ev = [fechas_real[i] for i in df_log_events['Día Índice']]
                            p_ev = [data['Close'].iloc[i] for i in df_log_events['Día Índice']]
                            fig_back.add_trace(go.Scatter(x=f_ev, y=p_ev, mode='markers', marker=dict(color='red', size=8, symbol='x'), name='Rebalanceo'))

                    fig_back.update_layout(template="plotly_white", height=500, title=f"Historia {ticker}") # Cambié a plotly_white para que contraste mejor con la línea negra
                    st.plotly_chart(fig_back, use_container_width=True)
                    
                    # --- TABLA DE AUDITORÍA ---
                    st.subheader("📋 Auditoría de Operaciones")
                    
                    tipo_tabla = st.radio("Ver detalle de:", ["Estrategia Dinámica (Rebalanceos)", "Estrategia Estática (Resumen)"], horizontal=True)
                    
                    if tipo_tabla == "Estrategia Dinámica (Rebalanceos)":
                        if len(log_ops) > 0:
                            df_ops = pd.DataFrame(log_ops)
                            df_ops["Fecha"] = [fechas_real[i].strftime('%Y-%m-%d') for i in df_ops['Día Índice']]
                            
                            cols_num = ["Fees Generados", "Costes (Swap+Gas)", "Pérdida IL (Info)", "Capital Final", "Precio Ejecución"]
                            for c in cols_num: df_ops[c] = df_ops[c].astype(float)
                            
                            cols_show = ["Operación", "Fecha", "Rango Activo", "Precio Ejecución", "Evento", "Fees Generados", "Pérdida IL (Info)", "Costes (Swap+Gas)", "Capital Final"]
                            
                            st.dataframe(df_ops[cols_show].style.format({
                                "Precio Ejecución": "${:,.2f}",
                                "Fees Generados": "+${:,.2f}",
                                "Pérdida IL (Info)": "${:,.2f}",
                                "Costes (Swap+Gas)": "-${:,.2f}",
                                "Capital Final": "${:,.2f}"
                            }), use_container_width=True)
                            
                            # P&L
                            tot_fees = df_ops["Fees Generados"].sum()
                            tot_gastos = df_ops["Costes (Swap+Gas)"].sum() # IL aquí es informativo
                            neto = tot_fees - tot_gastos
                            st.markdown(f"**Resultado Neto Operativo:** Fees (${tot_fees:,.2f}) - Costes Fricción (${tot_gastos:,.2f}) = **${neto:,.2f}**")
                        else:
                            st.success("Error: No se generó registro de operaciones.")
                            
                    else:
                        st.info("Estado diario de la estrategia Estática:")
                        if len(log_st) > 0:
                            df_st = pd.DataFrame(log_st)
                            df_st["Fecha"] = [fechas_real[i].strftime('%Y-%m-%d') for i in df_st['Día Índice']]
                            st.dataframe(df_st[["Fecha", "Precio", "En Rango"]].style.format({"Precio": "${:,.2f}"}), use_container_width=True, height=300)

            except Exception as e:
                st.error(f"Error: {e}")

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
