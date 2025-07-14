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

# === Configurazione pagina ===
st.set_page_config(
    page_title="Mappa Scuole - Analisi Distanze",
    page_icon="🏫",
    layout="wide"
)

# === Funzioni di supporto ===
@st.cache_data
def load_school_data():
    """Carica i dati delle scuole dal CSV"""
    try:
        return pd.read_csv("mappa_scuole.csv")
    except FileNotFoundError:
        st.error("❌ File 'mappa_scuole.csv' non trovato!")
        return None

def calcola_distanza_euclidea(lat1, lon1, lat2, lon2):
    """Calcola la distanza euclidea tra due punti in km usando la formula di Haversine"""
    R = 6371  # Raggio della Terra in km
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

def determina_fascia_distanza(distanza_km):
    """Determina la fascia di distanza in base ai km"""
    if distanza_km <= 10:
        return "0-10 km"
    elif distanza_km <= 20:
        return "10-20 km"
    else:
        return "20+ km"

def colore_per_fascia(fascia):
    colori = {
        "0-10 km": "green",
        "10-20 km": "orange",
        "20+ km": "red"
    }
    return colori.get(fascia, "gray")

@st.cache_data
def get_route_data(start, end, comune, profile, api_key):
    """Ottiene i dati del percorso da ORS con cache"""
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

# === Interfaccia utente ===
st.title("🏫 Mappa Scuole - Analisi Distanze")
st.write("Visualizza le scuole nelle vicinanze con distanze e percorsi ciclabili")

# === Sidebar per configurazioni ===
st.sidebar.header("⚙️ Configurazioni")

# Coordinate di partenza
st.sidebar.subheader("📍 Punto di partenza")
start_lat = st.sidebar.number_input("Latitudine", value=45.5586, format="%.4f")
start_lon = st.sidebar.number_input("Longitudine", value=9.3081, format="%.4f")
start_coords = (start_lat, start_lon)

# API Key ORS
st.sidebar.subheader("🔑 API OpenRouteService")
api_key = st.sidebar.text_input(
    "API Key ORS",
    value="eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjFhNDc0ZTg4OTY1MjRhZDM5M2ExNDIxNTIwNGUyMzQ3IiwiaCI6Im11cm11cjY0In0=",
    type="password"
)

# Filtri
st.sidebar.subheader("🎯 Filtri")
fasce_disponibili = ["0-10 km", "10-20 km", "20+ km"]
fasce_selezionate = st.sidebar.multiselect(
    "Fasce di distanza",
    fasce_disponibili,
    default=["0-10 km"]
)

mostra_percorsi = st.sidebar.checkbox("Mostra percorsi ciclabili", value=True)
mostra_solo_montessori = st.sidebar.checkbox("Solo scuole Montessori", value=False)

# === Caricamento dati ===
mappe_scuole = load_school_data()

