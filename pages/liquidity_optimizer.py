import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.stats import norm

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Liquidity Optimizer", layout="wide")

st.title("🧪 Optimizador de Liquidez Concentrada")
st.markdown("---")

# --- SIDEBAR: PARÁMETROS ---
with st.sidebar:
    st.header("⚙️ Configuración")
    
    # 1. Datos del Activo
    st.subheader("Simulación de Mercado")
    precio_actual = st.number_input("Precio Inicial ($)", value=1000.0)
    volatilidad_anual = st.slider("Volatilidad Anual (%)", 10, 200, 80) / 100
    tendencia_anual = st.slider("Tendencia Anual (%)", -50, 150, 20) / 100
    
    # 2. Parámetros de la Estrategia
    st.subheader("Estrategia")
    dias_analisis = st.slider("Días a simular", 7, 365, 30)
    apr_estimado = st.number_input("APR Pool Estimado (%)", value=40.0) / 100
    gas_rebalanceo = st.number_input("Coste Gas por Rebalanceo ($)", value=15.0)
    capital_inicial = st.number_input("Capital a Invertir ($)", value=10000.0)

    # 3. Bollinger (Rangos)
    st.subheader("Definición de Rangos")
    bb_window = st.selectbox("Media Móvil (Días)", [7, 14, 30, 60, 90], index=2)
    bb_std = st.slider("Desviaciones (SD)", 0.5, 4.0, 2.0, 0.1)

# --- FUNCIONES CORE (LÓGICA) ---

def generar_datos_mercado(precio, vol, tendencia, dias):
    """Genera una serie de precios simulada (Geometric Brownian Motion)"""
    dt = 1/365
    precios = [precio]
    mu = tendencia
    sigma = vol
    
    for _ in range(dias):
        shock = np.random.normal(0, 1)
        # Fórmula GBM: P_t = P_t-1 * exp((mu - 0.5*sigma^2)*dt + sigma*sqrt(dt)*Z)
        cambio = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shock
        precios.append(precios[-1] * np.exp(cambio))
        
    return pd.DataFrame(precios, columns=['close'])

def calcular_bollinger(df, window, std_dev):
    df['sma'] = df['close'].rolling(window=window).mean()
    df['std'] = df['close'].rolling(window=window).std()
    df['upper'] = df['sma'] + (df['std'] * std_dev)
    df['lower'] = df['sma'] - (df['std'] * std_dev)
    # Rellenamos NaN iniciales con el primer valor calculado válido para que no rompa
    df = df.bfill() 
    return df

def simular_comparativa(df, cap_inicial, apr, gas, window, std_dev):
    
    # --- PREPARACIÓN ---
    # Usamos los primeros 'window' días para calentar el indicador, la simulación empieza después
    if len(df) <= window:
        st.error("Necesitamos más días de datos para calcular la media móvil inicial.")
        return None
        
    # Calculamos bandas para todo el dataset
    df_bb = calcular_bollinger(df.copy(), window, std_dev)
    
    # Cortamos el DF para empezar la simulación "hoy" (usando datos pasados para la primera banda)
    # Para simplificar visualización, simularemos sobre todo el periodo generado
    # asumiendo que el día 0 ya tenemos bandas
    
    # --- ESTRATEGIA ESTÁTICA ---
    rango_inicial = df_bb.iloc[0]
    p_min_st = rango_inicial['lower']
    p_max_st = rango_inicial['upper']
    
    cap_estatico = cap_inicial
    fees_estatico = 0
    dias_rango_st = 0
    
    # --- ESTRATEGIA DINÁMICA ---
    cap_dinamico = cap_inicial
    fees_dinamico = 0
    gas_gastado = 0
    rebalanceos = 0
    p_min_dyn = p_min_st
    p_max_dyn = p_max_st
    
    fee_diario = apr / 365
    
    historia_dinamica = [] # Para graficar el valor del portfolio en el tiempo
    
    for i, row in df_bb.iterrows():
        precio = row['close']
        
        # 1. ESTÁTICA
        if p_min_st <= precio <= p_max_st:
            fees_estatico += cap_estatico * fee_diario
            dias_rango_st += 1
            
        # Valoración simple Estática (aprox IL)
        # Si se sale por arriba, valor bloqueado en p_max (todo stable)
        # Si se sale por abajo, valor cae con el activo
        val_estatico_hoy = cap_inicial # Empezamos asumiendo valor estable
        if precio > p_max_st:
            val_estatico_hoy = cap_inicial # Capped
        elif precio < p_min_st:
            val_estatico_hoy = cap_inicial * (precio / p_min_st)
        
        # 2. DINÁMICA
        in_range_dyn = p_min_dyn <= precio <= p_max_dyn
        
        if in_range_dyn:
            fees_dinamico += cap_dinamico * fee_diario
        else:
            # Rebalanceo
            rebalanceos += 1
            gas_gastado += gas
            
            # Realizar IL (Aproximación simplificada)
            if precio > p_max_dyn:
                 # Salida por arriba: Tenemos todo en Stable, valor preservado nominalmente
                 pass 
            elif precio < p_min_dyn:
                 # Salida por abajo: Tenemos todo en Token, el valor ha caído
                 cap_dinamico = cap_dinamico * (precio / p_min_dyn)
            
            # Resetear rangos
            # Nota: En la vida real el rango depende de la volatilidad DE ESE MOMENTO
            # Aquí usamos las bandas calculadas en ese día 'i'
            p_min_dyn = row['lower']
            p_max_dyn = row['upper']
            
        historia_dinamica.append(cap_dinamico + fees_dinamico - gas_gastado)

    # Resultados Finales
    total_estatico = val_estatico_hoy + fees_estatico
    total_dinamico = cap_dinamico + fees_dinamico - gas_gastado
    
    return {
        "estatica": {
            "total": total_estatico,
            "fees": fees_estatico,
            "dias_in": dias_rango_st,
            "rango": (p_min_st, p_max_st)
        },
        "dinamica": {
            "total": total_dinamico,
            "fees": fees_dinamico,
            "gas": gas_gastado,
            "rebalanceos": rebalanceos,
            "history": historia_dinamica
        }
    }

