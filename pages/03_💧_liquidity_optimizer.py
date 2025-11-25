import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Liquidity Pro Calc", layout="wide")

st.title("⚡ Optimizador: Eficiencia de Capital")
st.markdown("---")

# --- SIDEBAR: PARÁMETROS ---
with st.sidebar:
    st.header("1. Mercado y Simulación")
    precio_actual = st.number_input("Precio Inicial ($)", value=65000.0)
    volatilidad_anual = st.slider("Volatilidad Anual (%)", 10, 200, 60) / 100
    tendencia_anual = st.slider("Tendencia Anual (%)", -50, 150, 0) / 100
    n_simulaciones = st.slider("Nº Simulaciones", 50, 500, 200, step=50)
    dias_analisis = st.slider("Días a simular", 7, 365, 30, step=1)
    
    st.header("2. Estrategia ESTÁTICA (Base)")
    # Definimos la "anchura base" usando Bollinger
    std_estatica = st.slider("Ancho Estática (SD)", 1.0, 5.0, 3.0, 0.1, help="Define cuán ancha es la posición segura.")
    apr_base_estatica = st.number_input("APR Base Estática (%)", value=15.0) / 100
    
    st.header("3. Estrategia DINÁMICA (Agresiva)")
    # NUEVO INPUT: Porcentaje del rango estático
    pct_ancho_dinamico = st.slider("% del Ancho Estático", 5, 100, 20, step=5, help="Si pones 20%, el rango dinámico será un 20% del tamaño del estático (5x más concentrado).")
    
    gas_rebalanceo = st.number_input("Coste Gas Rebalanceo ($)", value=5.0)
    capital_inicial = st.number_input("Capital ($)", value=10000.0)
    
    # --- CÁLCULOS AUTOMÁTICOS DE EFICIENCIA ---
    factor_concentracion = 1 / (pct_ancho_dinamico / 100)
    apr_dinamico_teorico = apr_base_estatica * factor_concentracion
    
    st.markdown("---")
    st.info(f"""
    🔥 **Potencia de Concentración:**
    Estás usando un rango al **{pct_ancho_dinamico}%** del tamaño original.
    
    * Multiplicador: **{factor_concentracion:.2f}x**
    * APR Dinámico: **{apr_dinamico_teorico*100:.1f}%**
    """)
    
    bb_window = 30 

# --- NÚCLEO MATEMÁTICO ---

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

