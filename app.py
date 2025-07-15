# ... [import e setup invariati] ...
import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
import openrouteservice
import time
import os
import json
import math
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# === Configurazione pagina ===
st.set_page_config(
    page_title="Mappa Scuole - Analisi Distanze",
    page_icon="🏫",
    layout="wide"
)

# === Funzioni di supporto ===
@st.cache_data
def load_school_data():
    try:
        return pd.read_csv("mappa_scuole.csv")
    except FileNotFoundError:
        st.error("❌ File 'mappa_scuole.csv' non trovato!")
        return None

def determina_fascia_distanza(distanza):
    if distanza <= 10:
        return "0-10 km"
    elif distanza <= 20:
        return "10-20 km"
    else:
        return "20+ km"

def colore_per_fascia(fascia):
    return {
        "0-10 km": "green",
        "10-20 km": "orange",
        "20+ km": "red"
    }.get(fascia, "gray")

@st.cache_data
def get_route_data(start, end, comune, profile, api_key):
    try:
        client = openrouteservice.Client(key=api_key)
        coords = ((start[1], start[0]), (end[1], end[0]))  # lon, lat
        routes = client.directions(coords, profile=profile)
        geometry = routes['routes'][0]['geometry']
        summary = routes['routes'][0]['summary']
        decoded = openrouteservice.convert.decode_polyline(geometry)
        points = [(p[1], p[0]) for p in decoded['coordinates']]
        return {
            "points": points,
            "duration_min": round(summary['duration'] / 60, 1),
            "distance_km": round(summary['distance'] / 1000, 1)
        }
    except Exception as e:
        st.warning(f"⚠️ Errore nel calcolo del percorso per {comune}: {e}")
        return None

@st.cache_data
def geocodifica_indirizzo(indirizzo):
    geoloc = Nominatim(user_agent="streamlit-mappa-scuole")
    try:
        location = geoloc.geocode(indirizzo, timeout=10)
        if location:
            return location.latitude, location.longitude
        else:
            return None, None
    except GeocoderTimedOut:
        return None, None

# === Sidebar ===
st.sidebar.header("⚙️ Configurazioni")
st.sidebar.subheader("📍 Punto di partenza")
indirizzo_input = st.sidebar.text_input("Inserisci indirizzo o città", value="Brugherio")
lat, lon = geocodifica_indirizzo(indirizzo_input)
if lat is None or lon is None:
    st.sidebar.error("❌ Indirizzo non trovato, correggi e riprova.")
    st.stop()
start_coords = (lat, lon)

api_key = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjFhNDc0ZTg4OTY1MjRhZDM5M2ExNDIxNTIwNGUyMzQ3IiwiaCI6Im11cm11cjY0In0="

st.sidebar.subheader("🎯 Filtri")
fasce_disponibili = ["0-10 km", "10-20 km", "20+ km"]
fasce_selezionate = st.sidebar.multiselect("Fasce di distanza", fasce_disponibili, default=["0-10 km"])
mostra_posti_comune = st.sidebar.checkbox("Posti comune", value=False)
mostra_posti_montessori = st.sidebar.checkbox("Posti montessori", value=False)
mostra_posti_sostegno = st.sidebar.checkbox("Posti sostegno psicofisico", value=False)

# === Caricamento dati ===
mappe_scuole = load_school_data()
mappe_scuole.columns = mappe_scuole.columns.str.strip()

if mappe_scuole is None:
    st.error("❌ Impossibile caricare i dati delle scuole.")
    st.stop()

# === Applica fascia distanza in base a colonna 'distanza_km'
mappe_scuole['fascia_distanza'] = mappe_scuole['distanza_km'].apply(determina_fascia_distanza)

df_filtrato = mappe_scuole[mappe_scuole['fascia_distanza'].isin(fasce_selezionate)]
if mostra_posti_comune:
    df_filtrato = df_filtrato[df_filtrato['sum_COMUNE'] > 0]
if mostra_posti_montessori:
    df_filtrato = df_filtrato[df_filtrato['sum_CON METODO MONTESSORI'] > 0]
if mostra_posti_sostegno:
    df_filtrato = df_filtrato[df_filtrato['sum_SOSTEGNO PSICOFISICO'] > 0]

# === Tabs ===
tab1, tab2 = st.tabs(["🗺️ Mappa", "📋 Tabella"])

