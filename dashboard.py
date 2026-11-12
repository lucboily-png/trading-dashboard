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
import smtplib
from email.mime.text import MIMEText

st.set_page_config(page_title="Trading Monitor - EMA Trend Alerts", layout="wide")
st_autorefresh(interval=60 * 1000, key="refresh")


def get_secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


ACCESS_TOKEN = get_secret("OANDA_ACCESS_TOKEN")
ACCOUNT_ID = get_secret("OANDA_ACCOUNT_ID")

if not ACCESS_TOKEN or not ACCOUNT_ID:
    st.error(
        "Configuration OANDA manquante. Ajoute OANDA_ACCESS_TOKEN et "
        "OANDA_ACCOUNT_ID dans les Secrets de ton application Streamlit."
    )
    st.stop()

client = API(access_token=ACCESS_TOKEN, environment="practice")

VOICE_STRONG_BULL = (
    "https://cdn.pixabay.com/download/audio/2023/03/22/"
    "audio_7e47f7d88e.mp3?filename=alert-female-strong-bullish.mp3"
)
VOICE_STRONG_BEAR = (
    "https://cdn.pixabay.com/download/audio/2023/03/22/"
    "audio_2ac24c3bd2.mp3?filename=alert-female-strong-bearish.mp3"
)


def play_voice_alert(url):
    audio_script = f"""
        <script>
            var audio = new Audio("{url}");
            audio.volume = 1.0;
            audio.play().catch(function(error) {{
                console.log("Lecture audio bloquée par le navigateur:", error);
            }});
        </script>
    """
    components.html(audio_script, height=0, width=0)


def send_email_alert(subject, body):
    smtp_server = get_secret("SMTP_SERVER")
    smtp_port = get_secret("SMTP_PORT", 587)
    smtp_username = get_secret("SMTP_USERNAME")
    smtp_password = get_secret("SMTP_PASSWORD")
    email_from = get_secret("ALERT_EMAIL_FROM")
    email_to = get_secret("ALERT_EMAIL_TO")

    if not all([smtp_server, smtp_username, smtp_password, email_from, email_to]):
        return False, "Paramètres courriel SMTP non configurés."

    try:
        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = email_from
        message["To"] = email_to
        with smtplib.SMTP(smtp_server, int(smtp_port), timeout=20) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(message)
        return True, "Courriel envoyé."
    except Exception as exc:
        return False, f"Erreur d'envoi du courriel : {exc}"


# SIDEBAR
st.sidebar.title("Configuration des instruments")
pairs = [
    "EUR_USD", "SPX500_USD", "AUD_USD", "GBP_USD",
    "BTC_USD", "ETH_USD", "XAU_USD", "USD_CAD"
]
timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D", "W"]
instruments_config = []

for i in range(4):
    pair = st.sidebar.selectbox(f"Instrument {i + 1}", pairs, index=i, key=f"pair_{i}")
    timeframe = st.sidebar.selectbox(
        f"Timeframe {i + 1}", timeframes,
        index=3 if i == 0 else 1, key=f"timeframe_{i}"
    )
    instruments_config.append({"pair": pair, "timeframe": timeframe})

mute_alerts = st.sidebar.checkbox("Désactiver les alertes vocales", value=False)
email_alerts_enabled = st.sidebar.checkbox("Activer les alertes par courriel", value=True)

st.sidebar.subheader("💰 Calculateur gains/pertes")
capital = st.sidebar.number_input("Capital ($)", value=500.0, min_value=0.0)
risk_percent = st.sidebar.number_input("Risque (%)", value=2.0, min_value=0.0)
leverage = st.sidebar.number_input("Levier", value=50, min_value=1)
rr = st.sidebar.number_input("RR", value=3.0, min_value=0.1)
risk_amount = capital * (risk_percent / 100)
potential_gain = risk_amount * rr
exposure = capital * leverage
st.sidebar.write(f"Risque/trade : **{risk_amount:.2f} $**")
st.sidebar.write(f"Gain potentiel : **{potential_gain:.2f} $**")
st.sidebar.write(f"Exposition théorique : **{exposure:,.0f} $**")
st.sidebar.caption("Les signaux EMA sont des alertes de tendance, pas des ordres automatiques.")


