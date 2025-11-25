import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Liquidity Pro Calc", layout="wide")
st.title("🧪 Laboratorio de Liquidez: Simulación & Backtest")
st.markdown("---")

# --- 2. SIDEBAR (COMPARTIDO) ---
with st.sidebar:
    st.header("1. Configuración de Estrategia")
    
    # Inputs que aplican a AMBOS modos
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
    
    # Info Eficiencia
    factor_concentracion = 1 / (pct_ancho_dinamico / 100)
    st.markdown("---")
    st.info(f"⚡ **Multiplicador APR:** {factor_concentracion:.1f}x ({(apr_base_estatica * factor_concentracion)*100:.1f}%)")

# --- 3. FUNCIONES DEL NÚCLEO (TU CÓDIGO VALIDADO) ---

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
    """Calcula el valor de los activos al salir del rango (Venta progresiva)."""
    if p_exit >= p_max: # Salida por arriba (Todo Stable)
        precio_promedio_venta = np.sqrt(p_entry * p_max)
        stables_originales = cap_entrada * 0.5
        valor_venta_tokens = (cap_entrada * 0.5 / p_entry) * precio_promedio_venta
        return stables_originales + valor_venta_tokens
    elif p_exit <= p_min: # Salida por abajo (Todo Token)
        precio_promedio_compra = np.sqrt(p_entry * p_min)
        tokens_originales = (cap_entrada * 0.5) / p_entry
        tokens_comprados = (cap_entrada * 0.5) / precio_promedio_compra
        return (tokens_originales + tokens_comprados) * p_exit
    return cap_entrada 

def ejecutar_analisis_operaciones(precios_matrix, cap_inicial, apr_base, std_st, pct_dyn, gas, fee_swap, vol_anual, window_days):
    filas, columnas = precios_matrix.shape
    factor_concentracion = 1 / (pct_dyn / 100)
    fee_diario_st = apr_base / 365
    fee_diario_dyn = (apr_base * factor_concentracion) / 365 
    
    res_st_final = []
    res_dyn_final = []
    stats_rebalanceos = []
    log_operaciones = [] 
    
    # Barra de progreso solo si hay muchas simulaciones (Montecarlo)
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
        
        # Cálculo final Estática
        p_final = serie_precios[-1]
        val_estatico = calcular_valor_v3_exacto(cap_inicial, p_inicial, p_final, p_min_st, p_max_st)
        in_range_mask = (serie_precios >= p_min_st) & (serie_precios <= p_max_st)
        fees_st = np.sum(in_range_mask) * (cap_inicial * fee_diario_st)
        res_st_final.append(val_estatico + fees_st)
        
        # --- DINÁMICA (Gestión por Operaciones) ---
        cap_dyn = cap_inicial
        op_start_day = 0
        
        # Rango inicial
        delta_dyn = delta_st * (pct_dyn / 100)
        p_min_dyn = p_inicial - delta_dyn
        p_max_dyn = p_inicial + delta_dyn
        
        fees_acumulados_operacion = 0
        num_rebalanceos = 0
        
        ratio_width = delta_dyn / p_inicial
        
        for dia in range(1, filas):
            p_hoy = serie_precios[dia]
            
            # 1. Acumular Fees si está en rango
            if p_min_dyn <= p_hoy <= p_max_dyn:
                fees_acumulados_operacion += cap_dyn * fee_diario_dyn
            
            # 2. Chequeo de Salida (Fin de Operación)
            else:
                num_rebalanceos += 1
                
                # A. Determinar Evento y Precio de Ruptura (Límite del Rango)
                if p_hoy > p_max_dyn:
                    evento = "Ruptura Rango Superior ⬆️"
                    precio_ruptura = p_max_dyn 
                else:
                    evento = "Ruptura Rango Inferior ⬇️"
                    precio_ruptura = p_min_dyn 
                
                # B. Calcular Valor de Salida (Matemático)
                p_ref_anterior = (p_max_dyn + p_min_dyn) / 2
                val_salida_pool = calcular_valor_v3_exacto(cap_dyn, p_ref_anterior, p_hoy, p_min_dyn, p_max_dyn)
                
                # C. Calcular IL (Informativo)
                val_hold = (cap_dyn * 0.5) + ((cap_dyn * 0.5 / p_ref_anterior) * p_hoy)
                il_realizado = max(0, val_hold - val_salida_pool)
                
                # D. Costes
                coste_swap = val_salida_pool * 0.50 * fee_swap
                costes_totales = coste_swap + gas
                
                # E. Nuevo Capital
                cap_nuevo = val_salida_pool + fees_acumulados_operacion - costes_totales
                
                # F. Log (Solo Simulación 0)
                if sim_idx == 0:
                    log_operaciones.append({
                        "Operación": num_rebalanceos,
                        "Día Índice": dia, # Usaremos esto para el backtest
                        "Rango Teórico": f"{p_min_dyn:.0f} - {p_max_dyn:.0f}",
                        "Fees Generados": fees_acumulados_operacion,
                        "Valor Salida Pool": val_salida_pool,
                        "Pérdida IL (Info)": il_realizado,
                        "Costes (Swap+Gas)": costes_totales,
                        "Capital Final": cap_nuevo,
                        "Evento": evento,
                        "Precio Ruptura": precio_ruptura 
                    })
                
                # G. Reset para Siguiente Operación
                cap_dyn = cap_nuevo
                op_start_day = dia
                fees_acumulados_operacion = 0
                
                # Nuevo Rango centrado en p_hoy
                nuevo_delta = p_hoy * ratio_width
                p_min_dyn = p_hoy - nuevo_delta
                p_max_dyn = p_hoy + nuevo_delta

        res_dyn_final.append(cap_dyn + fees_acumulados_operacion)
        stats_rebalanceos.append(num_rebalanceos)

    if show_progress:
        progress_bar.empty()
    return (np.array(res_st_final), np.array(res_dyn_final), 
            np.mean(stats_rebalanceos), delta_st, log_operaciones)

