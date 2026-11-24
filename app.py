
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
st.caption("Global Economic Research | Version 2")

COUNTRIES = {
    "USA": "United States",
    "EMU": "Eurozone",
    "GBR": "United Kingdom",
    "JPN": "Japan",
    "AUS": "Australia",
    "CHN": "China"
}

# ==========================================
# DATA COLLECTION
# ==========================================

@st.cache_data(ttl=21600)
def fred_series(series_id):
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={series_id}"
    )
    response = requests.get(url, timeout=20)
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text))
    df.columns = ["Date", "CPI"]
    df["Date"] = pd.to_datetime(df["Date"])
    df["CPI"] = pd.to_numeric(df["CPI"], errors="coerce")

    return (
        df.dropna()
        .set_index("Date")["CPI"]
        .sort_index()
    )

@st.cache_data(ttl=21600)
def oecd_series(country):
    url = (
        "https://sdmx.oecd.org/public/rest/v1/data/"
        "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,"
        f"/{country}.M.N.CPI.PA._T.N.IX"
    )

    response = requests.get(
        url,
        params={"startPeriod": "2009-01"},
        headers={"Accept": "text/csv"},
        timeout=25
    )
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text))
    df["Date"] = pd.to_datetime(df["TIME_PERIOD"])
    df["CPI"] = pd.to_numeric(
        df["OBS_VALUE"], errors="coerce"
    )

    return (
        df.dropna()
        .set_index("Date")["CPI"]
        .sort_index()
    )

@st.cache_data(ttl=21600)
def load_monthly():
    sources = {
        "United States": ("USA", "CPIAUCNS"),
        "Eurozone": ("EA20", "CP0000EZ19M086NEST"),
        "United Kingdom": ("GBR", "GBRCPIALLMINMEI"),
        "Japan": ("JPN", "JPNCPALTT01IXNBM"),
        "Australia": ("AUS", None),
        "China": ("CHN", "CHNCPALTT01IXNBM")
    }

    frames = []
    errors = []

    for name, (code, fred_id) in sources.items():
        candidates = []

        try:
            series = oecd_series(code)
            if not series.empty:
                candidates.append((series, "OECD"))
        except Exception:
            pass

        if fred_id:
            try:
                series = fred_series(fred_id)
                if not series.empty:
                    candidates.append(
                        (series, f"FRED: {fred_id}")
                    )
            except Exception:
                pass

        if not candidates:
            errors.append(name)
            continue

        series, source = max(
            candidates,
            key=lambda item: item[0].index.max()
        )

        series.index = (
            series.index.to_period("M").to_timestamp()
        )
        series = series.groupby(level=0).last()
        series = series.asfreq("MS")

        data = pd.DataFrame({
            "CPI Index": series,
            "YoY": series.pct_change(
                12, fill_method=None
            ) * 100,
            "MoM": series.pct_change(
                1, fill_method=None
            ) * 100
        })

        data["Economy"] = name
        data["Source"] = source
        frames.append(
            data.rename_axis("Date").reset_index()
        )

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

    response = requests.get(url, timeout=25)
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

    with st.spinner("Retrieving global economic data..."):
        monthly, errors = load_monthly()

    for country in errors:
        st.warning(
            f"{country}: monthly data feed unavailable."
        )

    if not monthly.empty:
        latest = (
            monthly.dropna(subset=[mode])
            .sort_values("Date")
            .groupby("Economy")
            .tail(1)
        )

        latest = latest[
            latest["Economy"].isin(selected)
        ].copy()

        today = pd.Timestamp.now().normalize()

        latest["Age (days)"] = (
            today - latest["Date"]
        ).dt.days

        latest["Status"] = latest["Age (days)"].apply(
            lambda age: "Check freshness"
            if age > 75 else "Recent"
        )

        latest["Date"] = latest["Date"].dt.strftime(
            "%Y-%m"
        )

        st.subheader("Latest available observations")

        st.dataframe(
            latest[[
                "Economy", "Date", mode,
                "Status", "Source"
            ]].round(2),
            hide_index=True,
            use_container_width=True
        )

        cutoff = today - pd.DateOffset(years=years)

        visible = monthly[
            monthly["Economy"].isin(selected)
            & (monthly["Date"] >= cutoff)
        ]

        fig = px.line(
            visible.sort_values("Date"),
            x="Date",
            y=mode,
            color="Economy",
            title=f"Global Headline Inflation — {mode}",
            labels={mode: "Inflation (%)"}
        )

        fig.update_traces(connectgaps=False)
        fig.update_layout(hovermode="x unified")
        fig.add_hline(y=0, line_dash="dot")

        st.plotly_chart(
            fig, use_container_width=True
        )

        st.subheader("Monthly Inflation History")

        history = visible.pivot_table(
            index="Date",
            columns="Economy",
            values=mode
        ).sort_index(ascending=False)

        st.dataframe(
            history.round(2),
            use_container_width=True
        )

    st.caption(
        "Sources: OECD and FRED. Monthly indexes are "
        "not seasonally adjusted. MoM figures may "
        "reflect seasonal effects. Eurozone composition "
        "can differ by source. Australian monthly history "
        "may be shorter. Dates are observation months, "
        "not release dates."
    )

# ==========================================
# US CORE INFLATION
# ==========================================

with core_tab:
    st.header("United States — Core Inflation")

    try:
        headline = fred_series("CPIAUCSL")
        core = fred_series("CPILFESL")

        data = pd.concat(
            [headline, core], axis=1
        )
        data.columns = ["Headline CPI", "Core CPI"]
        data = data.asfreq("MS")

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
            changes.index.max()
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
        st.error(f"US CPI data unavailable: {error}")

    st.caption(
        "Source: FRED / BLS. Seasonally adjusted CPI. "
        "Core CPI excludes food and energy."
    )

# ==========================================
# ANNUAL INFLATION COMPARISON
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
st.caption(
    "Global Macro Research Dashboard | Version 2.0"
)