if mappe_scuole is not None:
    # === Calcolo distanze ===
    with st.spinner("🔄 Calcolo distanze euclidee..."):
        mappe_scuole['distanza_euclidea_km'] = mappe_scuole.apply(
            lambda row: calcola_distanza_euclidea(
                start_coords[0], start_coords[1], 
                row['latitudine'], row['longitudine']
            ), axis=1
        )
        
        mappe_scuole['fascia_distanza'] = mappe_scuole['distanza_euclidea_km'].apply(determina_fascia_distanza)
    
    # === Filtro dati ===
    df_filtrato = mappe_scuole[mappe_scuole['fascia_distanza'].isin(fasce_selezionate)]
    
    if mostra_solo_montessori:
        df_filtrato = df_filtrato[df_filtrato['sum_CON METODO MONTESSORI'] == 'S']
    
    # === Statistiche ===
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("📊 Totale scuole", len(df_filtrato))
    
    with col2:
        if len(df_filtrato) > 0:
            st.metric("📏 Distanza media", f"{df_filtrato['distanza_euclidea_km'].mean():.1f} km")
    
    with col3:
        if len(df_filtrato) > 0:
            st.metric("🏫 Scuole Montessori", len(df_filtrato[df_filtrato['sum_CON METODO MONTESSORI'] == 'S']))
    
    # === Creazione mappa ===
    st.subheader("🗺️ Mappa Interattiva")
    
    # Crea mappa base
    mappa = folium.Map(location=start_coords, zoom_start=11, tiles="CartoDB positron")
    
    # Marker partenza
    folium.Marker(
        location=start_coords,
        popup="Partenza: Brugherio",
        icon=folium.Icon(color='red', icon='home', prefix='fa')
    ).add_to(mappa)
    
    # Progress bar per percorsi
    if mostra_percorsi and len(df_filtrato) > 0:
        progress_bar = st.progress(0)
        status_text = st.empty()
    
    # === Aggiunta scuole per fascia ===
    for i, fascia in enumerate(fasce_selezionate):
        scuole_fascia = df_filtrato[df_filtrato['fascia_distanza'] == fascia]
        
        if len(scuole_fascia) > 0:
            colore_fascia = colore_per_fascia(fascia)
            
            for idx, (_, row) in enumerate(scuole_fascia.iterrows()):
                lat, lon = row["latitudine"], row["longitudine"]
                nome = row["Denominazione"]
                comune = row["Comune"]
                indirizzo = row["Indirizzo"]
                distanza_euclidea = row['distanza_euclidea_km']
                
                # Calcola percorso bici se richiesto
                minuti_bici = "?"
                km_bici = "?"
                
                if mostra_percorsi and api_key:
                    if mostra_percorsi:
                        status_text.text(f"Calcolo percorso {idx+1}/{len(scuole_fascia)} per {fascia}...")
                        progress_bar.progress((idx + 1) / len(scuole_fascia))
                    
                    bici = get_route_data(start_coords, (lat, lon), comune, "cycling-regular", api_key)
                    if bici:
                        minuti_bici = bici['duration_min']
                        km_bici = bici['distance_km']
                        
                        # Aggiungi percorso alla mappa
                        folium.PolyLine(
                            bici['points'], 
                            color=colore_fascia, 
                            weight=3, 
                            opacity=0.7,
                            popup=f"🚴 {nome}<br>⏱️ {minuti_bici} min<br>📏 {km_bici} km"
                        ).add_to(mappa)
                
                # Link Google Maps
                gmaps_url = (
                    f"https://www.google.com/maps/dir/?api=1"
                    f"&origin={start_coords[0]},{start_coords[1]}"
                    f"&destination={lat},{lon}"
                    f"&travelmode=transit"
                )
                
                # Popup scuola
                popup_html = f"""
                <b>{nome}</b><br>
                📍 <i>{indirizzo}</i><br>
                📏 Distanza diretta: {distanza_euclidea:.1f} km<br>
                🚴 Bici: {minuti_bici} min / {km_bici} km<br>
                🏘️ Posti_Comune: {row['sum_COMUNE']}<br>
                🏫 Posti_Montessori: {row['sum_CON METODO MONTESSORI']}<br>
                🧠 Posti_Sostegno psicofisico: {row['sum_SOSTEGNO PSICOFISICO']}<br>
                <a href="{gmaps_url}" target="_blank">🚌 Vai con i mezzi pubblici</a>
                """
                
                # Marker scuola
                folium.Marker(
                    location=(lat, lon),
                    tooltip=f"{nome} ({comune}) - {fascia}",
                    popup=folium.Popup(popup_html, max_width=350),
                    icon=folium.Icon(color=colore_fascia, icon='graduation-cap', prefix='fa')
                ).add_to(mappa)
    
    # Rimuovi progress bar
    if mostra_percorsi and len(df_filtrato) > 0:
        progress_bar.empty()
        status_text.empty()
    
    # === Visualizza mappa ===
    map_data = st_folium(mappa, width=1200, height=600)
    
    # === Tabella dati ===
    st.subheader("📋 Dettagli Scuole")
    
    # Prepara dati per tabella
    df_display = df_filtrato[['Denominazione', 'Comune', 'Indirizzo', 'distanza_euclidea_km', 
                             'fascia_distanza', 'sum_COMUNE', 'sum_CON METODO MONTESSORI', 'sum_SOSTEGNO PSICOFISICO']].copy()
    
    df_display.columns = ['Nome', 'Comune', 'Indirizzo', 'Distanza (km)', 'Fascia', 'Posti_COMUNE', 'Posti_Montessori', 'Posti_Sostegno']
    df_display = df_display.sort_values('Distanza (km)')
    
    st.dataframe(df_display, use_container_width=True)
    
    # === Statistiche dettagliate ===
    st.subheader("📊 Statistiche per Fascia")
    
    stats_fascia = df_filtrato.groupby('fascia_distanza').agg({
        'Denominazione': 'count',
        'distanza_euclidea_km': ['min', 'max', 'mean']
    }).round(2)
    
    for fascia in fasce_selezionate:
        if fascia in stats_fascia.index:
            count = stats_fascia.loc[fascia, ('Denominazione', 'count')]
            min_dist = stats_fascia.loc[fascia, ('distanza_euclidea_km', 'min')]
            max_dist = stats_fascia.loc[fascia, ('distanza_euclidea_km', 'max')]
            mean_dist = stats_fascia.loc[fascia, ('distanza_euclidea_km', 'mean')]
            
            colore = colore_per_fascia(fascia)
            st.write(f"**{fascia}** ({colore}): {count} scuole (min: {min_dist}km, max: {max_dist}km, media: {mean_dist}km)")
    
    # === Legenda ===
    st.sidebar.subheader("🎨 Legenda")
    st.sidebar.write("🔴 Punto di partenza")
    st.sidebar.write("🟢 0-10 km")
    st.sidebar.write("🟠 10-20 km") 
    st.sidebar.write("🔴 20+ km")
    
    # === Download CSV ===
    csv = df_display.to_csv(index=False)
    st.download_button(
        label="💾 Scarica dati CSV",
        data=csv,
        file_name=f"scuole_filtrate_{'-'.join(fasce_selezionate)}.csv",
        mime="text/csv"
    )

else:
    st.error("❌ Impossibile caricare i dati delle scuole. Assicurati che il file 'mappa_scuole.csv' sia presente nella directory dell'app.")
    st.info("💡 Il file dovrebbe contenere le colonne: Denominazione, Comune, Indirizzo, latitudine, longitudine, sum_CON METODO MONTESSORI, sum_SOSTEGNO PSICOFISICO")

# === Footer ===
st.markdown("---")
st.markdown("🔧 Sviluppato con Streamlit | 🗺️ Mappe powered by OpenRouteService")
