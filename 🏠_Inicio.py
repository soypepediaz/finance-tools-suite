import streamlit as st

# Configuración de la página: Colapsamos el menú lateral por defecto
st.set_page_config(
    page_title="Campamento DeFi Tools",
    page_icon="🏕️",
    layout="wide",
    initial_sidebar_state="collapsed" 
)

# CSS para ocultar marcas y limpiar
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            
            /* Opcional: Si quieres ocultar totalmente la barra lateral, descomenta esto: */
            /* [data-testid="stSidebar"] {display: none;} */
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- ESTRUCTURA PRINCIPAL (2 COLUMNAS) ---
col_img, col_text = st.columns([1, 2], gap="large")

with col_img:
    # Tu mascota a la izquierda
    try:
        st.image("mascota.png", use_container_width=True)
    except:
        st.warning("⚠️ Sube la imagen 'mascota.png' al repositorio.")

with col_text:
    st.title("Bienvenido al Campamento DeFi")
    st.markdown("### Tu centro de comando para operaciones On-Chain.")
    st.markdown("""
    Aquí tienes las herramientas profesionales diseñadas para gestionar tu riesgo y optimizar tus rendimientos.
    
    **Selecciona una herramienta para empezar:**
    """)
    
    st.write("") # Espacio separador
    
    # --- MENÚ DE APPS INTEGRADO (Debajo del texto, junto a la mascota) ---
    
    c_loop, c_dca = st.columns(2)
    
    with c_loop:
        with st.container(border=True):
            st.markdown("#### 🔄 Looping Master")
            st.caption("Aave: Liquidaciones y Escáner de Salud.")
            # ENLACE DE NAVEGACIÓN DIRECTO
            # Asegúrate de que el nombre del archivo en 'pages/' coincide EXACTAMENTE
            st.page_link("pages/01_🔄_Looping.py", label="Abrir Herramienta", icon="🚀", use_container_width=True)
            
    with c_dca:
        with st.container(border=True):
            st.markdown("#### 💰 Simulador DCA")
            st.caption("Bitcoin: Estrategia de Acumulación.")
            # ENLACE DE NAVEGACIÓN DIRECTO
            st.page_link("pages/02_💰_DCA_Bitcoin.py", label="Abrir Herramienta", icon="📈", use_container_width=True)

    # Aviso de próximas herramientas
    st.info("🚧 **Próximamente:** Calculadora de Impermanent Loss y Buscador de Yields.")

st.divider()
st.caption("© 2025 Campamento DeFi - Herramientas educativas. DYOR.")
