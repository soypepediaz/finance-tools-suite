import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Liquidity Pro Calc", layout="wide")

st.title("⚖️ Optimizador: Auditoría Financiera V3")
st.markdown("---")

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("1. Mercado y Simulación")
    precio_actual = st.number_input("Precio Inicial ($)", value=65000.0)
    volatilidad_anual = st.slider("Volatilidad Anual (%)", 10, 200, 60) / 100
    tendencia_anual = st.slider("Tendencia Anual (%)", -50, 150, 0) / 100
    
    n_simulaciones = st.slider("Nº Simulaciones", 50, 1000, 200, step=50)
    dias_analisis = st.slider("Días a simular", 7, 365, 30, step=1)
    
    st.markdown("---")
    
    st.header("2. Estrategia ESTÁTICA")
    col_bb1, col_bb2 = st.columns(2)
    with col_bb1:
        bb_window = st.number_input("Ventana (Días)", value=7, min_value=1, max_value=90)
    with col_bb2:
        std_estatica = st.number_input("Ancho (SD)", value=2.0, step=0.1, min_value=0.5, max_value=5.0)
        
    apr_base_estatica = st.number_input("APR Base Estática (%)", value=15.0) / 100
    
    st.markdown("---")
    
    st.header("3. Estrategia DINÁMICA")
    pct_ancho_dinamico = st.slider("% del Ancho Estático", 5, 100, 25, step=5)
    
    st.markdown("**Costes Operativos**")
    gas_rebalanceo = st.number_input("Gas por Rebalanceo ($)", value=5.0)
    swap_fee = st.number_input("Swap Fee del Pool (%)", value=0.30, step=0.01, format="%.2f") / 100
    
    capital_inicial = st.number_input("Capital ($)", value=10000.0)
    
    factor_concentracion = 1 / (pct_ancho_dinamico / 100)
    st.info(f"⚡ **APR Dinámico:** {(apr_base_estatica * factor_concentracion)*100:.1f}% ({factor_concentracion:.1f}x)")

# --- 3. MOTOR MATEMÁTICO AVANZADO ---

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
    """
    Calcula el valor EXACTO de la posición al salir del rango.
    Asume entrada 50/50 en p_entry.
    """
    # 1. Caso: Salida por ARRIBA (Somos 100% Stable)
    # Valor = Stables Originales + (Tokens Originales * Precio Promedio Venta)
    if p_exit >= p_max:
        # En V3, el precio promedio de venta geométrico es sqrt(P_entry * P_max)
        # Nota: Asumimos rango simétrico centrado para simplificar la proporción
        precio_promedio_venta = np.sqrt(p_entry * p_max)
        
        # Teníamos el 50% del capital en tokens. Cantidad Tokens = (0.5 * Cap) / P_entry
        stables_originales = cap_entrada * 0.5
        valor_venta_tokens = (cap_entrada * 0.5 / p_entry) * precio_promedio_venta
        
        nuevo_valor = stables_originales + valor_venta_tokens
        return nuevo_valor

    # 2. Caso: Salida por ABAJO (Somos 100% Token)
    # Valor = (Tokens Originales + Tokens Comprados) * Precio Actual
    elif p_exit <= p_min:
        # Precio promedio de compra de los nuevos tokens = sqrt(P_entry * P_min)
        precio_promedio_compra = np.sqrt(p_entry * p_min)
        
        tokens_originales = (cap_entrada * 0.5) / p_entry
        # Compramos tokens con el 50% de stables
        tokens_comprados = (cap_entrada * 0.5) / precio_promedio_compra
        
        total_tokens = tokens_originales + tokens_comprados
        nuevo_valor = total_tokens * p_exit
        return nuevo_valor
    
    # Dentro de rango (aprox lineal para Montecarlo rápido)
    return cap_entrada

