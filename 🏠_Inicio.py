import streamlit as st

# Configuración de la página
st.set_page_config(
    page_title="Looping Master - Campamento DeFi",
    page_icon="mascota.png", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS para ocultar marcas y limpiar la interfaz
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- FILA 1: CABECERA (Mascota + Bienvenida) ---
# Ajustamos la proporción a [1, 3] para que la columna de la imagen (izquierda)
# sea más estrecha y, por tanto, la mascota se vea más pequeña.
col_img, col_text = st.columns([1, 3], gap="large")

with col_img:
    try:
        st.image("mascota.png", use_container_width=True)
    except:
        st.warning("⚠️ Falta 'mascota.png'")

with col_text:
    st.title("Bienvenido al Campamento DeFi")
    st.markdown("### Tu centro de comando para operaciones On-Chain.")
    st.markdown("""
    Aquí tienes las herramientas profesionales diseñadas para gestionar tu riesgo y optimizar tus rendimientos.
    
    **Selecciona una herramienta para empezar:**
    """)

st.write("") # Espacio separador vertical

# --- FILA 2: MENÚ DE HERRAMIENTAS (4 Columnas) ---
# Ahora estas columnas ocupan todo el ancho, dando más espacio a cada tarjeta
c_loop, c_dca, c_pool, c_hunter = st.columns(4)

# Columna 1: Looping
with c_loop:
    with st.container(border=True):
        st.markdown("#### 🔄 Looping Master")
        st.caption("Aave: Liquidaciones y Salud.")
        st.page_link("pages/01_🔄_Looping.py", label="Abrir Herramienta", icon="🚀", use_container_width=True)
        
# Columna 2: DCA
with c_dca:
    with st.container(border=True):
        st.markdown("#### 💰 Simulador DCA")
        st.caption("Bitcoin: Estrategia Acumulación.")
        st.page_link("pages/02_💰_DCA_Bitcoin.py", label="Abrir Herramienta", icon="📈", use_container_width=True)

# Columna 3: Optimizador Pools
with c_pool:
    with st.container(border=True):
        st.markdown("#### 💧 Optimizador Pools")
        st.caption("Uniswap V3: Gestión de Liquidez.")
        st.page_link("pages/03_💧_Optimizador_Pools.py", label="Abrir Herramienta", icon="🦄", use_container_width=True)

# Columna 4: Cazador de Pools (NUEVA)
with c_hunter:
    with st.container(border=True):
        st.markdown("#### 🏹 Cazador Pools")
        st.caption("DeFi: Oportunidades de Yield.")
        # Usamos link_button para URLs externas manteniendo la estética
        st.link_button("Abrir Herramienta", url="https://lab.campamentodefi.com/Cazador_Pools", icon="🎯", use_container_width=True)

# Aviso de próximas herramientas
st.write("")
st.info("🚧 **Próximamente:** Más cosicas buenas para ayudarte a tomar mejores decisiones.")

st.divider()
# ==============================================================================
#  GLOBAL FOOTER (Pie de página común para todas las pestañas)
# ==============================================================================
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        Desarrollado con ❤️ por <a href='https://lab.campamentodefi.com' target='_blank' style='text-decoration: none; color: #FF4B4B;'>Campamento DeFi</a>, 
        el lugar de reunión de los seres <a href='https://link.soypepediaz.com/labinconfiscable' target='_blank' style='text-decoration: none; color: #FF4B4B;'>Inconfiscables</a>
    </div>
    """, 
    unsafe_allow_html=True
)
