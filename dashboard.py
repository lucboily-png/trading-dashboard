
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pytz
import streamlit.components.v1 as components

from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
from oandapyV20.endpoints.transactions import TransactionList
from streamlit_autorefresh import st_autorefresh


# =========================================================
# CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="Trading Monitor V2 - Smart Money",
    layout="wide"
)

st_autorefresh(interval=60 * 1000, key="refresh")

NY_TZ = pytz.timezone("America/New_York")

# OANDA : utiliser les Secrets Streamlit
try:
    ACCESS_TOKEN = st.secrets["OANDA_ACCESS_TOKEN"]
    ACCOUNT_ID = st.secrets["OANDA_ACCOUNT_ID"]
    client = API(access_token=ACCESS_TOKEN, environment="practice")
except Exception:
    st.error("Configuration OANDA manquante dans les Secrets Streamlit.")
    st.stop()


# =========================================================
# INSTRUMENTS
# =========================================================

PAIRS = {
    "XAU/USD - Gold": "XAU_USD",
    "SPX500 - S&P 500": "SPX500_USD"
}

TIMEFRAME = "M30"
CANDLE_COUNT = 300


# =========================================================
# ALERTES VOCALES
# =========================================================

VOICE_STRONG_BULL = (
    "https://cdn.pixabay.com/download/audio/2023/03/22/"
    "audio_7e47f7d88e.mp3?filename=alert-female-strong-bullish.mp3"
)

VOICE_WEAK_BULL = (
    "https://cdn.pixabay.com/download/audio/2023/03/22/"
    "audio_45ad3f98f1.mp3?filename=alert-female-weak-bullish.mp3"
)

VOICE_STRONG_BEAR = (
    "https://cdn.pixabay.com/download/audio/2023/03/22/"
    "audio_2ac24c3bd2.mp3?filename=alert-female-strong-bearish.mp3"
)

VOICE_WEAK_BEAR = (
    "https://cdn.pixabay.com/download/audio/2023/03/22/"
    "audio_e4df2d3f17.mp3?filename=alert-female-weak-bearish.mp3"
)


def play_voice_alert(url):
    components.html(
        f"""
        <script>
            var audio = new Audio("{url}");
            audio.volume = 1.0;
            audio.play().catch(function(e) {{
                console.log("Audio blocked by browser");
            }});
        </script>
        """,
        height=0
    )


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.title("Trading Monitor V2")

st.sidebar.markdown("### Configuration")

mute_alerts = st.sidebar.checkbox(
    "Mute alerts",
    value=False
)

show_ema = st.sidebar.checkbox(
    "Afficher EMA 50 / 100 / 200",
    value=True
)

show_fvg = st.sidebar.checkbox(
    "Afficher les Fair Value Gaps",
    value=True
)

show_structure = st.sidebar.checkbox(
    "Afficher BOS / CHoCH",
    value=True
)

st.sidebar.markdown("---")

st.sidebar.subheader("Calculateur gains / pertes")

capital = st.sidebar.number_input(
    "Capital ($)",
    min_value=0.0,
    value=500.0
)

risk_percent = st.sidebar.number_input(
    "Risque (%)",
    min_value=0.0,
    value=2.0
)

rr = st.sidebar.number_input(
    "Risk / Reward",
    min_value=0.1,
    value=3.0
)

risk_amount = capital * risk_percent / 100
potential_gain = risk_amount * rr

st.sidebar.write(f"Risque par trade : **${risk_amount:.2f}**")
st.sidebar.write(f"Gain potentiel : **${potential_gain:.2f}**")

st.sidebar.markdown("---")
st.sidebar.caption("Smart Money Lite | M30")


# =========================================================
# RÉCUPÉRATION DES DONNÉES OANDA
# =========================================================

