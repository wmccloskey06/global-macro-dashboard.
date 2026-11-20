
import streamlit as st
import pandas as pd
import requests
import plotly.express as px

st.set_page_config(
    page_title="Global Macro Dashboard",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Global Macro Dashboard")
st.caption("Global economic research | Version 1")

countries = {
    "USA": "United States",
    "EMU": "Eurozone",
    "JPN": "Japan",
    "GBR": "United Kingdom",
    "AUS": "Australia",
    "CHN": "China"
}

@st.cache_data(ttl=86400)
def load_inflation():
    codes = ";".join(countries.keys())
    url = (
        f"https://api.worldbank.org/v2/country/{codes}"
        "/indicator/FP.CPI.TOTL.ZG"
        "?format=json&date=2010:2026&per_page=1000"
    )

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    result = response.json()

    if not isinstance(result, list) or len(result) < 2:
        raise ValueError("Unexpected World Bank response")

    records = []
    for item in result[1] or []:
        code = item.get("countryiso3code")
        value = item.get("value")
        if code in countries and value is not None:
            records.append({
                "Year": int(item["date"]),
                "Economy": countries[code],
                "Inflation (%)": float(value)
            })

    if not records:
        raise ValueError("No inflation observations returned")

    return pd.DataFrame(records)

try:
    df = load_inflation()
except Exception as error:
    st.error(f"Unable to retrieve inflation data: {error}")
    st.stop()

st.sidebar.header("Dashboard controls")

selected = st.sidebar.multiselect(
    "Select economies",
    options=list(countries.values()),
    default=list(countries.values())
)

start_year = st.sidebar.slider(
    "Starting year",
    min_value=2010,
    max_value=2026,
    value=2015
)

filtered = df[
    df["Economy"].isin(selected)
    & (df["Year"] >= start_year)
]

st.subheader("Global Inflation Comparison")

if filtered.empty:
    st.warning("Select at least one economy.")
else:
    fig = px.line(
        filtered.sort_values("Year"),
        x="Year",
        y="Inflation (%)",
        color="Economy",
        markers=True,
        title="Annual Consumer Price Inflation"
    )
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Latest Available Observations")

    latest = (
        filtered.sort_values("Year")
        .groupby("Economy")
        .tail(1)
        .sort_values("Economy")
    )

    st.dataframe(
        latest[["Economy", "Year", "Inflation (%)"]],
        hide_index=True,
        use_container_width=True
    )

st.caption(
    "Source: World Bank, FP.CPI.TOTL.ZG. "
    "Annual data; observations may be published with a lag. "
    "Data is cached for up to 24 hours."
)
