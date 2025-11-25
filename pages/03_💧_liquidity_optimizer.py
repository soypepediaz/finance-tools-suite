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
    # CONTROL DE VENTANA (Nuevo)
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
    
    # Cálculos informativos en tiempo real en el sidebar
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
    # Generamos una matriz de shocks aleatorios (ruido normal)
    shocks = np.random.normal(0, 1, (dias, n_sims))
    # Ecuación diferencial estocástica (GBM)
    drift = (tendencia - 0.5 * vol**2) * dt
    diffusion = vol * np.sqrt(dt) * shocks
    log_retornos = np.cumsum(drift + diffusion, axis=0)
    precios = precio * np.exp(log_retornos)
    # Añadimos el precio inicial en la fila 0
    fila_cero = np.full((1, n_sims), precio)
    precios = np.vstack([fila_cero, precios])
    return precios

def ejecutar_analisis_completo(precios_matrix, cap_inicial, apr_base, std_st, pct_dyn, gas, fee_swap, vol_anual, window_days):
    """Simula el comportamiento de las estrategias día a día sobre la matriz de precios."""
    filas, columnas = precios_matrix.shape
    
    # Cálculo del APR diario base y boosteado
    factor_concentracion = 1 / (pct_dyn / 100)
    fee_diario_st = apr_base / 365
    fee_diario_dyn = (apr_base * factor_concentracion) / 365 
    
    # Listas para almacenar resultados de cada simulación
    res_st_final = []
    res_dyn_final = []
    stats_dias_out_st = []
    stats_rebalanceos_dyn = []
    
    # Barra de progreso
    progress_bar = st.progress(0)

    # Iteramos por cada simulación (columna de la matriz)
    for sim_idx in range(columnas):
        # Actualizar barra de progreso
        if sim_idx % (columnas // 10 + 1) == 0:
            progress_bar.progress(sim_idx / columnas)
            
        serie_precios = precios_matrix[:, sim_idx]
        p_inicial = serie_precios[0]
        
        # --- CÁLCULO DE RANGOS (CORREGIDO: Usa window_days) ---
        # La volatilidad escala con la raíz cuadrada del tiempo
        # Vol_Periodo = Vol_Anual * sqrt(Días_Ventana / 365)
        vol_periodo = vol_anual * np.sqrt(window_days/365)
        
        delta_st = p_inicial * vol_periodo * std_st
        delta_dyn_base = delta_st * (pct_dyn / 100)
        
        # ==============================
        # ESTRATEGIA A: ESTÁTICA
        # ==============================
        p_min_st = p_inicial - delta_st
        p_max_st = p_inicial + delta_st
        
        # Vectorización: ¿Qué días estuvo en rango?
        in_range_mask = (serie_precios >= p_min_st) & (serie_precios <= p_max_st)
        dias_in = np.sum(in_range_mask)
        dias_out = filas - dias_in
        stats_dias_out_st.append(dias_out)
        
        # Fees ganados
        fees_st_acum = dias_in * (cap_inicial * fee_diario_st)
        
        # Valor final del principal (Impermanent Loss al cierre)
        p_final = serie_precios[-1]
        val_prin_st = cap_inicial
        
        # Simplificación de valoración final
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
        
        # Rango inicial dinámico
        p_min_dyn = p_inicial - delta_dyn_base
        p_max_dyn = p_inicial + delta_dyn_base
        
        # Ratio para mantener la proporción del ancho relativa al precio
        ratio_half_width = delta_dyn_base / p_inicial
        
        # Bucle día a día (necesario porque hay decisiones dependientes del estado anterior)
        for dia in range(1, filas):
            p_hoy = serie_precios[dia]
            
            if p_min_dyn <= p_hoy <= p_max_dyn:
                # En Rango: Gana fees (con APR alto)
                fees_dyn_acum += cap_dyn * fee_diario_dyn
            else:
                # Fuera de Rango: REBALANCEO
                num_rebalanceos += 1
                
                # 1. Realizar pérdidas (IL se vuelve permanente)
                if p_hoy < p_min_dyn:
                    cap_dyn = cap_dyn * (p_hoy / p_min_dyn)
                
                # 2. Pagar Gas
                gas_total += gas
                
                # 3. Pagar Swap Fee (Nuevo: Penalización por recentrar)
                # Asumimos que se swapea el 50% del valor total
                coste_swap = cap_dyn * 0.50 * fee_swap
                cap_dyn -= coste_swap
                
                # 4. Calcular nuevos rangos centrados
                nuevo_delta = p_hoy * ratio_half_width
                p_min_dyn = p_hoy - nuevo_delta
                p_max_dyn = p_hoy + nuevo_delta
                
        stats_rebalanceos_dyn.append(num_rebalanceos)
        res_dyn_final.append(cap_dyn + fees_dyn_acum - gas_total)

    progress_bar.empty()
    
    # Devolvemos todos los datos necesarios para las métricas y gráficas
    return (np.array(res_st_final), np.array(res_dyn_final), 
            np.mean(stats_dias_out_st), np.mean(stats_rebalanceos_dyn),
            factor_concentracion, delta_st)

# --- 4. EJECUCIÓN DEL CÁLCULO ---

# Generamos escenarios
matriz = generar_montecarlo_precios(precio_actual, volatilidad_anual, tendencia_anual, dias_analisis, n_simulaciones)

# Ejecutamos análisis
res_estatica, res_dinamica, avg_dias_out, avg_rebalanceos, factor, delta_viz = ejecutar_analisis_completo(
    matriz, capital_inicial, apr_base_estatica, 
    std_estatica, pct_ancho_dinamico, gas_rebalanceo, swap_fee, volatilidad_anual, bb_window
)

# --- 5. VISUALIZACIÓN Y DASHBOARD ---

# Cálculo de KPIs Promedio
mean_st = np.mean(res_estatica)
mean_dyn = np.mean(res_dinamica)
win_rate = (np.sum(res_dinamica > res_estatica) / n_simulaciones) * 100

st.subheader("🏁 Comparativa de Rendimiento Esperado")

col1, col2, col3 = st.columns(3)

# KPI Estática
diff_st = mean_st - capital_inicial
col1.metric("Estática (Promedio)", f"${mean_st:,.0f}", f"{diff_st:+.0f} $ Netos")
col1.caption(f"📅 Pasa {avg_dias_out:.1f} días fuera de rango ({avg_dias_out/dias_analisis*100:.0f}%)")

# KPI Dinámica
diff_dyn = mean_dyn - capital_inicial
col2.metric("Dinámica (Promedio)", f"${mean_dyn:,.0f}", f"{diff_dyn:+.0f} $ Netos")
col2.caption(f"🔄 Realiza {avg_rebalanceos:.1f} rebalanceos (Swap + Gas)")

# KPI Ganador
diff_total = mean_dyn - mean_st
winner = "Dinámica" if diff_total > 0 else "Estática"
color_delta = "normal" if diff_total > 0 else "off"
col3.metric("Diferencia", f"${diff_total:,.0f}", f"Gana {winner} ({win_rate:.0f}% veces)")

# --- GRÁFICO 1: CONO DE VOLATILIDAD ---
st.subheader(f"1. Escenarios de Precio (Ventana: {bb_window} días)")

# Percentiles para el área sombreada
p10 = np.percentile(matriz, 10, axis=1)
p50 = np.percentile(matriz, 50, axis=1)
p90 = np.percentile(matriz, 90, axis=1)
x_axis = np.arange(len(p50))

fig_cone = go.Figure()

# Cono (Área 80% Probabilidad)
fig_cone.add_trace(go.Scatter(
    x=np.concatenate([x_axis, x_axis[::-1]]),
    y=np.concatenate([p90, p10[::-1]]),
    fill='toself', fillcolor='rgba(0, 150, 255, 0.15)',
    line=dict(color='rgba(255,255,255,0)'),
    name='80% Probabilidad'
))
# Mediana
fig_cone.add_trace(go.Scatter(x=x_axis, y=p50, mode='lines', line=dict(color='white', width=2), name='Precio Mediano'))

# Rangos Estáticos (Visualización)
# Nota: Mostramos el rango estático calculado con el precio inicial
fig_cone.add_hline(y=precio_actual + delta_viz, line_dash="dash", line_color="#2ecc71", annotation_text="Límite Sup. Estático")
fig_cone.add_hline(y=precio_actual - delta_viz, line_dash="dash", line_color="#2ecc71", annotation_text="Límite Inf. Estático")

fig_cone.update_layout(
    template="plotly_dark", 
    height=450, 
    margin=dict(t=30, b=10), 
    title=f"Proyección de Precio vs Tu Rango Estático",
    xaxis_title="Días Futuros",
    yaxis_title="Precio ($)"
)
st.plotly_chart(fig_cone, use_container_width=True)

# --- GRÁFICO 2: HISTOGRAMA DE RESULTADOS ---
st.subheader("2. Distribución de Resultados (Riesgo)")

fig_hist = go.Figure()
# Histograma Estática (Verde)
fig_hist.add_trace(go.Histogram(x=res_estatica, name='Estática', opacity=0.7, marker_color='#2ecc71', nbinsx=50))
# Histograma Dinámica (Rojo)
fig_hist.add_trace(go.Histogram(x=res_dinamica, name='Dinámica', opacity=0.7, marker_color='#e74c3c', nbinsx=50))

# Líneas de media vertical
fig_hist.add_vline(x=mean_st, line_dash="dash", line_color="#2ecc71", annotation_text="Media Est.")
fig_hist.add_vline(x=mean_dyn, line_dash="dash", line_color="#e74c3c", annotation_text="Media Dyn.")

fig_hist.update_layout(
    template="plotly_dark", 
    height=400, 
    margin=dict(t=30, b=10), 
    barmode='overlay', 
    title="¿Con cuánto dinero acabaré?",
    xaxis_title="Capital Final ($)",
    yaxis_title="Frecuencia de Escenarios"
)
st.plotly_chart(fig_hist, use_container_width=True)

# --- TEXTOS EXPLICATIVOS ---
with st.expander("ℹ️ ¿Cómo interpretar estos datos?"):
    st.markdown("""
    * **Coste de Swap:** Es el asesino silencioso de la estrategia dinámica. Cada vez que se recentra el rango, se paga una comisión sobre el volumen movido y se realiza la pérdida impermanente.
    * **Ventana de Días:** Si configuras la ventana en 7 días, el modelo calculará un rango basado en la volatilidad semanal. Si pones 30, usará la volatilidad mensual (rangos más amplios).
    * **Gráfico de Cono:** Si la zona azul se sale mucho de las líneas verdes discontinuas, significa que tu rango estático es demasiado estrecho para la volatilidad actual del mercado.
    """)