# OANDA DATA
def get_data(pair, granularity="M30", count=300):
    request = instruments.InstrumentsCandles(
        instrument=pair,
        params={"count": count, "granularity": granularity, "price": "M"}
    )
    client.request(request)
    candles = request.response.get("candles", [])
    rows = []
    for candle in candles:
        if "mid" not in candle:
            continue
        rows.append({
            "time": candle["time"],
            "open": float(candle["mid"]["o"]),
            "high": float(candle["mid"]["h"]),
            "low": float(candle["mid"]["l"]),
            "close": float(candle["mid"]["c"]),
            "volume": int(candle.get("volume", 0)),
            "complete": bool(candle.get("complete", False))
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert("America/New_York")
    return df


def get_current_price(pair):
    try:
        request = instruments.InstrumentsCandles(
            instrument=pair,
            params={"count": 1, "granularity": "M1", "price": "M"}
        )
        client.request(request)
        candles = request.response.get("candles", [])
        return float(candles[-1]["mid"]["c"]) if candles else None
    except Exception:
        return None


# INDICATORS
def add_indicators(df):
    df = df.copy()
    df["EMA50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["EMA100"] = df["close"].ewm(span=100, adjust=False).mean()
    df["EMA200"] = df["close"].ewm(span=200, adjust=False).mean()

    previous_close = df["close"].shift(1)
    true_range = pd.concat([
        df["high"] - df["low"],
        (df["high"] - previous_close).abs(),
        (df["low"] - previous_close).abs()
    ], axis=1).max(axis=1)
    df["ATR14"] = true_range.rolling(14).mean()

    df["Up"] = df["high"].diff()
    df["Down"] = -df["low"].diff()
    df["+DM"] = df["Up"].where((df["Up"] > df["Down"]) & (df["Up"] > 0), 0.0)
    df["-DM"] = df["Down"].where((df["Down"] > df["Up"]) & (df["Down"] > 0), 0.0)
    df["TR14"] = true_range.rolling(14).sum()
    df["+DI14"] = 100 * df["+DM"].rolling(14).sum() / df["TR14"]
    df["-DI14"] = 100 * df["-DM"].rolling(14).sum() / df["TR14"]
    di_sum = (df["+DI14"] + df["-DI14"]).replace(0, float("nan"))
    df["DX"] = 100 * (df["+DI14"] - df["-DI14"]).abs() / di_sum
    df["ADX14"] = df["DX"].rolling(14).mean()
    return df


def evaluate_ema_scenario(df):
    """Evaluate the latest closed candle and 3-candle EMA slope."""
    if len(df) < 205:
        return {
            "state": "NONE", "label": "Données insuffisantes",
            "color": "gray", "details": "Il faut au moins 205 chandelles clôturées."
        }

    last = df.iloc[-1]
    lookback = df.iloc[-4]
    required = [
        last["close"], last["EMA50"], last["EMA100"], last["EMA200"],
        lookback["EMA50"], lookback["EMA100"], lookback["EMA200"]
    ]
    if any(pd.isna(value) for value in required):
        return {
            "state": "NONE", "label": "Calcul des EMA en cours",
            "color": "gray", "details": "Les indicateurs ne sont pas encore disponibles."
        }

    bull_order = last["close"] > last["EMA50"] > last["EMA100"] > last["EMA200"]
    bull_slope = (
        last["EMA50"] > lookback["EMA50"]
        and last["EMA100"] > lookback["EMA100"]
        and last["EMA200"] > lookback["EMA200"]
    )
    bear_order = last["close"] < last["EMA50"] < last["EMA100"] < last["EMA200"]
    bear_slope = (
        last["EMA50"] < lookback["EMA50"]
        and last["EMA100"] < lookback["EMA100"]
        and last["EMA200"] < lookback["EMA200"]
    )

    if bull_order and bull_slope:
        return {
            "state": "BULL",
            "label": "🟢 SCÉNARIO 1 — TENDANCE HAUSSIÈRE CONFIRMÉE",
            "color": "green",
            "details": "Prix > EMA50 > EMA100 > EMA200; les trois EMA montent."
        }
    if bear_order and bear_slope:
        return {
            "state": "BEAR",
            "label": "🔴 SCÉNARIO 2 — TENDANCE BAISSIÈRE CONFIRMÉE",
            "color": "red",
            "details": "Prix < EMA50 < EMA100 < EMA200; les trois EMA descendent."
        }
    return {
        "state": "NONE",
        "label": "⚪ Aucun scénario confirmé",
        "color": "gray",
        "details": "L'alignement complet et la pente commune des EMA ne sont pas réunis."
    }


# ALERT STATE: no repeated alert every minute for the same active setup
def process_trend_alert(pair, timeframe, trend, candle_time):
    state_key = f"ema_alert_state_{pair}_{timeframe}"
    previous_state = st.session_state.get(state_key, "INIT")
    st.session_state[state_key] = trend["state"]

    is_new_signal = (
        trend["state"] in ("BULL", "BEAR")
        and trend["state"] != previous_state
    )
    if not is_new_signal:
        return

    if trend["state"] == "BULL":
        subject = f"🟢 Signal ACHAT — {pair} {timeframe}"
        body = (
            f"Signal haussier confirmé sur {pair} en {timeframe}.\n"
            "Condition : Prix > EMA50 > EMA100 > EMA200.\n"
            "Les trois moyennes mobiles montent.\n"
            f"Dernière chandelle clôturée : {candle_time}.\n\n"
            "Biais de tendance seulement; pas un ordre automatique."
        )
        voice_url = VOICE_STRONG_BULL
    else:
        subject = f"🔴 Signal VENTE — {pair} {timeframe}"
        body = (
            f"Signal baissier confirmé sur {pair} en {timeframe}.\n"
            "Condition : Prix < EMA50 < EMA100 < EMA200.\n"
            "Les trois moyennes mobiles descendent.\n"
            f"Dernière chandelle clôturée : {candle_time}.\n\n"
            "Biais de tendance seulement; pas un ordre automatique."
        )
        voice_url = VOICE_STRONG_BEAR

    st.session_state.setdefault("ema_new_alerts", [])
    st.session_state["ema_new_alerts"].append({
        "Heure": datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d %H:%M:%S"),
        "Instrument": pair,
        "Timeframe": timeframe,
        "Signal": subject
    })

    if not mute_alerts:
        play_voice_alert(voice_url)

    if email_alerts_enabled:
        sent, status = send_email_alert(subject, body)
        if not sent and "non configurés" not in status:
            st.warning(status)


# MAIN DASHBOARD
st.title("Trading Monitor — EMA Trend Alerts")
st.caption(
    "Alertes basées sur l'alignement du prix, l'ordre des EMA50/100/200 "
    "et la pente des trois moyennes."
)

for config in instruments_config:
    pair = config["pair"]
    timeframe = config["timeframe"]
    st.markdown("---")
    st.subheader(f"{pair} — {timeframe}")

    try:
        raw_df = get_data(pair, timeframe)
        if raw_df.empty:
            st.warning(f"Aucune donnée reçue pour {pair}.")
            continue

        # Signal uses completed candles only, not the still-forming candle.
        closed_df = raw_df[raw_df["complete"]].copy()
        if closed_df.empty:
            st.warning(f"Aucune chandelle clôturée disponible pour {pair}.")
            continue

        df = add_indicators(closed_df)
        current_price = get_current_price(pair)
        trend = evaluate_ema_scenario(df)
        last = df.iloc[-1]
        candle_time = last["time"].strftime("%Y-%m-%d %H:%M NY")

        process_trend_alert(pair, timeframe, trend, candle_time)

        if current_price is not None:
            st.write(f"💵 Prix actuel OANDA : **{current_price:.5f}**")

        st.markdown(
            f"<h4 style='color:{trend['color']};'>{trend['label']}</h4>",
            unsafe_allow_html=True
        )
        st.write(trend["details"])
        st.caption(f"Signal calculé sur la dernière chandelle clôturée : {candle_time}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("EMA50", f"{last['EMA50']:.5f}")
        col2.metric("EMA100", f"{last['EMA100']:.5f}")
        col3.metric("EMA200", f"{last['EMA200']:.5f}")
        col4.metric("ADX14", "N/D" if pd.isna(last["ADX14"]) else f"{last['ADX14']:.1f}")

        # CHART
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            row_heights=[0.7, 0.3], vertical_spacing=0.05
        )
        fig.add_trace(
            go.Scatter(
                x=df["time"], y=df["close"], name="Close",
                line=dict(color="gray", dash="dot")
            ), row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df["time"], y=df["EMA50"], name="EMA50",
                line=dict(color="blue", width=2)
            ), row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df["time"], y=df["EMA100"], name="EMA100",
                line=dict(color="gray", dash="dash", width=2)
            ), row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df["time"], y=df["EMA200"], name="EMA200",
                line=dict(color="orange", width=2)
            ), row=1, col=1
        )
        fig.add_trace(
            go.Bar(
                x=df["time"], y=df["volume"], name="Volume",
                marker_color="rgba(150,150,150,0.6)"
            ), row=2, col=1
        )
        fig.update_layout(
            height=700, template="plotly_dark",
            margin=dict(l=20, r=20, t=35, b=20),
            legend=dict(orientation="h", y=1.02, x=0)
        )
        st.plotly_chart(fig, use_container_width=True)

    except Exception as exc:
        st.error(f"Erreur pour {pair} ({timeframe}) : {exc}")