@st.cache_data(ttl=45)
def get_data(pair, timeframe="M30", count=300):

    request = instruments.InstrumentsCandles(
        instrument=pair,
        params={
            "count": count,
            "granularity": timeframe,
            "price": "M"
        }
    )

    client.request(request)

    candles = request.response["candles"]

    # Garder uniquement les chandeliers terminés
    candles = [c for c in candles if c.get("complete", False)]

    df = pd.DataFrame([
        {
            "time": c["time"],
            "open": float(c["mid"]["o"]),
            "high": float(c["mid"]["h"]),
            "low": float(c["mid"]["l"]),
            "close": float(c["mid"]["c"]),
            "volume": int(c.get("volume", 0))
        }
        for c in candles
    ])

    if df.empty:
        return df

    df["time"] = pd.to_datetime(df["time"], utc=True)
    df["time"] = df["time"].dt.tz_convert("America/New_York")

    return df


def get_current_price(pair):

    try:
        request = instruments.InstrumentsCandles(
            instrument=pair,
            params={
                "count": 1,
                "granularity": "M1",
                "price": "M"
            }
        )

        client.request(request)

        candles = request.response["candles"]

        return float(candles[-1]["mid"]["c"])

    except Exception:
        return None


# =========================================================
# INDICATEURS EMA
# =========================================================

def calculate_indicators(df):

    df = df.copy()

    df["EMA50"] = df["close"].ewm(
        span=50, adjust=False
    ).mean()

    df["EMA100"] = df["close"].ewm(
        span=100, adjust=False
    ).mean()

    df["EMA200"] = df["close"].ewm(
        span=200, adjust=False
    ).mean()

    return df


# =========================================================
# SMART MONEY : BOS / CHoCH
# =========================================================

def detect_market_structure(df):

    df = df.copy()

    # Swing highs et lows confirmés
    window = 5

    rolling_high = df["high"].rolling(
        window, center=True
    ).max()

    rolling_low = df["low"].rolling(
        window, center=True
    ).min()

    swing_high = (
        df["high"].sub(rolling_high).abs() < 0.0000001
    )

    swing_low = (
        df["low"].sub(rolling_low).abs() < 0.0000001
    )

    df["SwingHigh"] = swing_high
    df["SwingLow"] = swing_low

    df["Structure"] = ""
    df["EventPrice"] = None

    last_high = None
    last_low = None

    last_broken_high = None
    last_broken_low = None

    direction = 0

    events = []

    for i in range(2, len(df)):

        # Les pivots sont confirmés après deux chandeliers
        pivot_index = i - 2

        if swing_high.iloc[pivot_index]:
            last_high = df["high"].iloc[pivot_index]

        if swing_low.iloc[pivot_index]:
            last_low = df["low"].iloc[pivot_index]

        close_now = df["close"].iloc[i]
        close_prev = df["close"].iloc[i - 1]

        event = None
        event_price = None

        # Cassure d'un sommet
        if (
            last_high is not None
            and last_broken_high != pivot_index
            and close_prev <= last_high
            and close_now > last_high
        ):

            event = "BOS" if direction >= 0 else "CHoCH"
            event_price = last_high

            direction = 1
            last_broken_high = pivot_index

        # Cassure d'un creux
        elif (
            last_low is not None
            and last_broken_low != pivot_index
            and close_prev >= last_low
            and close_now < last_low
        ):

            event = "BOS" if direction <= 0 else "CHoCH"
            event_price = last_low

            direction = -1
            last_broken_low = pivot_index

        if event:

            df.loc[df.index[i], "Structure"] = event
            df.loc[df.index[i], "EventPrice"] = event_price

            events.append({
                "time": df["time"].iloc[i],
                "type": event,
                "direction": direction,
                "price": event_price
            })

    return df, events


# =========================================================
# SMART MONEY : FAIR VALUE GAPS
# =========================================================

def detect_fvg(df):

    gaps = []

    for i in range(2, len(df)):

        # FVG haussier
        if df["low"].iloc[i] > df["high"].iloc[i - 2]:

            gaps.append({
                "time": df["time"].iloc[i - 2],
                "end": df["time"].iloc[i],
                "type": "Bullish FVG",
                "top": df["low"].iloc[i],
                "bottom": df["high"].iloc[i - 2]
            })

        # FVG baissier
        elif df["high"].iloc[i] < df["low"].iloc[i - 2]:

            gaps.append({
                "time": df["time"].iloc[i - 2],
                "end": df["time"].iloc[i],
                "type": "Bearish FVG",
                "top": df["low"].iloc[i - 2],
                "bottom": df["high"].iloc[i]
            })

    return gaps


