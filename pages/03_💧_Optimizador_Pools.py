import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Liquidity Pro Calc", layout="wide")
st.title("⚖️ Optimizador: Auditoría por Operaciones")
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

# --- 3. FUNCIONES MATEMÁTICAS ---

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
    
    progress_bar = st.progress(0)

    for sim_idx in range(columnas):
        if sim_idx % (columnas // 10 + 1) == 0:
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
                    precio_ruptura = p_max_dyn # Precio límite visual
                else:
                    evento = "Ruptura Rango Inferior ⬇️"
                    precio_ruptura = p_min_dyn # Precio límite visual
                
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
                
                # F. Log (Solo Simulación 1)
                if sim_idx == 0:
                    log_operaciones.append({
                        "Operación": num_rebalanceos,
                        "Rango Teórico": f"{p_min_dyn:.0f} - {p_max_dyn:.0f}",
                        "Día In/Out": f"Día {op_start_day} ➝ {dia}",
                        "Fees Generados": fees_acumulados_operacion,
                        "Valor Salida Pool": val_salida_pool,
                        "Pérdida IL (Info)": il_realizado,
                        "Costes (Swap+Gas)": costes_totales,
                        "Capital Final": cap_nuevo,
                        "Evento": evento,
                        "Precio Ruptura": precio_ruptura # Usamos el límite del rango
                    })
                
                # G. Reset para Siguiente Operación
                cap_dyn = cap_nuevo
                op_start_day = dia
                fees_acumulados_operacion = 0
                
                # Nuevo Rango centrado en p_hoy (El rebalanceo se hace al precio real de mercado)
                nuevo_delta = p_hoy * ratio_width
                p_min_dyn = p_hoy - nuevo_delta
                p_max_dyn = p_hoy + nuevo_delta

        res_dyn_final.append(cap_dyn + fees_acumulados_operacion)
        stats_rebalanceos.append(num_rebalanceos)

    progress_bar.empty()
    return (np.array(res_st_final), np.array(res_dyn_final), 
            np.mean(stats_rebalanceos), delta_st, log_operaciones)

# --- 4. EJECUCIÓN ---
matriz = generar_montecarlo_precios(precio_actual, volatilidad_anual, tendencia_anual, dias_analisis, n_simulaciones)

res_st, res_dyn, avg_reb, delta_viz, log_ops = ejecutar_analisis_operaciones(
    matriz, capital_inicial, apr_base_estatica, std_estatica, pct_ancho_dinamico, 
    gas_rebalanceo, swap_fee, volatilidad_anual, bb_window
)

# --- 5. VISUALIZACIÓN ---
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

# --- TABLA DE OPERACIONES ---
st.subheader("📋 Registro de Operaciones (Simulación #1)")
st.info("Esta tabla muestra la secuencia de rebalanceos en la primera simulación. 'Precio Ruptura' indica el límite del rango donde se realizó la salida.")

if len(log_ops) > 0:
    df_ops = pd.DataFrame(log_ops)
    
    # Mostramos la tabla formateada
    st.dataframe(df_ops.style.format({
        "Fees Generados": "+${:,.2f}",
        "Valor Salida Pool": "${:,.2f}",
        "Pérdida IL (Info)": "${:,.2f}",
        "Costes (Swap+Gas)": "-${:,.2f}",
        "Capital Final": "${:,.2f}",
        "Precio Ruptura": "${:,.2f}"
    }), use_container_width=True)
    
    # --- CÁLCULO DEL P&L OPERATIVO (INGRESOS vs GASTOS) ---
    total_ingresos = df_ops["Fees Generados"].sum()
    
    # Gastos = Costes de Fricción (Swap+Gas) + Costes de Oportunidad Realizados (IL)
    total_friccion = df_ops["Costes (Swap+Gas)"].sum()
    total_il = df_ops["Pérdida IL (Info)"].sum()
    total_gastos = total_friccion + total_il
    
    # Resultado Neto
    neto_operativo = total_ingresos - total_gastos
    roi_gastos = (total_ingresos / total_gastos) * 100 if total_gastos > 0 else 0
    
    # Lógica del Diagnóstico
    if neto_operativo > 0:
        estado = "✅ **NEGOCIO RENTABLE**"
        mensaje = f"Tus ingresos (Fees) cubren todos los costes operativos (incluyendo el IL). Por cada $100 que gastas en rebalancear y asumir pérdidas, el mercado te devuelve **${roi_gastos:.0f}**."
    else:
        estado = "❌ **NEGOCIO EN PÉRDIDAS**"
        mensaje = f"Los fees no son suficientes para compensar el coste de rebalancear (vender barato/comprar caro). Estás perdiendo dinero operativamente. Sería mejor una estrategia estática (menos costes)."

    # Visualización del Resumen Operativo
    st.markdown("### 📊 Cuenta de Resultados Operativa")
    col_res1, col_res2, col_res3 = st.columns(3)
    
    col_res1.metric("Ingresos Totales (Fees)", f"${total_ingresos:,.2f}")
    col_res2.metric("Gastos Totales (IL + Swap + Gas)", f"-${total_gastos:,.2f}", help=f"Desglose: -${total_il:,.0f} (IL) y -${total_friccion:,.0f} (Comisiones)")
    col_res3.metric("Beneficio Neto Operativo", f"${neto_operativo:,.2f}", delta="Beneficio" if neto_operativo > 0 else "Pérdida")
    
    st.markdown(f"""
    ---
    **Diagnóstico de la Estrategia:**
    {estado}
    * {mensaje}
    """)
    
else:
    st.success("En esta simulación no hubo rebalanceos (Hold perfecto). El Beneficio Neto es igual a los Fees totales generados.")
