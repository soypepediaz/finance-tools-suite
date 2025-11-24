import streamlit as st

st.set_page_config(
    page_title="Mucho Finance Tools",
    page_icon="🚀",
    layout="wide"
)

# CSS para ocultar marcas
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- CONTENIDO PRINCIPAL ---
col1, col2 = st.columns([1, 2])

with col1:
    st.image("https://placehold.co/400x400/PNG?text=Mucho+Finance", use_container_width=True)

with col2:
    st.title("Bienvenido a la Suite de Herramientas DeFi")
    st.markdown("### Tu centro de comando para operaciones On-Chain.")
    st.markdown("""
    Aquí encontrarás calculadoras, simuladores y escáneres desarrollados por **Campamento DeFi** para ayudarte a tomar mejores decisiones de inversión.
    """)

st.divider()

st.subheader("🛠️ Herramientas Disponibles")

c_loop, c_dca, c_futuro = st.columns(3)

with c_loop:
    st.info("🔄 **Looping Master**")
    st.markdown("Calculadora de liquidación y escáner de salud para posiciones en Aave.")
    st.markdown("👉 *Selecciónalo en el menú lateral.*")

with c_dca:
    st.success("💰 **Simulador DCA**")
    st.markdown("Analiza estrategias de Dollar Cost Average apalancado sobre Bitcoin.")
    st.markdown("👉 *Selecciónalo en el menú lateral.*")

with c_futuro:
    st.warning("🚧 **Próximamente**")
    st.markdown("Estamos desarrollando nuevas herramientas de Impermanent Loss y Farming.")

st.divider()
st.caption("© 2024 Mucho Finance - Herramientas educativas.")