def ejecutar_analisis_auditado(precios_matrix, cap_inicial, apr_base, std_st, pct_dyn, gas, fee_swap, vol_anual, window_days):
    filas, columnas = precios_matrix.shape
    factor_concentracion = 1 / (pct_dyn / 100)
    fee_diario_st = apr_base / 365
    fee_diario_dyn = (apr_base * factor_concentracion) / 365 
    
    res_st_final = []
    res_dyn_final = []
    stats_dias_out_st = []
    stats_rebalanceos_dyn = []
    log_auditoria = []
    
    progress_bar = st.progress(0)

    for sim_idx in range(columnas):
        if sim_idx % (columnas // 10 + 1) == 0:
            progress_bar.progress(sim_idx / columnas)
            
        serie_precios = precios_matrix[:, sim_idx]
        p_inicial = serie_precios[0]
        
        # Rangos
        vol_periodo = vol_anual * np.sqrt(window_days/365)
        delta_st = p_inicial * vol_periodo * std_st
        delta_dyn_base = delta_st * (pct_dyn / 100)
        
        # --- ESTÁTICA ---
        p_min_st = p_inicial - delta_st
        p_max_st = p_inicial + delta_st
        
        # Valoración final Estática (Simplificada vs Hold)
        p_final = serie_precios[-1]
        val_estatico = calcular_valor_v3_exacto(cap_inicial, p_inicial, p_final, p_min_st, p_max_st)
        
        in_range_mask = (serie_precios >= p_min_st) & (serie_precios <= p_max_st)
        fees_st = np.sum(in_range_mask) * (cap_inicial * fee_diario_st)
        res_st_final.append(val_estatico + fees_st)
        stats_dias_out_st.append(filas - np.sum(in_range_mask))
        
        # --- DINÁMICA ---
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
                
                # --- CÁLCULO PRECISO DEL REBALANCEO ---
                cap_antes = cap_dyn # Valor nominal al inicio del día (aproximado)
                
                # 1. Calcular Valor REAL de salida (Mark-to-Market V3)
                # Aquí usamos el precio de entrada del rango anterior (aprox p_hoy-1 o el centro del rango)
                p_centro_rango_anterior = (p_max_dyn + p_min_dyn) / 2
                
                # Nuevo Capital basado en la ejecución real de la liquidez
                cap_nuevo_real = calcular_valor_v3_exacto(cap_dyn, p_centro_rango_anterior, p_hoy, p_min_dyn, p_max_dyn)
                
                # 2. Calcular Valor HOLD (Benchmark)
                # Si hubiéramos mantenido 50/50 desde el centro del rango anterior sin pool
                val_hold = (cap_dyn * 0.5) + ((cap_dyn * 0.5 / p_centro_rango_anterior) * p_hoy)
                
                # 3. La Pérdida IL Realizada es la diferencia
                # Nota: IL siempre es negativo (pérdida). Lo mostramos positivo como "Coste"
                perdida_il = max(0, val_hold - cap_nuevo_real)
                
                # Actualizamos el capital disponible
                cap_dyn = cap_nuevo_real
                
                # 4. Costes Fijos
                gas_total += gas
                coste_swap = cap_dyn * 0.50 * fee_swap
                cap_dyn -= (coste_swap + gas) # Descontamos del principal
                
                # LOG (Simulación 1)
                if sim_idx == 0:
                    evento = "⬆️ Subida (Salida Top)" if p_hoy > p_max_dyn else "⬇️ Bajada (Salida Bottom)"
                    log_auditoria.append({
                        "Día": dia,
                        "Precio": p_hoy,
                        "Evento": evento,
                        "Valor Hold (50/50)": val_hold,
                        "Valor Pool (Salida)": cap_nuevo_real,
                        "Pérdida IL Realizada": perdida_il,
                        "Swap Fee": coste_swap,
                        "Gas": gas,
                        "Capital Final": cap_dyn
                    })
                
                # Nuevo Rango
                nuevo_delta = p_hoy * ratio_half_width
                p_min_dyn = p_hoy - nuevo_delta
                p_max_dyn = p_hoy + nuevo_delta
                
        stats_rebalanceos_dyn.append(num_rebalanceos)
        res_dyn_final.append(cap_dyn + fees_dyn_acum)

    progress_bar.empty()
    return (np.array(res_st_final), np.array(res_dyn_final), 
            np.mean(stats_dias_out_st), np.mean(stats_rebalanceos_dyn),
            factor_concentracion, delta_st, log_auditoria)

# --- 4. EJECUCIÓN ---

matriz = generar_montecarlo_precios(precio_actual, volatilidad_anual, tendencia_anual, dias_analisis, n_simulaciones)

res_estatica, res_dinamica, avg_dias_out, avg_rebalanceos, factor, delta_viz, log_data = ejecutar_analisis_auditado(
    matriz, capital_inicial, apr_base_estatica, 
    std_estatica, pct_ancho_dinamico, gas_rebalanceo, swap_fee, volatilidad_anual, bb_window
)

# --- 5. VISUALIZACIÓN ---

# Dashboard de métricas y gráficos (Igual que versión anterior)
mean_st = np.mean(res_estatica)
mean_dyn = np.mean(res_dinamica)
win_rate = (np.sum(res_dinamica > res_estatica) / n_simulaciones) * 100

st.subheader("🏁 Resultados Finales (Promedio)")
k1, k2, k3 = st.columns(3)
k1.metric("Estática", f"${mean_st:,.0f}", f"{mean_st-capital_inicial:+.0f} $ Netos")
k2.metric("Dinámica", f"${mean_dyn:,.0f}", f"{mean_dyn-capital_inicial:+.0f} $ Netos")
winner = "Dinámica" if mean_dyn > mean_st else "Estática"
k3.metric("Ganador", winner, f"Gana el {win_rate:.0f}% de las veces")

# Gráficos
c_chart1, c_chart2 = st.columns(2)
with c_chart1:
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

with c_chart2:
    st.caption("Distribución de Retornos")
    fig2 = go.Figure()
    fig2.add_trace(go.Histogram(x=res_estatica, name='Estática', marker_color='#2ecc71', opacity=0.7))
    fig2.add_trace(go.Histogram(x=res_dinamica, name='Dinámica', marker_color='#e74c3c', opacity=0.7))
    fig2.update_layout(template="plotly_dark", height=300, margin=dict(t=10,b=10), barmode='overlay')
    st.plotly_chart(fig2, use_container_width=True)

# --- AUDITORÍA FINANCIERA DETALLADA ---
st.subheader("📋 Auditoría Financiera (Simulación #1)")

with st.expander("🔎 Ver desglose matemático de pérdidas (IL y Fees)", expanded=True):
    if len(log_data) > 0:
        df_log = pd.DataFrame(log_data)
        
        st.write("""
        Esta tabla demuestra cómo **salir del rango destruye valor relativo** aunque el precio suba.
        * **Valor Hold:** Lo que tendrías si te hubieras quedado quieto con tu 50% Crypto / 50% USD desde el último rebalanceo.
        * **Valor Pool:** Lo que realmente tienes (has vendido crypto mientras subía, o comprado mientras bajaba).
        * **Pérdida IL:** La diferencia irrecuperable entre Hold y Pool.
        """)
        
        st.dataframe(df_log.style.format({
            "Precio": "${:,.2f}",
            "Valor Hold (50/50)": "${:,.2f}",
            "Valor Pool (Salida)": "${:,.2f}",
            "Pérdida IL Realizada": "${:,.2f}", 
            "Swap Fee": "${:,.2f}",
            "Gas": "${:,.2f}",
            "Capital Final": "${:,.2f}"
        }), use_container_width=True)
        
        il_total = df_log["Pérdida IL Realizada"].sum()
        swap_total = df_log["Swap Fee"].sum()
        
        st.error(f"💸 En esta simulación, has dejado de ganar **${il_total:,.2f}** por Impermanent Loss y has pagado **${swap_total:,.2f}** en comisiones.")
    else:
        st.success("Sin rebalanceos en esta simulación.")