# =========================================================
# CRÉATION DU GRAPHIQUE
# =========================================================

def create_chart(df, gaps, events):

    fig = go.Figure()

    # Chandeliers japonais
    fig.add_trace(
        go.Candlestick(
            x=df["time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Price",
            increasing_line_color="#00C853",
            decreasing_line_color="#FF5252"
        )
    )

    # EMA
    if show_ema:

        fig.add_trace(go.Scatter(
            x=df["time"],
            y=df["EMA50"],
            name="EMA 50",
            line=dict(color="blue", width=1.5)
        ))

        fig.add_trace(go.Scatter(
            x=df["time"],
            y=df["EMA100"],
            name="EMA 100",
            line=dict(color="gray", width=1.5)
        ))

        fig.add_trace(go.Scatter(
            x=df["time"],
            y=df["EMA200"],
            name="EMA 200",
            line=dict(color="orange", width=2)
        ))

    # Fair Value Gaps
    if show_fvg:

        # Afficher les 8 dernières zones
        for gap in gaps[-8:]:

            color = (
                "rgba(0,200,83,0.16)"
                if gap["type"] == "Bullish FVG"
                else "rgba(255,82,82,0.16)"
            )

            fig.add_shape(
                type="rect",
                x0=gap["time"],
                x1=df["time"].iloc[-1] + pd.Timedelta(minutes=30),
                y0=gap["bottom"],
                y1=gap["top"],
                fillcolor=color,
                line=dict(width=1, color=color),
                layer="below"
            )

    # BOS et CHoCH
    if show_structure:

        for event in events[-15:]:

            bullish = event["direction"] == 1

            color = "#00C853" if bullish else "#FF5252"

            fig.add_annotation(
                x=event["time"],
                y=event["price"],
                text=event["type"],
                showarrow=True,
                arrowhead=2,
                arrowcolor=color,
                font=dict(color=color, size=11),
                bgcolor="rgba(0,0,0,0.65)",
                ax=0,
                ay=-35 if bullish else 35
            )

    fig.update_layout(
        height=750,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        title="Smart Money Concepts - M30",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=40, r=30, t=80, b=40)
    )

    return fig


# =========================================================
# AFFICHAGE PRINCIPAL
# =========================================================

st.title("Trading Monitor V2")
st.caption("Smart Money Lite | OANDA | M30")

st.markdown("---")