def ejecutar_analisis_eficiencia(precios_matrix, cap_inicial, apr_base, std_st, pct_dyn, gas, vol_anual):
    filas, columnas = precios_matrix.shape
    
    # 1. Calcular Multiplicador de Eficiencia
    # Si pct_dyn es 20% (0.2), el multiplicador es 5.
    factor_concentracion = 1 / (pct_dyn / 100)
    
    fee_diario_st = apr_base / 365
    fee_diario_dyn = (apr_base * factor_concentracion) / 365 
    
    res_st = []
    res_dyn = []
    
    progress_bar = st.progress(0)

    for sim_idx in range(columnas):
        if sim_idx % (columnas // 10 + 1) == 0:
            progress_bar.progress(sim_idx / columnas)
            
        serie_precios = precios_matrix[:, sim_idx]
        p_inicial = serie_precios[0]
        
        # --- CÁLCULO DE ANCHOS ---
        # Calculamos el "Delta" (mitad del ancho) de la estática basado en Bollinger
        # Delta = Precio * Vol_30dias * SD
        delta_st = p_inicial * (vol_anual * np.sqrt(30/365)) * std_st
        
        # Calculamos el "Delta" de la dinámica basado en el % del estático
        # Si la estática es +/- $1000, y pct es 20%, la dinámica es +/- $200
        delta_dyn_base = delta_st * (pct_dyn / 100)
        
        # --- 1. ESTRATEGIA ESTÁTICA ---
        p_min_st = p_inicial - delta_st
        p_max_st = p_inicial + delta_st
        
        # Lógica Estática
        in_range_mask = (serie_precios >= p_min_st) & (serie_precios <= p_max_st)
        fees_st_acum = np.sum(in_range_mask) * (cap_inicial * fee_diario_st)
        
        p_final = serie_precios[-1]
        val_prin_st = cap_inicial
        if p_final < p_min_st:
            val_prin_st = cap_inicial * (p_final / p_min_st)
        elif p_final > p_max_st:
            val_prin_st = cap_inicial 
        
        res_st.append(val_prin_st + fees_st_acum)
        
        # --- 2. ESTRATEGIA DINÁMICA ---
        cap_dyn = cap_inicial
        fees_dyn_acum = 0
        gas_total = 0
        
        # Rango inicial
        p_min_dyn = p_inicial - delta_dyn_base
        p_max_dyn = p_inicial + delta_dyn_base
        
        # En la dinámica, el ancho se mantiene proporcional al precio actual
        # Calculamos qué % representa delta_dyn sobre el precio inicial para mantener ese ratio
        # Ratio medio ancho = delta / precio
        ratio_half_width = delta_dyn_base / p_inicial
        
        for dia in range(1, filas):
            p_hoy = serie_precios[dia]
            
            if p_min_dyn <= p_hoy <= p_max_dyn:
                fees_dyn_acum += cap_dyn * fee_diario_dyn
            else:
                # REBALANCEO
                gas_total += gas
                
                # IL Realizado (Simplificado)
                if p_hoy < p_min_dyn:
                    cap_dyn = cap_dyn * (p_hoy / p_min_dyn)
                
                # Nuevo Rango: Centrado en precio hoy, manteniendo el % de ancho relativo
                nuevo_delta = p_hoy * ratio_half_width
                p_min_dyn = p_hoy - nuevo_delta
                p_max_dyn = p_hoy + nuevo_delta
                
        res_dyn.append(cap_dyn + fees_dyn_acum - gas_total)

    progress_bar.empty()
    return np.array(res_st), np.array(res_dyn), factor_concentracion

# --- EJECUCIÓN ---

matriz = generar_montecarlo_precios(precio_actual, volatilidad_anual, tendencia_anual, dias_analisis, n_simulaciones)

res_estatica, res_dinamica, factor = ejecutar_analisis_eficiencia(
    matriz, capital_inicial, apr_base_estatica, 
    std_estatica, pct_ancho_dinamico, gas_rebalanceo, volatilidad_anual
)

# --- VISUALIZACIÓN ---

# Estadísticas
mean_st = np.mean(res_estatica)
mean_dyn = np.mean(res_dinamica)
win_rate = (np.sum(res_dinamica > res_estatica) / n_simulaciones) * 100

st.subheader("🏁 Resultados de la Simulación")

col1, col2, col3 = st.columns(3)
col1.metric("Estática (Base)", f"${mean_st:,.0f}", f"APR: {apr_base_estatica*100:.1f}%")
col2.metric("Dinámica (Concentrada)", f"${mean_dyn:,.0f}", f"APR: {(apr_base_estatica * factor)*100:.1f}%")

diff = mean_dyn - mean_st
msg_winner = "Dinámica" if diff > 0 else "Estática"
col3.metric("Diferencia Promedio", f"${diff:,.0f}", f"Gana {msg_winner} ({win_rate:.0f}% veces)")

# Histograma Comparativo
fig_hist = go.Figure()
fig_hist.add_trace(go.Histogram(x=res_estatica, name='Estática', opacity=0.75, marker_color='#2ecc71')) # Verde
fig_hist.add_trace(go.Histogram(x=res_dinamica, name='Dinámica', opacity=0.75, marker_color='#e74c3c')) # Rojo
fig_hist.update_layout(
    barmode='overlay', 
    title=f"Distribución de Resultados ({n_simulaciones} simulaciones)", 
    xaxis_title="Valor Final de la Posición ($)",
    template="plotly_dark"
)
st.plotly_chart(fig_hist, use_container_width=True)

with st.expander("📐 Entender la Lógica del Porcentaje"):
    st.write(f"""
    1.  **Rango Estático:** Calculado con {std_estatica} Desviaciones Estándar. (Seguro y ancho).
    2.  **Rango Dinámico:** Has elegido usar solo el **{pct_ancho_dinamico}%** de ese ancho.
    3.  **Resultado:** Al concentrar la liquidez en un espacio {factor:.1f} veces más pequeño, tu liquidez "trabaja" {factor:.1f} veces más duro.
    4.  **Trade-off:** Ganas {factor:.1f}x más fees por día, pero te sales de rango con mucha más facilidad, obligándote a rebalancear (y gastar gas/realizar pérdidas).
    """)
