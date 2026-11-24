
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from io import StringIO

st.set_page_config(
    page_title="Global Macro Dashboard",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Global Macro Dashboard")
st.caption("Global Economic Research | Version 2.1")

COUNTRIES = {
    "USA": "United States",
    "EMU": "Eurozone",
    "GBR": "United Kingdom",
    "JPN": "Japan",
    "AUS": "Australia",
    "CHN": "China"
}

# ==========================================
# DATA CONNECTIONS
# ==========================================

@st.cache_data(ttl=21600)
def fred_index(series_id):
    url = (
        "https://fred.stlouisfed.org/graph/"
        f"fredgraph.csv?id={series_id}"
    )
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text))
    dates = pd.to_datetime(df.iloc[:, 0])
    values = pd.to_numeric(
        df[series_id], errors="coerce"
    )

    series = pd.Series(
        values.to_numpy(), index=dates
    ).sort_index()

    return series.asfreq("MS")

@st.cache_data(ttl=21600)
def oecd_inflation(transformation):
    url = (
        "https://sdmx.oecd.org/public/rest/data/"
        "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/"
        "GBR+AUS+CHN.M.N.CPI.IX._T.N._Z"
    )

    response = requests.get(
        url,
        params={"startPeriod": "2009-01"},
        headers={"Accept": "text/csv"},
        timeout=60
    )

    response.raise_for_status()
    df = pd.read_csv(StringIO(response.text))

    periods = 12 if transformation == "GY" else 1
    frames = []

    for code in ["GBR", "AUS", "CHN"]:
        data = df[df["REF_AREA"] == code].copy()

        if data.empty:
            continue

        data["Date"] = pd.to_datetime(data["TIME_PERIOD"])
        data["CPI"] = pd.to_numeric(
            data["OBS_VALUE"], errors="coerce"
        )

        index = data.set_index("Date")["CPI"]
        index = index.sort_index().asfreq("MS")

        inflation = index.pct_change(
            periods, fill_method=None
        ) * 100

        result = pd.DataFrame({
            "Date": inflation.index,
            "Inflation (%)": inflation.values,
            "Economy": COUNTRIES[code],
            "Source": "OECD CPI Index"
        })

        frames.append(result.dropna())

    if not frames:
        raise ValueError("OECD CPI data unavailable")

    return pd.concat(frames, ignore_index=True)


@st.cache_data(ttl=21600)
def load_monthly(mode):
    frames = []
    errors = []

    periods = 12 if mode == "YoY" else 1
    transformation = "GY" if mode == "YoY" else "GP"

    try:
        frames.append(
            oecd_inflation(transformation)
        )
    except Exception as error:
        errors.append(f"OECD: {error}")

    fred_sources = {
        "United States": "CPIAUCNS",
        "Eurozone": "CP0000EZ19M086NEST"
    }

    for economy, series_id in fred_sources.items():
        try:
            index = fred_index(series_id)
            inflation = index.pct_change(
                periods, fill_method=None
            ) * 100

            data = pd.DataFrame({
                "Date": inflation.index,
                "Inflation (%)": inflation.values,
                "Economy": economy,
                "Source": f"FRED: {series_id}"
            })

            frames.append(data.dropna())

        except Exception as error:
            errors.append(f"{economy}: {error}")

    if not frames:
        return pd.DataFrame(), errors

    return pd.concat(
        frames, ignore_index=True
    ), errors


@st.cache_data(ttl=86400)
def load_annual():
    codes = ";".join(COUNTRIES.keys())

    url = (
        f"https://api.worldbank.org/v2/country/{codes}"
        "/indicator/FP.CPI.TOTL.ZG"
        "?format=json&date=1990:2026&per_page=1000"
    )

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    records = []

    for item in response.json()[1] or []:
        code = item["countryiso3code"]

        if code in COUNTRIES and item["value"] is not None:
            records.append({
                "Year": int(item["date"]),
                "Economy": COUNTRIES[code],
                "Inflation (%)": float(item["value"])
            })

    return pd.DataFrame(records)


# ==========================================
# DASHBOARD CONTROLS
# ==========================================

st.sidebar.header("Dashboard Controls")

selected = st.sidebar.multiselect(
    "Select economies",
    list(COUNTRIES.values()),
    default=list(COUNTRIES.values())
)

years = st.sidebar.slider(
    "Years of history", 2, 15, 5
)

if st.sidebar.button("Refresh data"):
    st.cache_data.clear()
    st.rerun()

monthly_tab, core_tab, annual_tab = st.tabs([
    "Monthly Inflation",
    "US Core Inflation",
    "Annual Comparison"
])


# ==========================================
# GLOBAL MONTHLY INFLATION
# ==========================================