# RECENT ALERTS
st.markdown("---")
st.subheader("🔔 Alertes EMA récentes")
recent_alerts = st.session_state.get("ema_new_alerts", [])
if recent_alerts:
    st.dataframe(pd.DataFrame(recent_alerts[::-1]), use_container_width=True, hide_index=True)
else:
    st.info("Aucune nouvelle alerte EMA depuis l'ouverture du dashboard.")


# PROFIT / LOSS LAST 7 DAYS
st.markdown("---")
st.subheader("📅 Profits / Pertes (7 derniers jours)")
try:
    since = (datetime.utcnow() - timedelta(days=7)).isoformat("T") + "Z"
    request = TransactionList(accountID=ACCOUNT_ID, params={"from": since})
    client.request(request)
    transactions = request.response.get("transactions", [])
    pnl = {}

    for transaction in transactions:
        if transaction.get("type") == "ORDER_FILL" and "pl" in transaction:
            day = transaction["time"].split("T")[0]
            pnl[day] = pnl.get(day, 0.0) + float(transaction["pl"])

    if pnl:
        pnl_df = pd.DataFrame(sorted(pnl.items()), columns=["Date", "P&L"])
        pnl_df["P&L"] = pnl_df["P&L"].round(2)
        pnl_df["Status"] = pnl_df["P&L"].apply(
            lambda value: "🟢 Gain" if value >= 0 else "🔴 Perte"
        )
        st.dataframe(pnl_df, use_container_width=True, hide_index=True)
    else:
        st.info("Aucune transaction enregistrée dans les 7 derniers jours.")
except Exception as exc:
    st.error(f"Erreur OANDA dans l'historique des transactions : {exc}")

now = datetime.now(pytz.timezone("America/New_York"))
st.caption(f"🕒 Dernière mise à jour : {now.strftime('%Y-%m-%d %H:%M:%S')} NY")
