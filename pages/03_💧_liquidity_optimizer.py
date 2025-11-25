import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Liquidity Pro Calc", layout="wide")

st.title("⚖️ Optimizador Realista: Costes de Rebalanceo")
st.markdown("---")

# --- SIDEBAR: PARÁMETROS ---
with st.sidebar:
    st.header("1. Mercado y Simulación")
    precio_actual = st.number_input("Precio Inicial ($)", value=65000.0)
    volatilidad_anual = st.slider("Volatilidad Anual (%)", 10, 200, 60) / 100
    tendencia_anual = st.slider("Tendencia Anual (%)", -50, 150, 0) / 100
    n_simulaciones = st.slider("Nº Simulaciones", 50, 500, 200, step=50)
    dias_analisis = st.slider("Días a simular", 7, 365, 30, step=1)
    
    st.header("2. Estrategia ESTÁTICA")
    std_estatica = st.slider("Ancho Estática (SD)", 1.0, 5.0, 3.0, 0.1)
    apr_base_estatica = st.number_input("APR Base Estática (%)", value=15.0) / 100
    
    st.header("3. Estrategia DINÁMICA")
    pct_ancho_dinamico = st.slider("% del Ancho Estático", 5, 100, 25, step=5)
    
    st.markdown("**Costes de Fricción**")
    gas_rebalanceo = st.number_input("Gas por Rebalanceo ($)", value=5.0)
    swap_fee = st.number_input("Swap Fee del Pool (%)", value=0.30, step=0.01, format="%.2f", help="Comisión que pagas al hacer el swap del 50% de la cartera para recentrar el rango.") / 100
    
    capital_inicial = st.number_input("Capital ($)", value=10000.0)
    
    # Info Eficiencia
    factor_concentracion = 1 / (pct_ancho_dinamico / 100)
    apr_dinamico_teorico = apr_base_estatica * factor_concentracion
    st.info(f"⚡ **APR Dinámico Potencial:** {apr_dinamico_teorico*100:.1f}% ({factor_concentracion:.1f}x)")
    
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

