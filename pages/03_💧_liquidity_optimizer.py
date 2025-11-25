import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Liquidity Monte Carlo", layout="wide")

st.title("🎲 Optimizador de Liquidez (Montecarlo)")
st.markdown("---")

# --- SIDEBAR: PARÁMETROS ---
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # 1. Datos del Activo
    st.subheader("Simulación de Mercado")
    precio_actual = st.number_input("Precio Inicial ($)", value=65000.0)
    volatilidad_anual = st.slider("Volatilidad Anual (%)", 10, 200, 80) / 100
    tendencia_anual = st.slider("Tendencia Anual (%)", -50, 150, 0) / 100
    
    # 2. Parámetros de la Estrategia
    st.subheader("Estrategia")
    n_simulaciones = st.slider("Nº Simulaciones (Montecarlo)", 50, 1000, 200, step=50)
    dias_analisis = st.slider("Días a simular", 7, 365, 90, step=1)
    apr_estimado = st.number_input("APR Pool Estimado (%)", value=50.0) / 100
    gas_rebalanceo = st.number_input("Coste Gas por Rebalanceo ($)", value=5.0)
    capital_inicial = st.number_input("Capital a Invertir ($)", value=10000.0)

    # 3. Bollinger (Rangos)
    st.subheader("Definición de Rangos")
    bb_window = st.selectbox("Media Móvil (Días)", [7, 14, 30, 60], index=2)
    bb_std = st.slider("Desviaciones (SD)", 0.5, 4.0, 2.0, 0.1)

# --- NÚCLEO MATEMÁTICO (OPTIMIZADO CON NUMPY) ---

def generar_montecarlo_precios(precio, vol, tendencia, dias, n_sims):
    """
    Genera una matriz de precios (dias x simulaciones) usando NumPy vectorizado.
    Es muchísimo más rápido que hacer un bucle for 1000 veces.
    """
    dt = 1/365
    mu = tendencia
    sigma = vol
    
    # Generamos todos los shocks aleatorios de golpe
    # Shape: (dias, n_sims)
    shocks = np.random.normal(0, 1, (dias, n_sims))
    
    # Cálculo vectorial del movimiento browniano
    drift = (mu - 0.5 * sigma**2) * dt
    diffusion = sigma * np.sqrt(dt) * shocks
    
    # Retornos logarítmicos acumulados
    log_retornos = np.cumsum(drift + diffusion, axis=0)
    
    # Precios
    precios = precio * np.exp(log_retornos)
    
    # Insertamos la fila inicial (Día 0) con el precio original
    fila_cero = np.full((1, n_sims), precio)
    precios = np.vstack([fila_cero, precios])
    
    return precios

