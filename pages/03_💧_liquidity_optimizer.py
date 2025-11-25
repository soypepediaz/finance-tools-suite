import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Liquidity Pro Calc", layout="wide")

st.title("⚖️ Optimizador Realista: Costes y Ventanas Temporales")
st.markdown("---")

# --- 2. SIDEBAR: PARÁMETROS DE ENTRADA ---
with st.sidebar:
    st.header("1. Mercado y Simulación")
    # Inputs básicos de mercado
    precio_actual = st.number_input("Precio Inicial ($)", value=65000.0)
    volatilidad_anual = st.slider("Volatilidad Anual (%)", 10, 200, 60, help="Medida de cuánto oscila el precio anualmente.") / 100
    tendencia_anual = st.slider("Tendencia Anual (%)", -50, 150, 0, help="0% = Mercado Lateral. Positivo = Alcista.") / 100
    
    # Inputs de la simulación Montecarlo
    n_simulaciones = st.slider("Nº Simulaciones", 50, 1000, 200, step=50)
    dias_analisis = st.slider("Días a simular (Proyección)", 7, 365, 30, step=1)
    
    st.markdown("---")
    
    st.header("2. Estrategia ESTÁTICA")
    # CONTROL DE VENTANA
    col_bb1, col_bb2 = st.columns(2)
    with col_bb1:
        bb_window = st.number_input("Ventana (Días)", value=7, min_value=1, max_value=90, help="Días usados para calcular la volatilidad de la banda. 7 días = Scalping/Semanal. 30 días = Mensual.")
    with col_bb2:
        std_estatica = st.number_input("Ancho (SD)", value=2.0, step=0.1, min_value=0.5, max_value=5.0)
        
    apr_base_estatica = st.number_input("APR Base Estática (%)", value=15.0) / 100
    
    st.markdown("---")
    
    st.header("3. Estrategia DINÁMICA")
    # Definición relativa del rango dinámico
    pct_ancho_dinamico = st.slider("% del Ancho Estático", 5, 100, 25, step=5, help="Cuanto más bajo, más concentrada y agresiva es la posición.")
    
    st.markdown("**Costes de Fricción (Realidad)**")
    gas_rebalanceo = st.number_input("Gas por Rebalanceo ($)", value=5.0)
    swap_fee = st.number_input("Swap Fee del Pool (%)", value=0.30, step=0.01, format="%.2f", help="Comisión pagada al pool al intercambiar tokens para recentrar el rango.") / 100
    
    capital_inicial = st.number_input("Capital ($)", value=10000.0)
    
    # Cálculos informativos
    factor_concentracion = 1 / (pct_ancho_dinamico / 100)
    apr_dinamico_teorico = apr_base_estatica * factor_concentracion
    st.info(f"""
    ⚡ **Análisis de Potencia:**
    * Concentración: **{factor_concentracion:.1f}x**
    * APR Dinámico: **{apr_dinamico_teorico*100:.1f}%**
    """)

# --- 3. MOTOR MATEMÁTICO (MONTECARLO) ---

def generar_montecarlo_precios(precio, vol, tendencia, dias, n_sims):
    """Genera n escenarios de precios futuros usando Movimiento Browniano Geométrico."""
    dt = 1/365
    shocks = np.random.normal(0, 1, (dias, n_sims))
    drift = (tendencia - 0.5 * vol**2) * dt
    diffusion = vol * np.sqrt(dt) * shocks
    log_retornos = np.cumsum(drift + diffusion, axis=0)
    precios = precio * np.exp(log_retornos)
    fila_cero = np.full((1, n_sims), precio)
    precios = np.vstack([fila_cero, precios])
    return precios