def ejecutar_analisis_completo(precios_matrix, cap_inicial, apr_base, std_st, pct_dyn, gas, fee_swap, vol_anual):
    filas, columnas = precios_matrix.shape
    factor_concentracion = 1 / (pct_dyn / 100)
    
    fee_diario_st = apr_base / 365
    fee_diario_dyn = (apr_base * factor_concentracion) / 365 
    
    # Arrays para guardar resultados finales
    res_st_final = []
    res_dyn_final = []
    
    # Arrays para guardar estadísticas operativas
    stats_dias_out_st = []
    stats_rebalanceos_dyn = []
    
    progress_bar = st.progress(0)

    for sim_idx in range(columnas):
        if sim_idx % (columnas // 10 + 1) == 0:
            progress_bar.progress(sim_idx / columnas)
            
        serie_precios = precios_matrix[:, sim_idx]
        p_inicial = serie_precios[0]
        
        # --- CÁLCULO DE RANGOS INICIALES ---
        delta_st = p_inicial * (vol_anual * np.sqrt(30/365)) * std_st
        delta_dyn_base = delta_st * (pct_dyn / 100)
        
        # ==============================
        # 1. ESTRATEGIA ESTÁTICA
        # ==============================
        p_min_st = p_inicial - delta_st
        p_max_st = p_inicial + delta_st
        
        # Vectorizamos el cálculo de días en rango
        in_range_mask = (serie_precios >= p_min_st) & (serie_precios <= p_max_st)
        dias_in = np.sum(in_range_mask)
        dias_out = filas - dias_in
        stats_dias_out_st.append(dias_out)
        
        fees_st_acum = dias_in * (cap_inicial * fee_diario_st)
        
        # Valoración final (Mark to Market + IL latente)
        p_final = serie_precios[-1]
        val_prin_st = cap_inicial
        if p_final < p_min_st:
            val_prin_st = cap_inicial * (p_final / p_min_st)
        elif p_final > p_max_st:
            val_prin_st = cap_inicial 
        # (Si está en rango, asumimos valor ~ capital inicial simplificado para mantener paridad de comparación,
        # aunque estrictamente habría un pequeño IL no realizado)
        
        res_st_final.append(val_prin_st + fees_st_acum)
        
        # ==============================
        # 2. ESTRATEGIA DINÁMICA
        # ==============================
        cap_dyn = cap_inicial
        fees_dyn_acum = 0
        gas_total = 0
        costes_swap_total = 0
        num_rebalanceos = 0
        
        # Rango inicial
        p_min_dyn = p_inicial - delta_dyn_base
        p_max_dyn = p_inicial + delta_dyn_base
        
        # Ratio para mantener el ancho relativo
        ratio_half_width = delta_dyn_base / p_inicial
        
        for dia in range(1, filas):
            p_hoy = serie_precios[dia]
            
            if p_min_dyn <= p_hoy <= p_max_dyn:
                # DENTRO DE RANGO: Ganamos fees boosteados
                fees_dyn_acum += cap_dyn * fee_diario_dyn
            else:
                # FUERA DE RANGO -> REBALANCEO
                num_rebalanceos += 1
                
                # 1. Realización de Pérdida (IL se vuelve permanente)
                # Si bajó, nuestro capital vale menos porque tenemos 100% del activo depreciado
                if p_hoy < p_min_dyn:
                    cap_dyn = cap_dyn * (p_hoy / p_min_dyn)
                # Si subió, nuestro capital está capado en stable, no "pierde" nominalmente, 
                # pero pierde poder de compra vs el activo.
                
                # 2. Coste de Gas
                gas_total += gas
                
                # 3. Coste de Swap (NUEVO Y CRÍTICO)
                # Para recentrar, asumimos swap del 50% del portfolio
                coste_swap = cap_dyn * 0.50 * fee_swap
                costes_swap_total += coste_swap
                cap_dyn -= coste_swap # El fee se paga del principal
                
                # 4. Nuevo Rango
                nuevo_delta = p_hoy * ratio_half_width
                p_min_dyn = p_hoy - nuevo_delta
                p_max_dyn = p_hoy + nuevo_delta
                
        stats_rebalanceos_dyn.append(num_rebalanceos)
        res_dyn_final.append(cap_dyn + fees_dyn_acum - gas_total)

    progress_bar.empty()
    return (np.array(res_st_final), np.array(res_dyn_final), 
            np.mean(stats_dias_out_st), np.mean(stats_rebalanceos_dyn),
            factor_concentracion)

# --- EJECUCIÓN ---

matriz = generar_montecarlo_precios(precio_actual, volatilidad_anual, tendencia_anual, dias_analisis, n_simulaciones)

res_estatica, res_dinamica, avg_dias_out, avg_rebalanceos, factor = ejecutar_analisis_completo(
    matriz, capital_inicial, apr_base_estatica, 
    std_estatica, pct_ancho_dinamico, gas_rebalanceo, swap_fee, volatilidad_anual
)

# --- DASHBOARD DE RESULTADOS ---

# 1. KPIs Principales
mean_st = np.mean(res_estatica)
mean_dyn = np.mean(res_dinamica)
win_rate = (np.sum(res_dinamica > res_estatica) / n_simulaciones) * 100

st.subheader("🏁 Comparativa de Rendimiento")

kpi1, kpi2, kpi3 = st.columns(3)

# Estática
diff_st = mean_st - capital_inicial
kpi1.metric("Estática (Promedio)", f"${mean_st:,.0f}", f"{diff_st:+.0f} $ Netos")
kpi1.caption(f"📅 Pasa {avg_dias_out:.1f} días fuera de rango ({avg_dias_out/dias_analisis*100:.0f}%)")

# Dinámica
diff_dyn = mean_dyn - capital_inicial
kpi2.metric("Dinámica (Promedio)", f"${mean_dyn:,.0f}", f"{diff_dyn:+.0f} $ Netos")
kpi2.caption(f"🔄 Realiza {avg_rebalanceos:.1f} rebalanceos (Coste Swap+Gas incluido)")

# Veredicto
diff_total = mean_dyn - mean_st
winner = "Dinámica" if diff_total > 0 else "Estática"
kpi3.metric("Diferencia", f"${diff_total:,.0f}", f"Gana {winner} ({win_rate:.0f}% veces)")

# --- VISUALIZACIÓN 1: EL CONO (Contexto de Mercado) ---
st.subheader("1. Escenarios de Precio (Cono de Volatilidad)")

p10 = np.percentile(matriz, 10, axis=1)
p50 = np.percentile(matriz, 50, axis=1)
p90 = np.percentile(matriz, 90, axis=1)
x_axis = np.arange(len(p50))

fig_cone = go.Figure()

# Rango Dinámico (Sombreado)
fig_cone.add_trace(go.Scatter(
    x=np.concatenate([x_axis, x_axis[::-1]]),
    y=np.concatenate([p90, p10[::-1]]),
    fill='toself', fillcolor='rgba(0, 150, 255, 0.15)',
    line=dict(color='rgba(255,255,255,0)'),
    name='80% Probabilidad'
))
# Mediana
fig_cone.add_trace(go.Scatter(x=x_axis, y=p50, mode='lines', line=dict(color='white', width=2), name='Precio Mediano'))

# Líneas del Rango Estático
delta_viz = precio_actual * (volatilidad_anual * np.sqrt(30/365)) * std_estatica
fig_cone.add_hline(y=precio_actual + delta_viz, line_dash="dash", line_color="#2ecc71", annotation_text="Límite Sup. Estático")
fig_cone.add_hline(y=precio_actual - delta_viz, line_dash="dash", line_color="#2ecc71", annotation_text="Límite Inf. Estático")

fig_cone.update_layout(template="plotly_dark", height=400, margin=dict(t=30, b=10), title="Proyección de Precio vs Rango Estático")
st.plotly_chart(fig_cone, use_container_width=True)

# --- VISUALIZACIÓN 2: DISTRIBUCIÓN (Riesgo) ---
st.subheader("2. Distribución de Resultados Finales")

fig_hist = go.Figure()
fig_hist.add_trace(go.Histogram(x=res_estatica, name='Estática', opacity=0.7, marker_color='#2ecc71', nbinsx=40))
fig_hist.add_trace(go.Histogram(x=res_dinamica, name='Dinámica', opacity=0.7, marker_color='#e74c3c', nbinsx=40))

fig_hist.add_vline(x=mean_st, line_dash="dash", line_color="#2ecc71", annotation_text="Media Est.")
fig_hist.add_vline(x=mean_dyn, line_dash="dash", line_color="#e74c3c", annotation_text="Media Dyn.")

fig_hist.update_layout(template="plotly_dark", height=400, margin=dict(t=30, b=10), barmode='overlay', xaxis_title="Capital Final ($)")
st.plotly_chart(fig_hist, use_container_width=True)

# --- ANÁLISIS ---
with st.expander("🔎 Análisis detallado de los costes"):
    st.write(f"""
    **¿Por qué es importante el Swap Fee?**
    La estrategia dinámica ha realizado un promedio de **{avg_rebalanceos:.1f} movimientos**.
    
    Cada vez que rebalancea:
    1.  Paga **${gas_rebalanceo}** de Gas.
    2.  Intercambia aprox. el 50% de la cartera, pagando un **{swap_fee*100}%** de comisión.
    
    En mercados muy volátiles, estos costes se comen el beneficio del APR extra ("La muerte por mil cortes").
    """)