def ejecutar_analisis_montecarlo(precios_matrix, cap_inicial, apr, gas, window, std_dev):
    """
    Analiza las estrategias sobre la matriz de precios completa.
    """
    filas, columnas = precios_matrix.shape # (dias, n_sims)
    fee_diario = apr / 365
    
    resultados_estatica = []
    resultados_dinamica = []
    
    # Barra de progreso porque esto puede tardar un poco si N es grande
    progress_bar = st.progress(0)
    
    # Para calcular bandas de Bollinger necesitamos un "calentamiento"
    # Como no tenemos historia previa en la simulación, usaremos una aproximación
    # expandiendo la ventana progresivamente o asumiendo volatilidad inicial.
    # Para simplificar en Montecarlo, calcularemos las bandas sobre la marcha.

    for sim_idx in range(columnas):
        # Actualizar barra cada 10%
        if sim_idx % (columnas // 10) == 0:
            progress_bar.progress(sim_idx / columnas)
            
        serie_precios = precios_matrix[:, sim_idx]
        
        # --- ESTRATEGIA ESTÁTICA ---
        # Definimos rango el día 0 basándonos en precio inicial y volatilidad teórica
        # (Es una simplificación válida para día 0)
        # Rango basado en la volatilidad input del usuario para el día 0
        rango_pct_inicial = std_dev * (volatilidad_anual / np.sqrt(365)) * np.sqrt(window)
        # Ojo: Bollinger real usa la std de los ultimos X días. 
        # Aquí simularemos un rango fijo del +/- X%
        p_base = serie_precios[0]
        # Aproximación de banda inicial: 
        # Si la vol es 80%, en 30 días la desviación esperada es aprox 80% * sqrt(30/365)
        std_aprox = p_base * (volatilidad_anual * np.sqrt(window/365))
        
        p_min_st = p_base - (std_dev * std_aprox)
        p_max_st = p_base + (std_dev * std_aprox)
        
        # Vectorizamos el chequeo de "In Range" para la estática
        in_range_st_mask = (serie_precios >= p_min_st) & (serie_precios <= p_max_st)
        dias_in_st = np.sum(in_range_st_mask)
        fees_st = dias_in_st * (cap_inicial * fee_diario) # Simplificación: Fees sobre capital inicial
        
        # Valor final del principal (IL)
        p_final = serie_precios[-1]
        val_prin_st = cap_inicial
        if p_final < p_min_st:
            val_prin_st = cap_inicial * (p_final / p_min_st)
        elif p_final > p_max_st:
            val_prin_st = cap_inicial # Capped en stable
            
        resultados_estatica.append(val_prin_st + fees_st)
        
        # --- ESTRATEGIA DINÁMICA (Bucle simplificado) ---
        # Aquí sí necesitamos iterar porque el rebalanceo depende del estado anterior
        cap_dyn = cap_inicial
        fees_dyn = 0
        gas_total = 0
        
        # Rango actual
        p_min_dyn = p_min_st
        p_max_dyn = p_max_st
        
        for dia in range(1, filas):
            p_hoy = serie_precios[dia]
            
            if p_min_dyn <= p_hoy <= p_max_dyn:
                fees_dyn += cap_dyn * fee_diario
            else:
                # Rebalanceo
                gas_total += gas
                
                # IL Realizado
                if p_hoy < p_min_dyn:
                    cap_dyn = cap_dyn * (p_hoy / p_min_dyn)
                # Si sale por arriba (p_hoy > p_max_dyn), cap_dyn se mantiene (vendimos todo a stable)
                
                # Nuevo Rango (Simulado)
                # Centramos en p_hoy con el mismo ancho porcentual relativo
                width_pct = (p_max_dyn - p_min_dyn) / 2 / ((p_max_dyn + p_min_dyn)/2)
                # O recalculamos basado en std teórica
                std_aprox_dyn = p_hoy * (volatilidad_anual * np.sqrt(window/365))
                p_min_dyn = p_hoy - (std_dev * std_aprox_dyn)
                p_max_dyn = p_hoy + (std_dev * std_aprox_dyn)
                
        resultados_dinamica.append(cap_dyn + fees_dyn - gas_total)

    progress_bar.empty()
    return precios_matrix, np.array(resultados_estatica), np.array(resultados_dinamica)

# --- UI PRINCIPAL ---

# 1. Generar y Calcular (Solo si se pulsa o cambia input)
matriz_precios = generar_montecarlo_precios(precio_actual, volatilidad_anual, tendencia_anual, dias_analisis, n_simulaciones)
matriz_precios, res_st, res_dyn = ejecutar_analisis_montecarlo(matriz_precios, capital_inicial, apr_estimado, gas_rebalanceo, bb_window, bb_std)

# --- RESULTADOS AGREGADOS ---

# Estadísticas Clave
mean_st = np.mean(res_st)
mean_dyn = np.mean(res_dyn)
median_st = np.median(res_st)
median_dyn = np.median(res_dyn)

# ¿Quién gana más veces?
wins_dyn = np.sum(res_dyn > res_st)
win_rate = (wins_dyn / n_simulaciones) * 100

st.subheader("📊 Resultados del Análisis Montecarlo")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Retorno PROMEDIO Estático", f"${mean_st:,.0f}", delta=f"{mean_st - capital_inicial:.0f} $ Netos")
    st.caption(f"Mediana: ${median_st:,.0f}")

with col2:
    st.metric("Retorno PROMEDIO Dinámico", f"${mean_dyn:,.0f}", delta=f"{mean_dyn - capital_inicial:.0f} $ Netos")
    st.caption(f"Mediana: ${median_dyn:,.0f}")

with col3:
    diff_promedio = mean_dyn - mean_st
    st.metric("Diferencia (Promedio)", f"${diff_promedio:,.0f}", delta_color="normal")
    if win_rate > 50:
        st.success(f"🏆 La Dinámica gana en el **{win_rate:.1f}%** de los escenarios.")
    else:
        st.error(f"🐢 La Estática gana en el **{100 - win_rate:.1f}%** de los escenarios.")

# --- GRÁFICO DE CONO DE PROBABILIDAD ---
st.subheader(f"Proyección de Precios ({n_simulaciones} Escenarios)")

# Calculamos percentiles para el gráfico (El Cono)
p10 = np.percentile(matriz_precios, 10, axis=1)
p50 = np.percentile(matriz_precios, 50, axis=1) # Mediana
p90 = np.percentile(matriz_precios, 90, axis=1)
x_axis = np.arange(len(p50))

fig = go.Figure()

# Área sombreada (Rango 10% - 90% de probabilidad)
fig.add_trace(go.Scatter(
    x=np.concatenate([x_axis, x_axis[::-1]]),
    y=np.concatenate([p90, p10[::-1]]),
    fill='toself',
    fillcolor='rgba(0, 200, 200, 0.2)',
    line=dict(color='rgba(255,255,255,0)'),
    name='Rango Probable (80% casos)'
))

# Línea Mediana
fig.add_trace(go.Scatter(
    x=x_axis, y=p50,
    mode='lines', line=dict(color='white', width=2),
    name='Precio Mediano'
))

# Línea del Rango Estático (Solo referencia visual inicial)
# Usamos el precio inicial para pintar el rango teórico inicial
std_aprox_viz = precio_actual * (volatilidad_anual * np.sqrt(bb_window/365))
r_min_viz = precio_actual - (bb_std * std_aprox_viz)
r_max_viz = precio_actual + (bb_std * std_aprox_viz)

fig.add_hline(y=r_max_viz, line_dash="dash", line_color="red", annotation_text="Límite Sup. Estático (Ref)")
fig.add_hline(y=r_min_viz, line_dash="dash", line_color="green", annotation_text="Límite Inf. Estático (Ref)")

fig.update_layout(
    template="plotly_dark", 
    height=500, 
    title="Cono de Probabilidad de Precio (Montecarlo)",
    xaxis_title="Días",
    yaxis_title="Precio ($)"
)

st.plotly_chart(fig, use_container_width=True)

# --- EXPLICACIÓN DIDÁCTICA ---
with st.expander("ℹ️ ¿Cómo interpretar estos datos?"):
    st.write("""
    **Análisis de Montecarlo:** En lugar de predecir el futuro una vez, hemos simulado el mercado **{} veces** con diferentes caminos aleatorios basados en la volatilidad.
    
    * **Retorno Promedio:** Es la media matemática de todos los escenarios.
    * **Probabilidad de Victoria:** Porcentaje de veces que una estrategia superó a la otra.
    * **Gráfico:** La línea blanca es el camino "central". La zona azulada indica dónde estará el precio el 80% de las veces. Si tus rangos estáticos (líneas punteadas) están muy lejos de la zona azul, es probable que te salgas de rango.
    """.format(n_simulaciones))