# --- 4. INTERFAZ DE PESTAÑAS ---

tab1, tab2 = st.tabs(["🎲 Simulación Montecarlo", "📉 Backtesting Histórico"])

# ==========================================
# PESTAÑA 1: MONTECARLO (CÓDIGO ORIGINAL)
# ==========================================
with tab1:
    col_inp1, col_inp2, col_inp3 = st.columns(3)
    with col_inp1:
        precio_actual = st.number_input("Precio Inicial ($)", value=65000.0)
    with col_inp2:
        volatilidad_anual = st.slider("Volatilidad Anual (%)", 10, 200, 60) / 100
    with col_inp3:
        tendencia_anual = st.slider("Tendencia Anual (%)", -50, 150, 0) / 100
        
    n_simulaciones = st.slider("Nº Simulaciones", 50, 1000, 200, step=50)
    dias_analisis = st.slider("Días a simular", 7, 365, 30, step=1)
    
    if st.button("🚀 Ejecutar Montecarlo", type="primary"):
        # EJECUCIÓN (Usando el código que te gusta)
        matriz = generar_montecarlo_precios(precio_actual, volatilidad_anual, tendencia_anual, dias_analisis, n_simulaciones)
        
        res_st, res_dyn, avg_reb, delta_viz, log_ops = ejecutar_analisis_operaciones(
            matriz, capital_inicial, apr_base_estatica, std_estatica, pct_ancho_dinamico, 
            gas_rebalanceo, swap_fee, volatilidad_anual, bb_window
        )
        
        # VISUALIZACIÓN ORIGINAL
        st.subheader("🏁 Comparativa de Rendimiento (Promedio)")
        m_st, m_dyn = np.mean(res_st), np.mean(res_dyn)
        c1, c2, c3 = st.columns(3)
        c1.metric("Estática", f"${m_st:,.0f}", f"{m_st-capital_inicial:+.0f} $ Netos")
        c2.metric("Dinámica", f"${m_dyn:,.0f}", f"{m_dyn-capital_inicial:+.0f} $ Netos")
        winner = "Dinámica" if m_dyn > m_st else "Estática"
        c3.metric("Ganador", winner, f"Diferencia: ${m_dyn-m_st:,.0f}")

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.caption("Proyección de Mercado")
            p10, p50, p90 = np.percentile(matriz, 10, axis=1), np.percentile(matriz, 50, axis=1), np.percentile(matriz, 90, axis=1)
            x = np.arange(len(p50))
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=np.concatenate([x, x[::-1]]), y=np.concatenate([p90, p10[::-1]]), fill='toself', fillcolor='rgba(0,150,255,0.15)', line=dict(color='rgba(255,255,255,0)'), name='80% Prob.'))
            fig.add_trace(go.Scatter(x=x, y=p50, mode='lines', line=dict(color='white'), name='Mediana'))
            fig.add_hline(y=precio_actual+delta_viz, line_dash="dash", line_color="#2ecc71")
            fig.add_hline(y=precio_actual-delta_viz, line_dash="dash", line_color="#2ecc71")
            fig.update_layout(template="plotly_dark", height=300, margin=dict(t=10,b=10))
            st.plotly_chart(fig, use_container_width=True)

        with col_g2:
            st.caption("Distribución de Retornos")
            fig2 = go.Figure()
            fig2.add_trace(go.Histogram(x=res_st, name='Estática', marker_color='#2ecc71', opacity=0.7))
            fig2.add_trace(go.Histogram(x=res_dyn, name='Dinámica', marker_color='#e74c3c', opacity=0.7))
            fig2.update_layout(template="plotly_dark", height=300, margin=dict(t=10,b=10), barmode='overlay')
            st.plotly_chart(fig2, use_container_width=True)

        # TABLA OPERACIONES (TU FORMATO EXACTO)
        st.subheader("📋 Registro de Operaciones (Simulación #1)")
        if len(log_ops) > 0:
            df_ops = pd.DataFrame(log_ops)
            st.dataframe(df_ops.drop(columns=["Día Índice"]).style.format({ # Ocultamos índice interno
                "Fees Generados": "+${:,.2f}",
                "Valor Salida Pool": "${:,.2f}",
                "Pérdida IL (Info)": "${:,.2f}",
                "Costes (Swap+Gas)": "-${:,.2f}",
                "Capital Final": "${:,.2f}",
                "Precio Ruptura": "${:,.2f}"
            }), use_container_width=True)
            
            total_fees = df_ops["Fees Generados"].sum()
            total_friccion = df_ops["Costes (Swap+Gas)"].sum()
            total_il = df_ops["Pérdida IL (Info)"].sum()
            total_gastos = total_friccion + total_il
            neto_operativo = total_fees - total_gastos
            roi_gastos = (total_fees / total_gastos) * 100 if total_gastos > 0 else 0
            
            if neto_operativo > 0:
                estado = "✅ **NEGOCIO RENTABLE**"
                mensaje = f"Tus ingresos (Fees) cubren costes + IL. Retorno del gasto: {roi_gastos:.0f}%."
            else:
                estado = "❌ **NEGOCIO EN PÉRDIDAS**"
                mensaje = f"Estás perdiendo dinero operativamente. Los fees no cubren el rebalanceo."

            st.markdown("### 📊 Cuenta de Resultados Operativa")
            c_r1, c_r2, c_r3 = st.columns(3)
            c_r1.metric("Ingresos (Fees)", f"${total_fees:,.2f}")
            c_r2.metric("Gastos (IL+Costes)", f"-${total_gastos:,.2f}")
            c_r3.metric("Beneficio Neto", f"${neto_operativo:,.2f}", delta="Ganancia" if neto_operativo > 0 else "Pérdida")
            st.markdown(f"**Diagnóstico:** {estado} - {mensaje}")
        else:
            st.success("Sin rebalanceos.")