for label, pair in PAIRS.items():

    st.header(label)

    try:

        df = get_data(pair, TIMEFRAME, CANDLE_COUNT)

        if df.empty or len(df) < 210:
            st.warning("Données insuffisantes pour l'analyse.")
            continue

        df = calculate_indicators(df)

        df, events = detect_market_structure(df)

        gaps = detect_fvg(df)

        current_price = get_current_price(pair)

        last = df.iloc[-1]

        # ---------------------------------------------
        # TENDANCE EMA
        # ---------------------------------------------

        bullish_ema = (
            last["EMA50"] > last["EMA100"]
            and last["EMA100"] > last["EMA200"]
        )

        bearish_ema = (
            last["EMA50"] < last["EMA100"]
            and last["EMA100"] < last["EMA200"]
        )

        if bullish_ema:
            ema_status = "Haussier"
        elif bearish_ema:
            ema_status = "Baissier"
        else:
            ema_status = "Neutre"

        # ---------------------------------------------
        # DERNIER ÉVÉNEMENT STRUCTUREL
        # ---------------------------------------------

        last_event = events[-1] if events else None

        if last_event:

            direction_text = (
                "Haussier"
                if last_event["direction"] == 1
                else "Baissier"
            )

            structure_status = (
                f'{last_event["type"]} {direction_text}'
            )

        else:
            structure_status = "Aucun événement détecté"

        # ---------------------------------------------
        # AFFICHAGE DES INDICATEURS
        # ---------------------------------------------

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Prix actuel",
                f"{current_price:.5f}"
                if current_price is not None
                else "N/D"
            )

        with col2:
            st.metric("Tendance EMA", ema_status)

        with col3:
            st.metric("Structure M30", structure_status)

        with col4:
            st.metric("FVG détectés", len(gaps))

        # ---------------------------------------------
        # SIGNAL STRUCTUREL
        # ---------------------------------------------

        if last_event and last_event["time"] == last["time"]:

            if last_event["direction"] == 1:

                signal = (
                    "🟢 CHoCH haussier"
                    if last_event["type"] == "CHoCH"
                    else "🟢 BOS haussier"
                )

                voice = VOICE_STRONG_BULL

            else:

                signal = (
                    "🔴 CHoCH baissier"
                    if last_event["type"] == "CHoCH"
                    else "🔴 BOS baissier"
                )

                voice = VOICE_STRONG_BEAR

            st.subheader(signal)

            # Une seule alerte par événement
            alert_key = (
                f"{pair}_{last_event['time']}_{last_event['type']}"
            )

            if not mute_alerts:

                if alert_key not in st.session_state:

                    play_voice_alert(voice)

                    st.session_state[alert_key] = True

        else:

            st.info(
                "Aucune nouvelle cassure structurelle "
                "sur le dernier chandelier terminé."
            )

        # ---------------------------------------------
        # TABLEAU DES DERNIERS FVG
        # ---------------------------------------------

        with st.expander("Voir les derniers Fair Value Gaps"):

            if gaps:

                fvg_df = pd.DataFrame(gaps[-10:][::-1])

                fvg_df = fvg_df[
                    ["time", "type", "top", "bottom"]
                ]

                st.dataframe(
                    fvg_df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.write("Aucun FVG détecté.")

        # ---------------------------------------------
        # TABLEAU STRUCTUREL
        # ---------------------------------------------

        with st.expander("Historique BOS / CHoCH"):

            if events:

                events_df = pd.DataFrame(events[-15:][::-1])

                st.dataframe(
                    events_df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.write("Aucune structure détectée.")

        # ---------------------------------------------
        # GRAPHIQUE
        # ---------------------------------------------

        fig = create_chart(df, gaps, events)

        st.plotly_chart(
            fig,
            use_container_width=True,
            key=f"chart_{pair}"
        )

        st.markdown("---")

    except Exception as e:

        st.error(f"Erreur pour {pair} : {e}")


# =========================================================
# PROFITS / PERTES - 7 DERNIERS JOURS
# =========================================================

st.subheader("📅 Profits / Pertes - 7 derniers jours")

try:

    since = (
        datetime.now(pytz.UTC) - timedelta(days=7)
    ).isoformat()

    request = TransactionList(
        accountID=ACCOUNT_ID,
        params={"from": since}
    )

    client.request(request)

    transactions = request.response.get(
        "transactions", []
    )

    pnl = {}

    for transaction in transactions:

        if (
            transaction["type"] == "ORDER_FILL"
            and "pl" in transaction
        ):

            date = transaction["time"].split("T")[0]

            pnl[date] = (
                pnl.get(date, 0)
                + float(transaction["pl"])
            )

    if pnl:

        df_pnl = pd.DataFrame(
            sorted(pnl.items()),
            columns=["Date", "P&L"]
        )

        df_pnl["P&L"] = df_pnl["P&L"].round(2)

        df_pnl["Status"] = df_pnl["P&L"].apply(
            lambda x: "Gain" if x >= 0 else "Perte"
        )

        st.dataframe(
            df_pnl,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Aucune transaction enregistrée "
            "dans les 7 derniers jours."
        )

except Exception as e:

    st.error(f"Erreur OANDA : {e}")


# =========================================================
# DERNIÈRE MISE À JOUR
# =========================================================

now = datetime.now(NY_TZ)

st.caption(
    f"Dernière mise à jour : "
    f"{now.strftime('%Y-%m-%d %H:%M:%S')} NY"
)
