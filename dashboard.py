import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pytz
import streamlit.components.v1 as components
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
from oandapyV20.endpoints.transactions import TransactionList
from streamlit_autorefresh import st_autorefresh

# --- Page config ---
st.set_page_config(page_title="Trading Monitor + Voice Alerts", layout="wide")

# --- Auto-refresh ---
st_autorefresh(interval=60 * 1000, key="refresh")

# --- Human voice alert system ---
def play_voice_alert(url):
    audio_script = f"""
        <script>
            var audio = new Audio("{url}");
            audio.volume = 1.0;
            audio.play();
        </script>
    """
    components.html(audio_script, height=0, width=0)


# --- Voice files ---
VOICE_STRONG_BULL = "https://cdn.pixabay.com/download/audio/2023/03/22/audio_7e47f7d88e.mp3?filename=alert-female-strong-bullish.mp3"
VOICE_WEAK_BULL  = "https://cdn.pixabay.com/download/audio/2023/03/22/audio_45ad3f98f1.mp3?filename=alert-female-weak-bullish.mp3"
VOICE_STRONG_BEAR = "https://cdn.pixabay.com/download/audio/2023/03/22/audio_2ac24c3bd2.mp3?filename=alert-female-strong-bearish.mp3"
VOICE_WEAK_BEAR   = "https://cdn.pixabay.com/download/audio/2023/03/22/audio_e4df2d3f17.mp3?filename=alert-female-weak-bearish.mp3"

# --- Oanda connection ---
ACCESS_TOKEN = "c934bb8699bd3ec60e58b918a3d5399b-27034ab74bc7b6a1f2546817767e57d3"
ACCOUNT_ID = "101-002-37205058-001"
client = API(access_token=ACCESS_TOKEN, environment="practice")

st.subheader("P/L non réalisé (positions ouvertes)")

unrealized_total, detail = get_unrealized_pl(client, account_id)

if unrealized_total is None:
    st.error("Impossible de récupérer les positions ouvertes.")
else:
    color = "green" if unrealized_total >= 0 else "red"
    st.markdown(f"<h2 style='color:{color};'> {unrealized_total:.2f} </h2>", unsafe_allow_html=True)


# --- Sidebar Config ---
st.sidebar.title("Configuration des instruments")
instruments_config = []
pairs = ["EUR_USD", "AUD_USD", "GBP_USD", "BTC_USD"]

for i in range(4):
    pair = st.sidebar.selectbox(f"Pair {i+1}:", pairs, index=i)
    timeframe = st.sidebar.selectbox(f"Timeframe {i+1}:", ["M1", "M5", "M15", "H1", "H4"], index=1)
    instruments_config.append({"pair": pair, "timeframe": timeframe})

mute_alerts = st.sidebar.checkbox("Mute alerts", value=False)

# --- Gain Calculator ---
st.sidebar.subheader("💰 Calculateur gains/pertes")
capital = st.sidebar.number_input("Capital ($)", value=500.0)
risk_percent = st.sidebar.number_input("Risque (%)", value=2.0)
leverage = st.sidebar.number_input("Levier", value=50)
rr = st.sidebar.number_input("RR", value=3.0)

risk_amount = capital * (risk_percent / 100)
potential_gain = risk_amount * rr
exposure = capital * leverage

st.sidebar.write(f"Risque/trade: **{risk_amount:.2f} $**")
st.sidebar.write(f"Gain potentiel: **{potential_gain:.2f} $**")
st.sidebar.write(f"Exposition totale: **{exposure:,.0f} $**")

# --- Extract Oanda Candles ---
def get_data(pair, granularity="M5", count=300):
    r = instruments.InstrumentsCandles(instrument=pair, params={
        "count": count, "granularity": granularity, "price": "M"
    })
    client.request(r)
    data = r.response["candles"]

    df = pd.DataFrame([{
        "time": c["time"],
        "open": float(c["mid"]["o"]),
        "high": float(c["mid"]["h"]),
        "low": float(c["mid"]["l"]),
        "close": float(c["mid"]["c"]),
        "volume": c.get("volume", 0)
    } for c in data])

    df["time"] = pd.to_datetime(df["time"]).dt.tz_convert("America/New_York")
    return df

def get_current_price(pair):
    try:
        r = instruments.InstrumentsCandles(instrument=pair, params={
            "count": 1, "granularity": "M1", "price": "M"
        })
        client.request(r)
        return float(r.response["candles"][-1]["mid"]["c"])
    except:
        return None