def ejecutar_analisis_completo(precios_matrix, cap_inicial, apr_base, std_st, pct_dyn, gas, fee_swap, vol_anual, window_days):
    filas, columnas = precios_matrix.shape
    
    factor_concentracion = 1 / (pct_dyn / 100)
    fee_diario_st = apr_base / 365
    fee_diario_dyn = (apr_base * factor_concentracion) / 365 
    
    res_st_final = []
    res_dyn_final = []
    stats_dias_out_st = []
    stats_rebalanceos_dyn = []
    
    # LOG PARA AUDITORÍA (Solo simulación #0)
    log_auditoria = []
    
    progress_bar = st.progress(0)

    for sim_idx in range(columnas):
        if sim_idx % (columnas // 10 + 1) == 0:
            progress_bar.progress(sim_idx / columnas)
            
        serie_precios = precios_matrix[:, sim_idx]
        p_inicial = serie_precios[0]
        
        # Volatilidad ajustada a la ventana
        vol_periodo = vol_anual * np.sqrt(window_days/365)
        
        delta_st = p_inicial * vol_periodo * std_st
        delta_dyn_base = delta_st * (pct_dyn / 100)
        
        # ==============================
        # ESTRATEGIA A: ESTÁTICA
        # ==============================
        p_min_st = p_inicial - delta_st
        p_max_st = p_inicial + delta_st
        
        in_range_mask = (serie_precios >= p_min_st) & (serie_precios <= p_max_st)
        dias_in = np.sum(in_range_mask)
        stats_dias_out_st.append(filas - dias_in)
        
        fees_st_acum = dias_in * (cap_inicial * fee_diario_st)
        
        p_final = serie_precios[-1]
        val_prin_st = cap_inicial
        if p_final < p_min_st:
            val_prin_st = cap_inicial * (p_final / p_min_st)
        elif p_final > p_max_st:
            val_prin_st = cap_inicial 
        
        res_st_final.append(val_prin_st + fees_st_acum)
        
        # ==============================
        # ESTRATEGIA B: DINÁMICA
        # ==============================
        cap_dyn = cap_inicial
        fees_dyn_acum = 0
        gas_total = 0
        num_rebalanceos = 0
        
        p_min_dyn = p_inicial - delta_dyn_base
        p_max_dyn = p_inicial + delta_dyn_base
        
        ratio_half_width = delta_dyn_base / p_inicial
        
        for dia in range(1, filas):
            p_hoy = serie_precios[dia]
            
            if p_min_dyn <= p_hoy <= p_max_dyn:
                fees_dyn_acum += cap_dyn * fee_diario_dyn
            else:
                num_rebalanceos += 1
                
                # Datos para Log antes de modificar el capital
                cap_antes = cap_dyn
                razon = "⬇️ Caída (IL)" if p_hoy < p_min_dyn else "⬆️ Subida (Stable)"
                
                # 1. Realizar Pérdidas
                perdida_il = 0.0
                if p_hoy < p_min_dyn:
                    nuevo_cap_il = cap_dyn * (p_hoy / p_min_dyn)
                    perdida_il = cap_dyn - nuevo_cap_il
                    cap_dyn = nuevo_cap_il
                
                # 2. Gas
                gas_total += gas
                
                # 3. Swap Fee
                coste_swap = cap_dyn * 0.50 * fee_swap
                cap_dyn -= coste_swap
                
                # Guardar Log (Solo Simulación 0)
                if sim_idx == 0:
                    log_auditoria.append({
                        "Día": dia,
                        "Precio": p_hoy,
                        "Evento": razon,
                        "Cap. Pre-Ajuste": cap_antes,
                        "Pérdida IL": perdida_il,
                        "Swap Fee": coste_swap,
                        "Gas": gas,
                        "Cap. Post-Ajuste": cap_dyn
                    })
                
                # 4. Nuevo Rango
                nuevo_delta = p_hoy * ratio_half_width
                p_min_dyn = p_hoy - nuevo_delta
                p_max_dyn = p_hoy + nuevo_delta
                
        stats_rebalanceos_dyn.append(num_rebalanceos)
        res_dyn_final.append(cap_dyn + fees_dyn_acum - gas_total)

    progress_bar.empty()
    return (np.array(res_st_final), np.array(res_dyn_final), 
            np.mean(stats_dias_out_st), np.mean(stats_rebalanceos_dyn),
            factor_concentracion, delta_st, log_auditoria)

# --- 4. EJECUCIÓN ---

matriz = generar_montecarlo_precios(precio_actual, volatilidad_anual, tendencia_anual, dias_analisis, n_simulaciones)

res_estatica, res_dinamica, avg_dias_out, avg_rebalanceos, factor, delta_viz, log_data = ejecutar_analisis_completo(
    matriz, capital_inicial, apr_base_estatica, 
    std_estatica, pct_ancho_dinamico, gas_rebalanceo, swap_fee, volatilidad_anual, bb_window
)

# --- 5. VISUALIZACIÓN ---

mean_st = np.mean(res_estatica)
mean_dyn = np.mean(res_dinamica)
win_rate = (np.sum(res_dinamica > res_estatica) / n_simulaciones) * 100

st.subheader("🏁 Comparativa de Rendimiento Esperado (Promedio)")

col1, col2, col3 = st.columns(3)
diff_st = mean_st - capital_inicial
col1.metric("Estática (Promedio)", f"${mean_st:,.0f}", f"{diff_st:+.0f} $ Netos")
col1.caption(f"📅 Fuera de rango: {avg_dias_out:.1f} días (Media)")

diff_dyn = mean_dyn - capital_inicial
col2.metric("Dinámica (Promedio)", f"${mean_dyn:,.0f}", f"{diff_dyn:+.0f} $ Netos")
col2.caption(f"🔄 Rebalanceos: {avg_rebalanceos:.1f} (Media)")

diff_total = mean_dyn - mean_st
winner = "Dinámica" if diff_total > 0 else "Estática"
col3.metric("Diferencia", f"${diff_total:,.0f}", f"Gana {winner} ({win_rate:.0f}% veces)")

# GRÁFICOS
st.subheader(f"1. Escenarios de Precio (Ventana: {bb_window} días)")
p10, p50, p90 = np.percentile(matriz, 10, axis=1), np.percentile(matriz, 50, axis=1), np.percentile(matriz, 90, axis=1)
x = np.arange(len(p50))
fig = go.Figure()
fig.add_trace(go.Scatter(x=np.concatenate([x, x[::-1]]), y=np.concatenate([p90, p10[::-1]]), fill='toself', fillcolor='rgba(0,150,255,0.15)', line=dict(color='rgba(255,255,255,0)'), name='80% Prob.'))
fig.add_trace(go.Scatter(x=x, y=p50, mode='lines', line=dict(color='white'), name='Mediana'))
fig.add_hline(y=precio_actual+delta_viz, line_dash="dash", line_color="#2ecc71", annotation_text="Límite Sup.")
fig.add_hline(y=precio_actual-delta_viz, line_dash="dash", line_color="#2ecc71", annotation_text="Límite Inf.")
fig.update_layout(template="plotly_dark", height=400, margin=dict(t=30,b=10), title="Proyección de Precio")
st.plotly_chart(fig, use_container_width=True)

st.subheader("2. Distribución de Resultados")
fig2 = go.Figure()
fig2.add_trace(go.Histogram(x=res_estatica, name='Estática', marker_color='#2ecc71', opacity=0.7))
fig2.add_trace(go.Histogram(x=res_dinamica, name='Dinámica', marker_color='#e74c3c', opacity=0.7))
fig2.add_vline(x=mean_st, line_dash="dash", line_color="#2ecc71")
fig2.add_vline(x=mean_dyn, line_dash="dash", line_color="#e74c3c")
fig2.update_layout(template="plotly_dark", height=350, margin=dict(t=30,b=10), barmode='overlay')
st.plotly_chart(fig2, use_container_width=True)

# --- AUDITORÍA DE REBALANCEOS ---
st.subheader("📋 Auditoría de Costes (Ejemplo: Simulación #1)")

st.warning(f"""
**⚠️ Contexto Importante:**
La tabla de abajo muestra el detalle paso a paso de **UNA sola simulación** (la primera de las {n_simulaciones} generadas). 
* Sirve para entender **cómo** se pierde dinero en cada rebalanceo (Swap + IL + Gas).
* No representa el resultado final promedio (para eso, mira los números grandes de arriba).
""")

with st.expander("🔍 Ver desglose de operaciones y costes (Simulación #1)", expanded=False):
    if len(log_data) > 0:
        df_log = pd.DataFrame(log_data)
        
        st.dataframe(df_log.style.format({
            "Precio": "${:,.2f}",
            "Cap. Pre-Ajuste": "${:,.2f}",
            "Pérdida IL": "${:,.2f}", 
            "Swap Fee": "${:,.2f}",
            "Gas": "${:,.2f}",
            "Cap. Post-Ajuste": "${:,.2f}"
        }), use_container_width=True)
        
        total_il = df_log["Pérdida IL"].sum()
        total_swap = df_log["Swap Fee"].sum()
        total_gas = df_log["Gas"].sum()
        total_destruccion = total_il + total_swap + total_gas
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Pérdida por IL", f"${total_il:,.2f}", help="Dinero perdido por vender el activo cuando bajó de precio.")
        c2.metric("Comisiones Swap", f"${total_swap:,.2f}", help="Dinero pagado al pool por intercambiar tokens.")
        c3.metric("Gas Total", f"${total_gas:,.2f}")
        c4.metric("Coste Total Operativo", f"${total_destruccion:,.2f}", delta="-Destrucción de Capital", delta_color="inverse")
        
    else:
        st.success("🎉 En esta simulación específica (la #1), el precio se mantuvo dentro del rango dinámico todo el tiempo. ¡Cero costes de rebalanceo! (Prueba a regenerar para ver casos peores).")