with tab1:
    st.subheader("🗺️ Mappa Interattiva")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("📊 Totale scuole", len(df_filtrato))
    with col2:
        if len(df_filtrato) > 0:
            st.metric("📏 Distanza media", f"{df_filtrato['distanza_km'].mean():.1f} km")
    with col3:
        st.metric("🏩 Posti Comune", len(df_filtrato[df_filtrato['sum_COMUNE'] > 0]))
    with col4:
        st.metric("🏫 Posti Montessori", len(df_filtrato[df_filtrato['sum_CON METODO MONTESSORI'] > 0]))
    with col5:
        st.metric("🧠 Posti Sostegno Psicofisico", len(df_filtrato[df_filtrato['sum_SOSTEGNO PSICOFISICO'] > 0]))

    mappa = folium.Map(location=start_coords, zoom_start=11, tiles="CartoDB positron")
    folium.Marker(location=start_coords, popup=f"Partenza: {indirizzo_input}", icon=folium.Icon(color='red', icon='home', prefix='fa')).add_to(mappa)

    if len(df_filtrato) > 0:
        progress_bar = st.progress(0)
        status_text = st.empty()

    for i, fascia in enumerate(fasce_selezionate):
        scuole_fascia = df_filtrato[df_filtrato['fascia_distanza'] == fascia]
        colore_fascia = colore_per_fascia(fascia)
        for idx, (_, row) in enumerate(scuole_fascia.iterrows()):
            lat_scuola, lon_scuola = row["latitudine"], row["longitudine"]
            nome = row["Denominazione"]
            comune = row["Comune"]
            indirizzo_scuola = row["Indirizzo"]
            distanza_km = row['distanza_km']

            status_text.text(f"Calcolo percorso {idx+1}/{len(scuole_fascia)} per {fascia}...")
            progress_bar.progress((idx + 1) / len(scuole_fascia))

            bici = get_route_data(start_coords, (lat_scuola, lon_scuola), comune, "cycling-regular", api_key)
            minuti_bici = bici['duration_min'] if bici else "?"
            km_bici = bici['distance_km'] if bici else "?"

            if bici:
                folium.PolyLine(bici['points'], color=colore_fascia, weight=3, opacity=0.7, popup=f"🚴 {nome}<br>⏱️ {minuti_bici} min<br>📏 {km_bici} km").add_to(mappa)

            gmaps_url = f"https://www.google.com/maps/dir/?api=1&origin={start_coords[0]},{start_coords[1]}&destination={lat_scuola},{lon_scuola}&travelmode=transit"

            popup_html = f"""
            <b>{nome}</b><br>
            📍 <i>{indirizzo_scuola}</i><br>
            📏 Distanza: {distanza_km:.1f} km<br>
            🚴 Bici: {minuti_bici} min / {km_bici} km<br>
            🏩 Posti Comune: {row['sum_COMUNE']}<br>
            🏫 Montessori: {row['sum_CON METODO MONTESSORI']}<br>
            🧠 Sostegno: {row['sum_SOSTEGNO PSICOFISICO']}<br>
            <a href="{gmaps_url}" target="_blank">🚌 Vai con i mezzi pubblici</a>
            """

            folium.Marker(
                location=(lat_scuola, lon_scuola),
                tooltip=f"{nome} ({comune}) - {fascia}",
                popup=folium.Popup(popup_html, max_width=350),
                icon=folium.Icon(color=colore_fascia, icon='graduation-cap', prefix='fa')
            ).add_to(mappa)

        time.sleep(4)

    if len(df_filtrato) > 0:
        progress_bar.empty()
        status_text.empty()

    st_data = st_folium(mappa, width=1200, height=700)

with tab2:
    st.subheader("📋 Dettagli Scuole")
    df_display = df_filtrato[['Denominazione', 'Comune', 'Indirizzo', 'distanza_km', 'km_bici',
                             'fascia_distanza', 'sum_COMUNE', 'sum_CON METODO MONTESSORI', 'sum_SOSTEGNO PSICOFISICO']].copy()
    df_display.columns = ['Nome', 'Comune', 'Indirizzo', 'Distanza (km)', 'Distanza_Bici (km)', 'Fascia', 'Posti_COMUNE', 'Posti_Montessori', 'Posti_Sostegno']
    df_display = df_display.sort_values('Distanza (km)')
    st.dataframe(df_display, use_container_width=True)

    st.subheader("📊 Statistiche per Fascia")
    stats_fascia = df_filtrato.groupby('fascia_distanza').agg({
        'Denominazione': 'count',
        'distanza_km': ['min', 'max', 'mean']
    }).round(2)

    for fascia in fasce_selezionate:
        if fascia in stats_fascia.index:
            count = stats_fascia.loc[fascia, ('Denominazione', 'count')]
            min_dist = stats_fascia.loc[fascia, ('distanza_km', 'min')]
            max_dist = stats_fascia.loc[fascia, ('distanza_km', 'max')]
            mean_dist = stats_fascia.loc[fascia, ('distanza_km', 'mean')]
            st.write(f"**fascia {fascia}**: {count} scuole (min: {min_dist}km, max: {max_dist}km, media: {mean_dist}km)")

    csv = df_display.to_csv(index=False)
    st.download_button(
        label="💾 Scarica dati CSV",
        data=csv,
        file_name=f"scuole_filtrate_{'-'.join(fasce_selezionate)}.csv",
        mime="text/csv"
    )

# === Legenda Sidebar ===
st.sidebar.subheader("🎨 Legenda")
st.sidebar.write("🔴 Punto di partenza")
st.sidebar.write("🟢 0-10 km")
st.sidebar.write("🟠 10-20 km")
st.sidebar.write("🔴 20+ km")

# === Footer ===
st.markdown("---")
st.markdown("🔧 Sviluppato da Li sen Hu e Davide Pedretti | 🗺️ Mappe powered by OpenRouteService")