# --- DISPLAY EACH INSTRUMENT ---
for config in instruments_config:
    pair = config["pair"]
    tf = config["timeframe"]
    df = get_data(pair, tf)
    current_price = get_current_price(pair)

    # EMAs
    df["EMA50"]  = df["close"].ewm(span=50, adjust=False).mean()
    df["EMA100"] = df["close"].ewm(span=100, adjust=False).mean()
    df["EMA200"] = df["close"].ewm(span=200, adjust=False).mean()

    # ATR
    df["TR"] = (df["high"] - df["low"]).abs()
    df["ATR14"] = df["TR"].rolling(14).mean()

    # ADX calculation
    df["Up"] = df["high"] - df["high"].shift(1)
    df["Down"] = df["low"].shift(1) - df["low"]
    df["+DM"] = df["Up"].where((df["Up"] > df["Down"]) & (df["Up"] > 0), 0)
    df["-DM"] = df["Down"].where((df["Down"] > df["Up"]) & (df["Down"] > 0), 0)
    df["TR14"] = df["TR"].rolling(14).sum()
    df["+DI14"] = 100 * df["+DM"].rolling(14).sum() / df["TR14"]
    df["-DI14"] = 100 * df["-DM"].rolling(14).sum() / df["TR14"]
    df["DX"] = 100 * (df["+DI14"] - df["-DI14"]).abs() / (df["+DI14"] + df["-DI14"])
    df["ADX14"] = df["DX"].rolling(14).mean()

    # --- SIGNAL ---
    signal = "⚪ No signal"
    signal_color = "white"

    if len(df) > 200:
        ema50_prev, ema200_prev = df["EMA50"].iloc[-2], df["EMA200"].iloc[-2]
        ema50_now,  ema200_now  = df["EMA50"].iloc[-1], df["EMA200"].iloc[-1]
        adx = df["ADX14"].iloc[-1]
        atr = df["ATR14"].iloc[-1]
        atr_threshold = df["close"].iloc[-1] * 0.001

        golden = ema50_prev < ema200_prev and ema50_now > ema200_now
        death  = ema50_prev > ema200_prev and ema50_now < ema200_now

        if golden:
            strong = adx > 25 and atr > atr_threshold
            signal = "🟢 Strong Bullish Cross" if strong else "🟢 Weak Bullish Cross"
            signal_color = "green"
            if not mute_alerts:
                play_voice_alert(VOICE_STRONG_BULL if strong else VOICE_WEAK_BULL)

        elif death:
            strong = adx > 25 and atr > atr_threshold
            signal = "🔴 Strong Bearish Cross" if strong else "🔴 Weak Bearish Cross"
            signal_color = "red"
            if not mute_alerts:
                play_voice_alert(VOICE_STRONG_BEAR if strong else VOICE_WEAK_BEAR)

    st.markdown(f"## {pair} — {tf}")
    if current_price:
        st.write(f"💵 Current price: **{current_price:.5f}**")

    st.markdown(
        f"<b>Signal:</b> <span style='color:{signal_color}'>{signal}</span>",
        unsafe_allow_html=True
    )

    # --- FIGURE (HEIGHT 1000px) ---
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.3], vertical_spacing=0.05
    )

    # Price + EMAs
    fig.add_trace(go.Scatter(x=df["time"], y=df["close"], name="Close",
                             line=dict(color="gray", dash="dot")), row=1, col=1)

    fig.add_trace(go.Scatter(x=df["time"], y=df["EMA50"], name="EMA50",
                             line=dict(color="blue", width=2)), row=1, col=1)

    fig.add_trace(go.Scatter(x=df["time"], y=df["EMA100"], name="EMA100",
                             line=dict(color="gray", dash="dash")), row=1, col=1)

    fig.add_trace(go.Scatter(x=df["time"], y=df["EMA200"], name="EMA200",
                             line=dict(color="orange")), row=1, col=1)

    # Volume
    fig.add_trace(go.Bar(
        x=df["time"], y=df["volume"], name="Volume",
        marker_color="rgba(255,255,255,0.6)"
    ), row=2, col=1)

    fig.update_layout(height=700, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("---")

# --- PROFIT / LOSS LAST 7 DAYS ---
st.subheader("📅 Profits / Pertes (7 derniers jours)")

try:
    since = (datetime.utcnow() - timedelta(days=7)).isoformat("T") + "Z"
    r = TransactionList(accountID=ACCOUNT_ID, params={"from": since})
    client.request(r)

    transactions = r.response.get("transactions", [])
    pnl = {}

    for t in transactions:
        if t["type"] == "ORDER_FILL" and "pl" in t:
            d = t["time"].split("T")[0]
            pnl[d] = pnl.get(d, 0) + float(t["pl"])

    if pnl:
        df_pnl = pd.DataFrame(sorted(pnl.items()), columns=["Date", "P&L"])
        df_pnl["P&L"] = df_pnl["P&L"].round(2)
        df_pnl["Status"] = df_pnl["P&L"].apply(lambda x: "🟢 Gain" if x >= 0 else "🔴 Perte")
        st.table(df_pnl)
    else:
        st.info("Aucune transaction enregistrée dans les 7 derniers jours.")

except Exception as e:
    st.error(f"Erreur OANDA : {e}")

now = datetime.now(pytz.timezone("America/New_York"))
st.caption(f"🕒 Last update: {now.strftime('%Y-%m-%d %H:%M:%S')} NY")