# --- UI PRINCIPAL ---

# 1. Generar Datos
df_market = generar_datos_mercado(precio_actual, volatilidad_anual, tendencia_anual, dias_analisis)

# 2. Ejecutar Simulación
res = simular_comparativa(df_market, capital_inicial, apr_estimado, gas_rebalanceo, bb_window, bb_std)

if res:
    # --- PANEL SUPERIOR: KPIs ---
    col1, col2, col3 = st.columns(3)
    
    est_neto = res['estatica']['total'] - capital_inicial
    dyn_neto = res['dinamica']['total'] - capital_inicial
    
    col1.metric("Resultado Estático", f"${res['estatica']['total']:.2f}", f"{est_neto:.2f} $")
    col2.metric("Resultado Dinámico", f"${res['dinamica']['total']:.2f}", f"{dyn_neto:.2f} $")
    
    diff = res['dinamica']['total'] - res['estatica']['total']
    winner = "Dinámica" if diff > 0 else "Estática"
    color = "normal" if diff > 0 else "off"
    col3.metric("Diferencia (Dyn - Stat)", f"${diff:.2f}", f"Ganador: {winner}")

    # --- GRÁFICO ---
    st.subheader("Análisis Visual de Rangos")
    
    # Calcular bandas para visualización
    df_viz = calcular_bollinger(df_market, bb_window, bb_std)
    
    fig = go.Figure()
    
    # Precio
    fig.add_trace(go.Scatter(x=df_viz.index, y=df_viz['close'], mode='lines', name='Precio', line=dict(color='white')))
    
    # Bandas Bollinger (Dinámicas)
    fig.add_trace(go.Scatter(x=df_viz.index, y=df_viz['upper'], mode='lines', name='Banda Sup', line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=df_viz.index, y=df_viz['lower'], mode='lines', name='Banda Inf', line=dict(width=0), fill='tonexty', fillcolor='rgba(0, 255, 255, 0.1)', showlegend=False))
    
    # Rango Estático (Fijo)
    r_min, r_max = res['estatica']['rango']
    fig.add_hline(y=r_max, line_dash="dash", line_color="red", annotation_text="Límite Sup. Estático")
    fig.add_hline(y=r_min, line_dash="dash", line_color="green", annotation_text="Límite Inf. Estático")

    fig.update_layout(template="plotly_dark", height=500, title="Evolución de Precio vs Rangos")
    st.plotly_chart(fig, use_container_width=True)

    # --- DETALLE ---
    st.subheader("Desglose de Rendimiento")
    c1, c2 = st.columns(2)
    
    with c1:
        st.info("🐢 Estrategia Estática (Hold Range)")
        st.write(f"**Días en Rango:** {res['estatica']['dias_in']} de {dias_analisis}")
        st.write(f"**Fees Generados:** ${res['estatica']['fees']:.2f}")
        st.write(f"**Rango Usado:** ${r_min:.2f} - ${r_max:.2f}")
        
    with c2:
        st.warning("🐇 Estrategia Dinámica (Auto-Rebalance)")
        st.write(f"**Veces Rebalanceado:** {res['dinamica']['rebalanceos']}")
        st.write(f"**Gas Gastado:** ${res['dinamica']['gas']:.2f}")
        st.write(f"**Fees Generados:** ${res['dinamica']['fees']:.2f}")
        if diff < 0:
            st.error(f"⚠️ El rebalanceo destruyó ${abs(diff):.2f} de valor vs quedarse quieto.")
        else:
            st.success(f"✅ El rebalanceo generó ${diff:.2f} extra.")