# ==========================================
# PESTAÑA 2: BACKTESTING (CORREGIDO)
# ==========================================
with tab2:
    st.header("Validación con Datos Reales")
    st.info("Descarga datos de Yahoo Finance y simula tu estrategia en el pasado.")
    
    col_b1, col_b2, col_b3 = st.columns(3)
    with col_b1:
        ticker = st.text_input("Ticker", value="BTC-USD", help="Ej: BTC-USD, ETH-USD, SOL-USD")
    with col_b2:
        start_date = st.date_input("Fecha Inicio", value=pd.to_datetime("2024-01-01"))
    with col_b3:
        end_date = st.date_input("Fecha Fin", value=pd.to_datetime("today"))
    
    if st.button("📉 Ejecutar Backtest con Datos Reales", type="primary"):
        with st.spinner(f"Descargando datos históricos de {ticker}..."):
            try:
                # 1. Descarga
                data = yf.download(ticker, start=start_date, end=end_date, progress=False)
                
                if len(data) < 7:
                    st.error("Error: Rango de fechas demasiado corto o sin datos.")
                else:
                    # Aplanar datos para evitar problemas de multi-index en versiones nuevas de yfinance
                    if isinstance(data.columns, pd.MultiIndex):
                        data.columns = data.columns.get_level_values(0)
                        
                    precios_real = data['Close'].values.reshape(-1, 1)
                    fechas_real = data.index
                    
                    # Cálculo Volatilidad Real
                    log_rets = np.log(data['Close'] / data['Close'].shift(1))
                    vol_real_periodo = log_rets.std() * np.sqrt(365)
                    st.info(f"📊 Volatilidad Real detectada en el periodo: **{vol_real_periodo*100:.1f}%** (Usada para definir rangos)")
                    
                    # 2. Ejecutar Motor
                    res_st, res_dyn, avg_reb, delta_viz, log_ops = ejecutar_analisis_operaciones(
                        precios_real, capital_inicial, apr_base_estatica, std_estatica, 
                        pct_ancho_dinamico, gas_rebalanceo, swap_fee, vol_real_periodo, bb_window
                    )
                    
                    # 3. Resultados
                    val_st = res_st[0]
                    val_dyn = res_dyn[0]
                    
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Resultado Estático", f"${val_st:,.0f}", f"{val_st-capital_inicial:+.0f} $")
                    k2.metric("Resultado Dinámico", f"${val_dyn:,.0f}", f"{val_dyn-capital_inicial:+.0f} $")
                    k3.metric("Diferencia", f"${val_dyn-val_st:,.0f}", delta_color="normal")
                    
                    # 4. Gráfico
                    st.subheader("Evolución de Precio y Eventos")
                    fig_back = go.Figure()
                    fig_back.add_trace(go.Scatter(x=fechas_real, y=data['Close'], mode='lines', name='Precio', line=dict(color='white', width=1)))
                    
                    if len(log_ops) > 0:
                        df_log = pd.DataFrame(log_ops)
                        # Mapear índices a fechas reales
                        fechas_eventos = [fechas_real[i] for i in df_log['Día Índice']]
                        precios_eventos = [data['Close'].iloc[i] for i in df_log['Día Índice']]
                        
                        fig_back.add_trace(go.Scatter(
                            x=fechas_eventos, y=precios_eventos, 
                            mode='markers', marker=dict(color='yellow', size=8, symbol='x'),
                            name='Rebalanceo'
                        ))
                    
                    # Rango Estático (Fijo al inicio)
                    p_start = precios_real[0][0]
                    rango_sup = p_start + (p_start * (vol_real_periodo * np.sqrt(bb_window/365) * std_estatica))
                    rango_inf = p_start - (p_start * (vol_real_periodo * np.sqrt(bb_window/365) * std_estatica))
                    fig_back.add_hline(y=rango_sup, line_dash="dash", line_color="#2ecc71")
                    fig_back.add_hline(y=rango_inf, line_dash="dash", line_color="#2ecc71")
                    fig_back.update_layout(template="plotly_dark", height=500, title=f"Historia {ticker}")
                    st.plotly_chart(fig_back, use_container_width=True)
                    
                    # 5. Auditoría
                    st.subheader("📋 Auditoría de Operaciones Reales")
                    if len(log_ops) > 0:
                        df_ops = pd.DataFrame(log_ops)
                        df_ops["Fecha"] = [fechas_real[i].strftime('%Y-%m-%d') for i in df_ops['Día Índice']]
                        
                        # --- CORRECCIÓN DE TIPOS (ESTO SOLUCIONA TU ERROR) ---
                        cols_numericas = ["Fees Generados", "Costes (Swap+Gas)", "Pérdida IL (Info)", "Capital Final"]
                        for col in cols_numericas:
                            df_ops[col] = df_ops[col].astype(float)
                        # -----------------------------------------------------

                        st.dataframe(df_ops[["Operación", "Fecha", "Evento", "Fees Generados", "Costes (Swap+Gas)", "Pérdida IL (Info)", "Capital Final"]].style.format({
                            "Fees Generados": "+${:,.2f}",
                            "Costes (Swap+Gas)": "-${:,.2f}",
                            "Pérdida IL (Info)": "${:,.2f}",
                            "Capital Final": "${:,.2f}"
                        }), use_container_width=True)
                        
                        total_fees = df_ops["Fees Generados"].sum()
                        total_gastos = df_ops["Costes (Swap+Gas)"].sum() + df_ops["Pérdida IL (Info)"].sum()
                        neto = total_fees - total_gastos
                        
                        st.markdown("### 📊 Resultado Operativo Real")
                        c_r1, c_r2, c_r3 = st.columns(3)
                        c_r1.metric("Ingresos Totales", f"${total_fees:,.2f}")
                        c_r2.metric("Gastos (Fricción + IL)", f"-${total_gastos:,.2f}")
                        c_r3.metric("Neto Real", f"${neto:,.2f}", delta="Ganancia" if neto > 0 else "Pérdida")

            except Exception as e:
                st.error(f"Error técnico: {e}")