with monthly_tab:

    st.header("Global Monthly Inflation")

    mode = st.radio(
        "Inflation measure",
        ["YoY", "MoM"],
        horizontal=True
    )

    with st.spinner("Retrieving inflation data..."):
        monthly, errors = load_monthly(mode)

    for error in errors:
        st.warning(error)

    if not monthly.empty:

        monthly = monthly[
            monthly["Economy"].isin(selected)
        ].copy()

        today = pd.Timestamp.now().normalize()

        latest = (
            monthly.sort_values("Date")
            .groupby("Economy")
            .tail(1)
            .copy()
        )

        latest["Age"] = (
            today - latest["Date"]
        ).dt.days

        latest["Status"] = latest["Age"].apply(
            lambda age: "Outdated"
            if age > 90 else "Recent"
        )

        latest["Observation"] = (
            latest["Date"].dt.strftime("%Y-%m")
        )

        available = set(latest["Economy"])

        for economy in selected:
            if economy not in available:
                st.warning(
                    f"{economy}: current monthly "
                    "data feed unavailable."
                )

        st.subheader("Latest Available Observations")

        st.dataframe(
            latest[[
                "Economy",
                "Observation",
                "Inflation (%)",
                "Status",
                "Source"
            ]].round(2),
            hide_index=True,
            use_container_width=True
        )

        cutoff = today - pd.DateOffset(years=years)

        visible = monthly[
            monthly["Date"] >= cutoff
        ]

        fig = px.line(
            visible.sort_values("Date"),
            x="Date",
            y="Inflation (%)",
            color="Economy",
            title=f"Global Headline Inflation — {mode}"
        )

        fig.update_layout(hovermode="x unified")
        fig.update_traces(connectgaps=False)
        fig.add_hline(y=0, line_dash="dot")

        st.plotly_chart(
            fig, use_container_width=True
        )

        st.subheader("Monthly Inflation History")

        history = visible.pivot_table(
            index="Date",
            columns="Economy",
            values="Inflation (%)"
        ).sort_index(ascending=False)

        st.dataframe(
            history.round(2),
            use_container_width=True
        )

    else:
        st.warning("Monthly inflation data unavailable.")

    st.caption(
        "Sources: OECD, FRED. Observation dates are "
        "not release dates. Monthly changes may "
        "reflect seasonal effects. Eurozone data "
        "uses HICP. Australian monthly history "
        "may have limited coverage."
    )


# ==========================================
# US CORE INFLATION
# ==========================================

with core_tab:

    st.header("United States — Core Inflation")

    try:
        headline = fred_index("CPIAUCSL")
        core = fred_index("CPILFESL")

        data = pd.concat(
            [headline, core], axis=1
        )

        data.columns = ["Headline CPI", "Core CPI"]

        measure = st.radio(
            "US inflation measure",
            ["YoY", "MoM"],
            horizontal=True,
            key="us_measure"
        )

        periods = 12 if measure == "YoY" else 1

        changes = data.pct_change(
            periods, fill_method=None
        ) * 100

        recent = changes.dropna()

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Headline CPI",
            f"{recent.iloc[-1, 0]:.2f}%"
        )

        col2.metric(
            "Core CPI",
            f"{recent.iloc[-1, 1]:.2f}%"
        )

        col3.metric(
            "Observation",
            recent.index[-1].strftime("%b %Y")
        )

        cutoff = (
            recent.index.max()
            - pd.DateOffset(years=years)
        )

        visible = changes.loc[
            changes.index >= cutoff
        ]

        fig = px.line(
            visible,
            title=f"US Headline vs Core CPI — {measure}",
            labels={"value": "Inflation (%)"}
        )

        st.plotly_chart(
            fig, use_container_width=True
        )

        st.dataframe(
            recent.tail(12).round(2),
            use_container_width=True
        )

    except Exception as error:
        st.error(f"US CPI unavailable: {error}")

    st.caption(
        "Source: FRED / BLS. Seasonally adjusted. "
        "Core CPI excludes food and energy."
    )


# ==========================================
# ANNUAL INFLATION
# ==========================================

with annual_tab:

    st.header("Annual Global Inflation Comparison")

    try:
        annual = load_annual()

        annual = annual[
            annual["Economy"].isin(selected)
        ]

        fig = px.line(
            annual.sort_values("Year"),
            x="Year",
            y="Inflation (%)",
            color="Economy",
            markers=True
        )

        st.plotly_chart(
            fig, use_container_width=True
        )

        latest = (
            annual.sort_values("Year")
            .groupby("Economy")
            .tail(1)
        )

        st.dataframe(
            latest.round(2),
            hide_index=True,
            use_container_width=True
        )

    except Exception as error:
        st.error(f"Annual data unavailable: {error}")

    st.caption(
        "Source: World Bank, FP.CPI.TOTL.ZG. "
        "Annual observations may be published with a lag."
    )

st.divider()
st.caption("Global Macro Research Dashboard | Version 2.1")
