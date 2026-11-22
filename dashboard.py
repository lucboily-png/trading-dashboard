import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import pytz
import streamlit.components.v1 as components
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
from streamlit_autorefresh import st_autorefresh
import smtplib
import requests
import hashlib
import json
from pathlib import Path
from email.mime.text import MIMEText

st.set_page_config(page_title="Trading Monitor - Fibonacci Alerts", layout="wide")
st_autorefresh(interval=60 * 1000, key="refresh")


# DESIGN V1 â prÃ©sentation uniquement (aucune rÃ¨gle de trading modifiÃ©e)
st.markdown("""
<style>
:root { --navy:#071426; --panel:#0d2038; --panel2:#102945; --line:#1d4267; --blue:#18a8ff; --cyan:#35d5e8; --green:#20d68a; --red:#ff5b6e; --amber:#ffbf47; }
.stApp { background: radial-gradient(circle at 12% 0%, #102b4a 0, #071426 42%, #050d19 100%); color:#eaf3ff; }
[data-testid="stHeader"] { background:rgba(5,13,25,.82); }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#0b1b30,#071321); border-right:1px solid #173756; }
[data-testid="stSidebar"] * { color:#22b8ff; }
h1,h2,h3,h4 { color:#f1f7ff !important; letter-spacing:-.025em; }
[data-testid="stMetric"] { background:linear-gradient(145deg,rgba(16,43,72,.95),rgba(8,24,43,.95)); border:1px solid #1c456c; padding:14px 16px; border-radius:15px; box-shadow:0 8px 24px rgba(0,0,0,.18); }
[data-testid="stMetricLabel"] { color:#9db8d4 !important; }
[data-testid="stMetricValue"] { color:#f4f8ff !important; }
[data-testid="stVerticalBlockBorderWrapper"] { background:linear-gradient(145deg,rgba(13,32,56,.92),rgba(7,20,36,.92)); border:1px solid #1b4267; border-radius:17px; }
.stButton>button, .stDownloadButton>button { border-radius:10px; border:1px solid #187fbe; background:linear-gradient(100deg,#087cc4,#12a9ed); color:white; font-weight:650; }
.stButton>button:hover, .stDownloadButton>button:hover { border-color:#5bdcff; color:white; }
[data-testid="stDataFrame"] { border:1px solid #1b4267; border-radius:12px; overflow:hidden; }
hr { border-color:#1a3b5c !important; }
[data-testid="stCaptionContainer"] { color:#91abc7; }
/* Menus déroulants : contraste renforcé pour les instruments et timeframes */
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
    background-color:#102945 !important;
    border:1px solid #2873a8 !important;
    color:#f3f8ff !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] input,
[data-testid="stSelectbox"] [data-baseweb="select"] span,
[data-testid="stMultiSelect"] [data-baseweb="select"] input,
[data-testid="stMultiSelect"] [data-baseweb="select"] span {
    color:#f3f8ff !important;
    -webkit-text-fill-color:#f3f8ff !important;
}
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="menu"] {
    background-color:#0d2038 !important;
    border:1px solid #2873a8 !important;
}
[data-baseweb="popover"] [role="option"],
[data-baseweb="menu"] [role="option"] {
    background-color:#0d2038 !important;
    color:#f3f8ff !important;
    -webkit-text-fill-color:#f3f8ff !important;
}
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [aria-selected="true"],
[data-baseweb="menu"] [role="option"]:hover,
[data-baseweb="menu"] [aria-selected="true"] {
    background-color:#155184 !important;
    color:#ffffff !important;
    -webkit-text-fill-color:#ffffff !important;
}
/* Correctif ciblé : texte de la valeur sélectionnée dans le champ fermé */
[data-testid="stSelectbox"] [data-baseweb="select"] *,
[data-testid="stMultiSelect"] [data-baseweb="select"] * {
    color: #f3f8ff !important;
    -webkit-text-fill-color: #f3f8ff !important;
    opacity: 1 !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] [class*="singleValue"],
[data-testid="stSelectbox"] [data-baseweb="select"] [class*="single-value"],
[data-testid="stSelectbox"] [data-baseweb="select"] [role="combobox"] {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    opacity: 1 !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] svg {
    fill: #dcecff !important;
    color: #dcecff !important;
}

/* Espacement plus proche d'un terminal de trading */
.block-container { padding-top:1.4rem; padding-bottom:2rem; max-width:1600px; }
</style>
""", unsafe_allow_html=True)


def get_secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


# SUPABASE — stockage persistant des trades virtuels
SUPABASE_URL = str(get_secret("SUPABASE_URL", "") or "").strip().strip('"').rstrip("/")

# Nettoyage de l'adresse
SUPABASE_URL = SUPABASE_URL.replace("https:/", "https://")
SUPABASE_URL = SUPABASE_URL.replace("http:/", "http://")

if not SUPABASE_URL.startswith(("https://", "http://")):
    SUPABASE_URL = "https://" + SUPABASE_URL

SUPABASE_SERVICE_ROLE_KEY = get_secret("SUPABASE_SERVICE_ROLE_KEY", "")

def supabase_configured():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)

def supabase_request(method, table="virtual_trades", params=None, payload=None,
                     prefer=None):
    """Appel REST Supabase. La clé service_role reste côté serveur Streamlit."""
    if not supabase_configured():
        raise RuntimeError("Secrets SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY manquants.")
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    response = requests.request(
        method,
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        params=params,
        json=payload,
        timeout=20,
    )
    response.raise_for_status()
    if response.text.strip():
        return response.json()
    return []

def _signal_identity(pair, timeframe, fib, fib_mode):
    identity = (
        f"{pair}|{timeframe}|{fib['direction']}|{fib_mode}|"
        f"{fib['origin']['time']}|{fib['endpoint']['time']}"
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def create_pending_setup(pair, timeframe, setup, candle_time, trade_plan, fib_mode):
    """Stocke une configuration en attente; aucun trade n'est encore ouvert."""
    if not supabase_configured():
        return False, "Supabase requis pour conserver une configuration en attente."
    if not trade_plan or not setup.get("fib"):
        return False, "Configuration incomplète."

    fib = setup["fib"]
    candle_iso = pd.Timestamp(
        candle_time.replace(" NY", "")
    ).tz_localize("America/New_York").isoformat()
    signal_key = _signal_identity(pair, timeframe, fib, fib_mode.upper())
    metadata = {
        "phase": "WAIT_RETEST",
        "trigger_level": float(setup["trigger_level"]),
        "zone_low": float(fib["zone_low"]),
        "zone_high": float(fib["zone_high"]),
        "atr": float(fib["atr"]),
        "endpoint_price": float(fib["endpoint"]["price"]),
        "origin_price": float(fib["origin"]["price"]),
        "origin_time": str(fib["origin"]["time"]),
        "endpoint_time": str(fib["endpoint"]["time"]),
        "manual": bool(fib.get("manual", False)),
        "retest_seen": False,
        "retest_high": None,
        "retest_low": None,
        "retest_time": None,
        "bars_elapsed": 0,
        "last_processed_candle": candle_iso,
        "max_wait_candles": 6,
        "retest_tolerance_atr": 0.15,
        "max_entry_extension_atr": 0.25,
        "fib_mode": fib_mode.upper(),
    }
    payload = {
        "signal_key": signal_key,
        "instrument": pair,
        "timeframe": timeframe,
        "direction": fib["direction"],
        "fib_mode": fib_mode.upper(),
        "signal_time": datetime.now(pytz.UTC).isoformat(),
        "candle_time": candle_iso,
        # Ces prix sont provisoires et le statut PENDING empêche leur suivi comme trade.
        "entry_price": float(trade_plan["entry"]),
        "stop_loss": float(trade_plan["stop_loss"]),
        "take_profit": float(trade_plan["take_profit"]),
        "rr": float(trade_plan["rr"]),
        "status": "PENDING",
        "notes": json.dumps(metadata, ensure_ascii=False),
    }
    result = supabase_request(
        "POST", payload=payload,
        params={"on_conflict": "signal_key"},
        prefer="resolution=ignore-duplicates,return=representation",
    )
    return bool(result), "Configuration en attente enregistrée." if result else "Configuration déjà enregistrée."


def activate_pending_setup(pending, confirmation_candle, trade_plan):
    """Transforme une configuration PENDING en trade OPEN après le retest confirmé."""
    candle_iso = pd.Timestamp(confirmation_candle["time"]).isoformat()
    supabase_request(
        "PATCH",
        params={"id": f"eq.{pending['id']}", "status": "eq.PENDING"},
        payload={
            "status": "OPEN",
            "candle_time": candle_iso,
            "entry_price": float(trade_plan["entry"]),
            "stop_loss": float(trade_plan["stop_loss"]),
            "take_profit": float(trade_plan["take_profit"]),
            "rr": float(trade_plan["rr"]),
            "notes": "Entrée confirmée après retest et nouvelle clôture de confirmation. Trade virtuel; aucun ordre OANDA envoyé.",
            "updated_at": datetime.now(pytz.UTC).isoformat(),
        },
        prefer="return=minimal",
    )


def update_pending_setup(pending_id, metadata, status="PENDING", note=None):
    payload = {
        "status": status,
        "notes": note if note is not None else json.dumps(metadata, ensure_ascii=False),
        "updated_at": datetime.now(pytz.UTC).isoformat(),
    }
    supabase_request(
        "PATCH",
        params={"id": f"eq.{pending_id}", "status": "eq.PENDING"},
        payload=payload,
        prefer="return=minimal",
    )


def load_pending_setups(pair, timeframe):
    if not supabase_configured():
        return []
    return supabase_request(
        "GET",
        params={
            "select": "*",
            "status": "eq.PENDING",
            "instrument": f"eq.{pair}",
            "timeframe": f"eq.{timeframe}",
            "order": "candle_time.asc",
        },
    )


def monitor_virtual_trades(pair, timeframe, closed_df):
    """Vérifie les chandelles clôturées après le signal et ferme les trades virtuels."""
    if not supabase_configured() or closed_df.empty:
        return
    trades = supabase_request(
        "GET",
        params={
            "select": "*",
            "status": "eq.OPEN",
            "instrument": f"eq.{pair}",
            "timeframe": f"eq.{timeframe}",
            "order": "candle_time.asc",
        },
    )
    if not trades:
        return

    candles = closed_df.copy()
    candles["_utc_time"] = pd.to_datetime(candles["time"], utc=True)
    for trade in trades:
        signal_candle_time = pd.to_datetime(trade["candle_time"], utc=True)
        later = candles[candles["_utc_time"] > signal_candle_time]
        for _, candle in later.iterrows():
            high = float(candle["high"])
            low = float(candle["low"])
            direction = trade["direction"]
            stop = float(trade["stop_loss"])
            target = float(trade["take_profit"])

            if direction == "BULL":
                hit_stop = low <= stop
                hit_target = high >= target
            else:
                hit_stop = high >= stop
                hit_target = low <= target

            if not hit_stop and not hit_target:
                continue

            close_time = pd.Timestamp(candle["time"]).isoformat()
            if hit_stop and hit_target:
                status = "AMBIGUOUS"
                close_price = None
                result_r = None
                note = "TP et SL touchés dans la même chandelle; ordre intrachandelle inconnu."
            elif hit_target:
                status = "WIN"
                close_price = target
                result_r = float(trade["rr"])
                note = "Take-profit atteint."
            else:
                status = "LOSS"
                close_price = stop
                result_r = -1.0
                note = "Stop-loss atteint."

            supabase_request(
                "PATCH",
                params={"id": f"eq.{trade['id']}", "status": "eq.OPEN"},
                payload={
                    "status": status,
                    "close_price": close_price,
                    "close_time": close_time,
                    "result_r": result_r,
                    "notes": note,
                    "updated_at": datetime.now(pytz.UTC).isoformat(),
                },
                prefer="return=minimal",
            )
            break

def load_virtual_trade_stats():
    """Charge l'historique des trades virtuels depuis Supabase."""
    return supabase_request(
        "GET",
        params={"select": "*", "order": "created_at.desc", "limit": "500"},
    )


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
        import ssl
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            smtp_server, int(smtp_port or 465), context=context, timeout=30
        ) as server:
            server.login(smtp_username, smtp_password)
            server.send_message(message)
        return True, "Courriel envoyé."
    except Exception as exc:
        return False, f"Erreur d'envoi du courriel : {exc}"


# SIDEBAR
st.sidebar.title("Configuration des instruments")
# Les symboles sont ceux utilisés par OANDA. La disponibilité de BTC_USD
# dépend du type de compte et des instruments autorisés chez OANDA.
pairs = [None, "SPX500_USD", "XAU_USD", "EUR_USD", "BTC_USD"]
pair_labels = {
    "SPX500_USD": "SPX500 — S&P 500",
    "XAU_USD": "XAU/USD — Or",
    "EUR_USD": "EUR/USD — Euro / Dollar",
    "BTC_USD": "BTC/USD — Bitcoin",
}
timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D", "W"]
# Huit emplacements permettent de surveiller quatre marchés en M30 et M5.
default_configs = [
    ("SPX500_USD", "M30"), ("SPX500_USD", "M5"),
    ("XAU_USD", "M30"), ("XAU_USD", "M5"),
    ("EUR_USD", "M30"), ("EUR_USD", "M5"),
    (None, "M30"), (None, "M5"),
]
instruments_config = []

for i, (default_pair, default_timeframe) in enumerate(default_configs):
    default_pair_index = pairs.index(default_pair)
    default_timeframe_index = timeframes.index(default_timeframe)
    pair_key = f"pair_{i}"
    timeframe_key = f"timeframe_{i}"
    if st.session_state.get(pair_key) not in pairs:
        st.session_state[pair_key] = default_pair
    if st.session_state.get(timeframe_key) not in timeframes:
        st.session_state[timeframe_key] = default_timeframe
    pair = st.sidebar.selectbox(
        f"Instrument {i + 1}", pairs,
        index=default_pair_index,
        format_func=lambda value: "— Désactivé —" if value is None else pair_labels.get(value, value),
        key=pair_key
    )
    timeframe = st.sidebar.selectbox(
        f"Timeframe {i + 1}", timeframes,
        index=default_timeframe_index, key=timeframe_key
    )
    if pair is not None:
        instruments_config.append({"pair": pair, "timeframe": timeframe})

st.sidebar.caption(
    "SPX500, XAU/USD et EUR/USD sont préchargés en M30/M5. "
    "Les deux emplacements libres peuvent servir à ajouter BTC/USD ou un autre timeframe."
)

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
show_emas = st.sidebar.checkbox("Afficher les EMA sur le graphique", value=True)
st.sidebar.caption("Les alertes reposent sur le dernier Fibonacci valide, pas sur les EMA.")


# OANDA DATA
@st.cache_data(ttl=45, show_spinner=False)
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


def get_m30_market_context(pair):
    """Évalue le biais M30 sur chandelles clôturées uniquement."""
    raw_m30 = get_data(pair, "M30")
    if raw_m30.empty:
        return {"bias": "NEUTRAL", "strength": "Indisponible", "adx": None,
                "details": "Données M30 indisponibles."}

    closed_m30 = raw_m30[raw_m30["complete"]].copy()
    if len(closed_m30) < 210:
        return {"bias": "NEUTRAL", "strength": "Données insuffisantes", "adx": None,
                "details": "Au moins 210 chandelles M30 clôturées sont nécessaires."}

    m30 = add_indicators(closed_m30)
    last = m30.iloc[-1]
    values = [last.get("close"), last.get("EMA50"), last.get("EMA100"),
              last.get("EMA200"), last.get("+DI14"), last.get("-DI14"),
              last.get("ADX14")]
    if any(pd.isna(value) for value in values):
        return {"bias": "NEUTRAL", "strength": "Indisponible", "adx": None,
                "details": "Indicateurs M30 incomplets."}

    close = float(last["close"])
    ema50, ema100, ema200 = (float(last[k]) for k in ("EMA50", "EMA100", "EMA200"))
    plus_di, minus_di = float(last["+DI14"]), float(last["-DI14"])
    adx = float(last["ADX14"])

    if close > ema200 and ema50 > ema100 and plus_di > minus_di:
        bias = "BULL"
        details = "Prix au-dessus de l'EMA200, EMA50 au-dessus EMA100 et +DI dominant."
    elif close < ema200 and ema50 < ema100 and minus_di > plus_di:
        bias = "BEAR"
        details = "Prix sous l'EMA200, EMA50 sous EMA100 et -DI dominant."
    else:
        bias = "NEUTRAL"
        details = "Les critères de direction M30 ne sont pas suffisamment alignés."

    strength = "Faible" if adx < 15 else ("Modérée" if adx < 25 else "Forte")
    return {"bias": bias, "strength": strength, "adx": adx, "details": details,
            "candle_time": str(last["time"])}


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


def find_last_fibonacci(df, pivot_window=3, min_leg_atr=1.5):
    """Trouve le dernier swing confirmé et construit son retracement Fibonacci.

    Les pivots sont confirmés seulement après `pivot_window` chandelles à droite,
    afin d'éviter d'utiliser un sommet/creux qui n'est pas encore établi.
    """
    data = df.reset_index(drop=True)
    if len(data) < max(40, pivot_window * 2 + 20):
        return None, "Données insuffisantes pour détecter un swing fiable."

    pivots = []
    for i in range(pivot_window, len(data) - pivot_window):
        high = float(data.loc[i, "high"])
        low = float(data.loc[i, "low"])
        left = data.iloc[i-pivot_window:i]
        right = data.iloc[i+1:i+pivot_window+1]
        is_high = high > float(left["high"].max()) and high >= float(right["high"].max())
        is_low = low < float(left["low"].min()) and low <= float(right["low"].min())
        if is_high:
            pivots.append({"index": i, "type": "HIGH", "price": high, "time": data.loc[i, "time"]})
        if is_low:
            pivots.append({"index": i, "type": "LOW", "price": low, "time": data.loc[i, "time"]})

    pivots.sort(key=lambda x: x["index"])
    # Fusionne deux pivots consécutifs de même type en conservant l'extrême.
    alternating = []
    for pivot in pivots:
        if not alternating or alternating[-1]["type"] != pivot["type"]:
            alternating.append(pivot)
        else:
            old = alternating[-1]
            more_extreme = (
                pivot["price"] > old["price"] if pivot["type"] == "HIGH"
                else pivot["price"] < old["price"]
            )
            if more_extreme:
                alternating[-1] = pivot

    if len(alternating) < 2:
        return None, "Aucun mouvement haussier ou baissier confirmé détecté."

    # Le dernier mouvement est formé par les deux derniers pivots confirmés.
    origin, endpoint = alternating[-2], alternating[-1]
    if origin["type"] == endpoint["type"]:
        return None, "Le dernier swing n'est pas encore exploitable."

    atr = float(data.iloc[-1].get("ATR14", float("nan")))
    leg_size = abs(endpoint["price"] - origin["price"])
    if pd.isna(atr) or atr <= 0 or leg_size < min_leg_atr * atr:
        return None, "Dernier mouvement trop faible pour produire un Fibonacci valide."

    bullish = origin["type"] == "LOW" and endpoint["type"] == "HIGH"
    bearish = origin["type"] == "HIGH" and endpoint["type"] == "LOW"
    if not (bullish or bearish):
        return None, "Structure de swing non valide."

    if bullish:
        levels = {r: endpoint["price"] - leg_size * r for r in (0.382, 0.5, 0.618, 0.786)}
        zone_low, zone_high = levels[0.618], levels[0.5]
        invalidated = float(data.iloc[-1]["close"]) < origin["price"]
        direction = "BULL"
    else:
        levels = {r: endpoint["price"] + leg_size * r for r in (0.382, 0.5, 0.618, 0.786)}
        zone_low, zone_high = levels[0.5], levels[0.618]
        invalidated = float(data.iloc[-1]["close"]) > origin["price"]
        direction = "BEAR"

    if invalidated:
        return None, "Fibonacci invalidé : le prix a dépassé le point de départ du mouvement."

    return {
        "direction": direction,
        "origin": origin,
        "endpoint": endpoint,
        "levels": levels,
        "zone_low": zone_low,
        "zone_high": zone_high,
        "leg_size": leg_size,
        "atr": atr,
    }, "Dernier swing confirmé et Fibonacci valide."



def build_manual_fibonacci(df, high_time, high_price, low_time, low_price):
    """Construit un Fibonacci à partir de deux points choisis par l'utilisateur."""
    data = df.reset_index(drop=True)
    high_price, low_price = float(high_price), float(low_price)
    if high_price <= low_price:
        return None, "Le sommet doit être supérieur au creux."
    atr = data.iloc[-1].get("ATR14")
    if pd.isna(atr) or float(atr) <= 0:
        return None, "ATR14 indisponible."

    hi = data.index[data["time"].astype(str) == str(high_time)].tolist()
    lo = data.index[data["time"].astype(str) == str(low_time)].tolist()
    if not hi or not lo:
        return None, "Les chandelles choisies ne sont plus disponibles."
    hi, lo = hi[0], lo[0]
    if hi == lo:
        return None, "Choisis deux chandelles différentes."

    high_point = {"index": hi, "type": "HIGH", "price": high_price, "time": data.loc[hi, "time"]}
    low_point = {"index": lo, "type": "LOW", "price": low_price, "time": data.loc[lo, "time"]}
    if lo < hi:
        origin, endpoint, direction = low_point, high_point, "BULL"
        levels = {r: high_price - (high_price - low_price) * r for r in (0.382, 0.5, 0.618, 0.786)}
        zone_low, zone_high = levels[0.618], levels[0.5]
    else:
        origin, endpoint, direction = high_point, low_point, "BEAR"
        levels = {r: low_price + (high_price - low_price) * r for r in (0.382, 0.5, 0.618, 0.786)}
        zone_low, zone_high = levels[0.5], levels[0.618]

    return {
        "direction": direction, "origin": origin, "endpoint": endpoint,
        "levels": levels, "zone_low": zone_low, "zone_high": zone_high,
        "leg_size": high_price - low_price, "atr": float(atr), "manual": True,
    }, "Fibonacci manuel actif."



def evaluate_fibonacci_setup(
    df,
    current_price=None,
    fib_override=None,
    max_close_extension_atr=0.50,
    max_live_extension_atr=0.35,
    max_trigger_wait_candles=3
):
    """Attend un rejet dans la zone, puis la cassure de son extrême par une
    chandelle clôturée avant de confirmer le signal.
    """
    fib, fib_message = (
        (fib_override, "Fibonacci manuel actif.")
        if fib_override is not None else find_last_fibonacci(df)
    )
    if fib is None:
        return {
            "state": "WAIT", "label": "⚪ En attente d'un Fibonacci valide",
            "color": "gray", "details": fib_message, "fib": None
        }

    direction = fib["direction"]
    zone_low, zone_high = fib["zone_low"], fib["zone_high"]
    data = df.reset_index(drop=True)
    if len(data) < 3:
        return {
            "state": "WAIT", "label": "⚪ En attente de confirmation",
            "color": "gray", "details": "Pas assez de chandelles clôturées.", "fib": fib
        }

    last = data.iloc[-1]
    live = float(current_price if current_price is not None else last["close"])
    endpoint_index = int(fib["endpoint"]["index"])
    touch_start = max(endpoint_index + 1, len(data) - 10)
    retest_candles = data.iloc[touch_start:]
    touch = any(
        float(row["low"]) <= zone_high and float(row["high"]) >= zone_low
        for _, row in retest_candles.iterrows()
    )
    in_zone = zone_low <= live <= zone_high

    if direction == "BULL":
        label = "🟢 ACHAT — CASSURE DU REJET CONFIRMÉE"
        wait_label = "🟡 Zone d'achat Fibonacci — attente du rejet et de la cassure"
        zone_name = "ZONE D'ACHAT"
        rejection_condition = lambda row: (
            float(row["close"]) > float(row["open"])
            and float(row["close"]) > zone_high
        )
        trigger_broken = lambda row, rejection: (
            float(row["close"]) > float(rejection["high"])
        )
        details = (
            "Après le retour dans la zone 50–61,8 %, le système attend une "
            "chandelle de rejet haussière, puis la clôture d'une chandelle "
            "au-dessus de son plus haut."
        )
    else:
        label = "🔴 VENTE — CASSURE DU REJET CONFIRMÉE"
        wait_label = "🟡 Zone de vente Fibonacci — attente du rejet et de la cassure"
        zone_name = "ZONE DE VENTE"
        rejection_condition = lambda row: (
            float(row["close"]) < float(row["open"])
            and float(row["close"]) < zone_low
        )
        trigger_broken = lambda row, rejection: (
            float(row["close"]) < float(rejection["low"])
        )
        details = (
            "Après le retour dans la zone 50–61,8 %, le système attend une "
            "chandelle de rejet baissière, puis la clôture d'une chandelle "
            "sous son plus bas."
        )

    # Cherche la dernière chandelle de rejet clôturée AVANT la dernière chandelle.
    # La dernière chandelle doit ensuite casser son extrême dans le bon sens.
    prior = data.iloc[touch_start:-1]
    rejection = None
    rejection_index = None
    for idx in range(len(prior) - 1, -1, -1):
        row = prior.iloc[idx]
        overlaps_zone = (
            float(row["low"]) <= zone_high and float(row["high"]) >= zone_low
        )
        if overlaps_zone and rejection_condition(row):
            rejection = row
            rejection_index = touch_start + idx
            break

    confirmed = False
    trigger_level = None
    candles_waited = None
    if rejection is not None:
        candles_waited = len(data) - 1 - rejection_index
        if 1 <= candles_waited <= max_trigger_wait_candles:
            confirmed = trigger_broken(last, rejection)
            trigger_level = (
                float(rejection["high"]) if direction == "BULL"
                else float(rejection["low"])
            )

    if confirmed:
        close_price = float(last["close"])
        if direction == "BEAR":
            close_extension = max(0.0, zone_low - close_price)
            live_extension = max(0.0, close_price - live)
        else:
            close_extension = max(0.0, close_price - zone_high)
            live_extension = max(0.0, live - close_price)

        atr_value = float(fib["atr"])
        close_limit = max_close_extension_atr * atr_value
        live_limit = max_live_extension_atr * atr_value
        too_late_reasons = []
        if close_extension > close_limit:
            too_late_reasons.append(
                f"La clôture de déclenchement est déjà à {close_extension:.5f} "
                f"de la zone (limite {close_limit:.5f})."
            )
        if live_extension > live_limit:
            too_late_reasons.append(
                f"Le prix en direct a prolongé le mouvement de {live_extension:.5f} "
                f"depuis la clôture (limite {live_limit:.5f})."
            )

        if too_late_reasons:
            return {
                "state": direction + "_TOO_LATE",
                "label": (
                    "⚠️ VENTE — CASSURE CONFIRMÉE, ENTRÉE TROP TARDIVE"
                    if direction == "BEAR"
                    else "⚠️ ACHAT — CASSURE CONFIRMÉE, ENTRÉE TROP TARDIVE"
                ),
                "color": "orange",
                "details": "La cassure est confirmée, mais le prix est déjà trop "
                           "éloigné. Attendre un nouveau retracement. "
                           + " ".join(too_late_reasons),
                "fib": fib, "zone_name": zone_name, "touch": touch,
                "in_zone": in_zone, "trigger_level": trigger_level
            }

        return {
            "state": direction + "_CONFIRMED", "label": label,
            "color": "green" if direction == "BULL" else "red",
            "details": (
                details + f" Niveau de déclenchement cassé : {trigger_level:.5f}. "
                "Filtre anti-retard validé."
            ),
            "fib": fib, "zone_name": zone_name, "touch": touch,
            "in_zone": in_zone, "trigger_level": trigger_level,
            "rejection_time": str(rejection["time"])
        }

    if rejection is not None and candles_waited is not None:
        if candles_waited <= max_trigger_wait_candles:
            extra = (
                f"Rejet détecté. Attente de la cassure de "
                f"{trigger_level if trigger_level is not None else (float(rejection['high']) if direction == 'BULL' else float(rejection['low'])):.5f}. "
                f"Chandelles écoulées : {candles_waited}/{max_trigger_wait_candles}."
            )
        else:
            extra = "Le rejet précédent a expiré sans cassure; attente d'un nouveau rejet. "
        return {
            "state": direction + "_WAIT", "label": wait_label,
            "color": "orange", "details": extra + details, "fib": fib,
            "zone_name": zone_name, "touch": touch, "in_zone": in_zone
        }

    if in_zone or touch:
        extra = (
            "Le prix est dans la zone. " if in_zone
            else "La zone a été visitée récemment. "
        )
        return {
            "state": direction + "_WAIT", "label": wait_label,
            "color": "orange", "details": extra + details, "fib": fib,
            "zone_name": zone_name, "touch": touch, "in_zone": in_zone
        }

    return {
        "state": direction + "_TRACKING",
        "label": "🔵 Fibonacci valide — surveillance du retracement",
        "color": "blue",
        "details": f"{zone_name} : le prix n'a pas encore atteint la zone 50–61,8 %. " + details,
        "fib": fib, "zone_name": zone_name, "touch": False, "in_zone": in_zone
    }


def build_trade_plan(setup, current_price, min_rr=1.5, stop_buffer_atr=0.20):
    """Construit un plan indicatif uniquement après confirmation et filtre anti-retard.

    Entrée = prix médian courant observé dans la chandelle en formation.
    SL = au-delà du bord externe de la zone Fibonacci + marge ATR.
    TP = extrémité du swing initial. Le plan est rejeté si le RR est inférieur
    au minimum ou si le prix a déjà dépassé la cible.
    """
    if setup.get("state") not in ("BULL_CONFIRMED", "BEAR_CONFIRMED"):
        return None, "Aucun plan : attendre une confirmation Fibonacci non tardive."

    fib = setup.get("fib")
    if not fib or current_price is None:
        return None, "Aucun plan : prix courant ou Fibonacci indisponible."

    entry = float(current_price)
    atr = float(fib["atr"])
    buffer = atr * stop_buffer_atr
    target = float(fib["endpoint"]["price"])

    if fib["direction"] == "BEAR":
        stop = float(fib["zone_high"]) + buffer
        if not (target < entry < stop):
            return None, "Aucun plan : le prix est déjà au niveau de la cible ou la structure risque/rendement est invalide."
        risk = stop - entry
        reward = entry - target
        side = "VENTE"
    else:
        stop = float(fib["zone_low"]) - buffer
        if not (stop < entry < target):
            return None, "Aucun plan : le prix est déjà au niveau de la cible ou la structure risque/rendement est invalide."
        risk = entry - stop
        reward = target - entry
        side = "ACHAT"

    rr_value = reward / risk if risk > 0 else 0.0
    if rr_value < min_rr:
        return None, (
            f"Aucun plan proposé : le rendement jusqu'à l'extrémité du swing "
            f"n'offre que 1:{rr_value:.2f}, sous le minimum de 1:{min_rr:.2f}."
        )

    return {
        "side": side,
        "entry": entry,
        "stop_loss": stop,
        "take_profit": target,
        "rr": rr_value,
        "risk_distance": risk,
        "reward_distance": reward,
        "buffer": buffer,
    }, "Plan indicatif calculé à partir du prix observé et du swing Fibonacci."


# ALERT STATE: no repeated alert every minute for the same active setup
ALERT_HISTORY_FILE = Path(__file__).resolve().parent / "fib_alert_history.csv"

ALERT_COLUMNS = [
    "Heure alerte", "Heure chandelle", "Instrument", "Timeframe",
    "Direction", "Etat", "Zone basse", "Zone haute",
    "Entree", "Stop-loss", "Take-profit", "R_R",
    "Prix au signal", "Mode Fibonacci", "Resultat", "Notes"
]


def append_alert_history(record):
    """Ajoute une alerte au CSV local pour permettre sa consultation et son export."""
    row = {column: record.get(column, "") for column in ALERT_COLUMNS}
    one_row = pd.DataFrame([row], columns=ALERT_COLUMNS)
    try:
        if ALERT_HISTORY_FILE.exists():
            one_row.to_csv(ALERT_HISTORY_FILE, mode="a", header=False, index=False, encoding="utf-8-sig")
        else:
            one_row.to_csv(ALERT_HISTORY_FILE, index=False, encoding="utf-8-sig")
        return True
    except Exception as exc:
        st.warning(f"Impossible d'enregistrer le journal CSV local : {exc}")
        return False


def load_alert_history():
    """Lit le journal CSV local; retourne un tableau vide s'il n'existe pas."""
    if not ALERT_HISTORY_FILE.exists():
        return pd.DataFrame(columns=ALERT_COLUMNS)
    try:
        history = pd.read_csv(ALERT_HISTORY_FILE, encoding="utf-8-sig")
        for column in ALERT_COLUMNS:
            if column not in history.columns:
                history[column] = ""
        return history[ALERT_COLUMNS]
    except Exception as exc:
        st.warning(f"Impossible de lire le journal CSV local : {exc}")
        return pd.DataFrame(columns=ALERT_COLUMNS)


def process_fibonacci_alert(pair, timeframe, setup, candle_time, current_price, trade_plan):
    """Phase 1: alerte la configuration, mais n'ouvre aucun trade."""
    if setup.get("state") not in ("BULL_CONFIRMED", "BEAR_CONFIRMED"):
        return
    if not trade_plan or not setup.get("fib") or setup.get("trigger_level") is None:
        return

    fib = setup["fib"]
    bullish = setup["state"] == "BULL_CONFIRMED"
    direction = "ACHAT" if bullish else "VENTE"
    fib_mode = "MANUEL" if fib.get("manual") else "AUTOMATIQUE"
    signal_key = _signal_identity(pair, timeframe, fib, fib_mode)
    alert_state_key = f"fib_alerted_setup_{pair}_{timeframe}"
    if st.session_state.get(alert_state_key) == signal_key:
        return

    if not supabase_configured():
        st.error("Alerte non envoyée : Supabase est nécessaire pour conserver le retest en attente de façon fiable.")
        return

    try:
        saved, message = create_pending_setup(
            pair, timeframe, setup, candle_time, trade_plan, fib_mode
        )
    except Exception as exc:
        st.error(f"Erreur Supabase — sauvegarde de la configuration : {exc}")
        return

    if not saved:
        st.info(f"Supabase : {message}")
        st.session_state[alert_state_key] = signal_key
        return

    zone_low = float(fib["zone_low"])
    zone_high = float(fib["zone_high"])
    trigger = float(setup["trigger_level"])
    now_text = datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
    subject = f"{'🟡 Configuration ACHAT' if bullish else '🟡 Configuration VENTE'} Fibonacci — {pair} {timeframe}"
    body = (
        f"Configuration Fibonacci détectée sur {pair} en {timeframe}.\n"
        f"Direction : {direction}.\n"
        f"Zone Fibonacci 50–61,8 % : {zone_low:.5f} à {zone_high:.5f}.\n"
        f"Niveau de cassure à retester : {trigger:.5f}.\n"
        f"Prix observé lors du signal : {float(current_price):.5f}.\n"
        f"Dernière chandelle clôturée : {candle_time}.\n\n"
        "ATTENTION : ce courriel est une alerte de configuration, PAS une autorisation d'entrée.\n"
        "Attendre le retour au niveau de cassure, puis une nouvelle chandelle M5/M30 de confirmation.\n"
        "Une deuxième alerte sera envoyée seulement si l'entrée reste valide. Aucun ordre automatique."
    )
    record = {
        "Heure alerte": now_text,
        "Heure chandelle": candle_time,
        "Instrument": pair,
        "Timeframe": timeframe,
        "Direction": direction,
        "Etat": "CONFIGURATION — ATTENTE RETEST",
        "Zone basse": zone_low,
        "Zone haute": zone_high,
        "Entree": "",
        "Stop-loss": "",
        "Take-profit": "",
        "R_R": "",
        "Prix au signal": current_price,
        "Mode Fibonacci": fib_mode,
        "Resultat": "",
        "Notes": f"Niveau à retester : {trigger:.5f}. Aucun trade ouvert.",
    }
    append_alert_history(record)
    st.session_state.setdefault("fib_new_alerts", [])
    st.session_state["fib_new_alerts"].append({
        "Heure": now_text,
        "Instrument": pair,
        "Timeframe": timeframe,
        "Signal": subject,
        "Zone": f"{zone_low:.5f} – {zone_high:.5f}",
        "Entrée": "En attente du retest",
        "SL": "—",
        "TP": "—",
        "R/R": "—",
    })

    if not mute_alerts:
        play_voice_alert(VOICE_STRONG_BULL if bullish else VOICE_STRONG_BEAR)
    if email_alerts_enabled:
        sent, status = send_email_alert(subject, body)
        if not sent:
            st.warning(status)
    st.success("Configuration enregistrée : attente du retest avant toute entrée.")
    st.session_state[alert_state_key] = signal_key


def process_pending_entries(pair, timeframe, closed_df, current_price, m30_context=None):
    """Phase 2: attend le retest puis une nouvelle clôture dans le sens du trade."""
    if not supabase_configured() or closed_df.empty:
        return

    try:
        pending_setups = load_pending_setups(pair, timeframe)
        if timeframe == "M5" and pending_setups and (
            not m30_context or m30_context.get("bias") not in ("BULL", "BEAR")
        ):
            for pending in pending_setups:
                update_pending_setup(
                    pending["id"], json.loads(pending.get("notes") or "{}"),
                    status="EXPIRED",
                    note="Configuration M5 annulée : le contexte directionnel M30 est neutre ou indisponible."
                )
            st.info(f"{pair} M5 : configuration en attente annulée — contexte M30 non directionnel.")
            return
    except Exception as exc:
        st.warning(f"Erreur Supabase — lecture des configurations en attente : {exc}")
        return

    for pending in pending_setups:
        try:
            meta = json.loads(pending.get("notes") or "{}")
            if meta.get("phase") != "WAIT_RETEST":
                continue

            direction = pending["direction"]
            if timeframe == "M5" and m30_context.get("bias") != direction:
                update_pending_setup(
                    pending["id"], meta, status="EXPIRED",
                    note=("Configuration M5 annulée : le biais M30 n'est plus aligné "
                          "avec la direction du setup avant la confirmation.")
                )
                st.info(f"{pair} M5 : configuration annulée — biais M30 opposé ou neutre.")
                continue
            trigger = float(meta["trigger_level"])
            atr = float(meta["atr"])
            tolerance = float(meta.get("retest_tolerance_atr", 0.15)) * atr
            max_extension = float(meta.get("max_entry_extension_atr", 0.25)) * atr
            max_wait = int(meta.get("max_wait_candles", 6))
            stop = float(pending["stop_loss"])
            last_processed = pd.to_datetime(meta["last_processed_candle"], utc=True)

            candles = closed_df.copy()
            candles["_utc_time"] = pd.to_datetime(candles["time"], utc=True)
            later = candles[candles["_utc_time"] > last_processed]
            if later.empty:
                continue

            completed_trade = False
            expired_note = None
            for _, candle in later.iterrows():
                high, low = float(candle["high"]), float(candle["low"])
                open_price, close = float(candle["open"]), float(candle["close"])
                candle_stamp = pd.Timestamp(candle["time"]).isoformat()
                meta["last_processed_candle"] = candle_stamp
                meta["bars_elapsed"] = int(meta.get("bars_elapsed", 0)) + 1
                if meta["bars_elapsed"] > max_wait:
                    expired_note = "Configuration expirée : délai maximal de retest et de confirmation dépassé."
                    break

                # Invalidation avant entrée : si le stop théorique est touché, on annule.
                stop_touched = (low <= stop) if direction == "BULL" else (high >= stop)
                if stop_touched:
                    expired_note = "Configuration annulée : le stop théorique a été touché avant l'entrée confirmée."
                    break

                # Le retest doit revenir près du niveau de cassure.
                if not meta.get("retest_seen"):
                    retest_band_low = trigger - tolerance
                    retest_band_high = trigger + tolerance
                    overlaps_retest = low <= retest_band_high and high >= retest_band_low
                    if overlaps_retest:
                        meta["retest_seen"] = True
                        meta["retest_high"] = high
                        meta["retest_low"] = low
                        meta["retest_time"] = candle_stamp
                    if meta["bars_elapsed"] >= max_wait and not meta.get("retest_seen"):
                        expired_note = "Configuration expirée : aucun retest du niveau de cassure dans le délai prévu."
                        break
                    # Confirmation obligatoire sur une chandelle ultérieure.
                    continue

                # La chandelle de confirmation doit être postérieure à celle du retest.
                if direction == "BULL":
                    confirmed = close > open_price and close > float(meta["retest_high"])
                    extension = max(0.0, close - trigger)
                else:
                    confirmed = close < open_price and close < float(meta["retest_low"])
                    extension = max(0.0, trigger - close)

                if confirmed:
                    if extension > max_extension:
                        expired_note = (
                            "Configuration annulée : la confirmation est arrivée trop loin du niveau de retest; "
                            "aucune entrée tardive n'est autorisée."
                        )
                        break

                    fib = {
                        "direction": direction,
                        "zone_low": float(meta["zone_low"]),
                        "zone_high": float(meta["zone_high"]),
                        "atr": atr,
                        "endpoint": {"price": float(meta["endpoint_price"])},
                        "origin": {"price": float(meta["origin_price"])},
                        "manual": bool(meta.get("manual", False)),
                    }
                    setup = {"state": direction + "_CONFIRMED", "fib": fib}
                    # Utilise la clôture de la chandelle de confirmation, pas un prix live potentiellement éloigné.
                    final_plan, plan_message = build_trade_plan(setup, close)
                    if not final_plan:
                        expired_note = f"Configuration annulée après retest : {plan_message}"
                        break

                    activate_pending_setup(pending, candle, final_plan)
                    now_text = datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
                    direction_label = "ACHAT" if direction == "BULL" else "VENTE"
                    subject = f"{'🟢 ENTRÉE ACHAT' if direction == 'BULL' else '🔴 ENTRÉE VENTE'} confirmée après retest — {pair} {timeframe}"
                    body = (
                        f"ENTRÉE POTENTIELLE CONFIRMÉE après retest sur {pair} en {timeframe}.\n"
                        f"Direction : {direction_label}.\n"
                        f"Entrée indicative (clôture de confirmation) : {final_plan['entry']:.5f}.\n"
                        f"Stop-loss : {final_plan['stop_loss']:.5f}.\n"
                        f"Take-profit : {final_plan['take_profit']:.5f}.\n"
                        f"Ratio R/R : 1:{final_plan['rr']:.2f}.\n"
                        f"Niveau retesté : {trigger:.5f}.\n"
                        f"Chandelle de confirmation : {candle_stamp}.\n\n"
                        "Le retest et la reprise ont été confirmés sur le même timeframe que le signal initial. "
                        "Valider le prix disponible avant toute exécution. Aucun ordre automatique n'est envoyé."
                    )
                    record = {
                        "Heure alerte": now_text,
                        "Heure chandelle": candle_stamp,
                        "Instrument": pair,
                        "Timeframe": timeframe,
                        "Direction": direction_label,
                        "Etat": "ENTREE CONFIRMEE APRES RETEST",
                        "Zone basse": meta["zone_low"],
                        "Zone haute": meta["zone_high"],
                        "Entree": final_plan["entry"],
                        "Stop-loss": final_plan["stop_loss"],
                        "Take-profit": final_plan["take_profit"],
                        "R_R": final_plan["rr"],
                        "Prix au signal": close,
                        "Mode Fibonacci": meta.get("fib_mode", "AUTOMATIQUE"),
                        "Resultat": "",
                        "Notes": "Retest puis confirmation sur chandelle clôturée; trade virtuel activé.",
                    }
                    append_alert_history(record)
                    st.session_state.setdefault("fib_new_alerts", [])
                    st.session_state["fib_new_alerts"].append({
                        "Heure": now_text,
                        "Instrument": pair,
                        "Timeframe": timeframe,
                        "Signal": subject,
                        "Zone": f"{float(meta['zone_low']):.5f} – {float(meta['zone_high']):.5f}",
                        "Entrée": f"{final_plan['entry']:.5f}",
                        "SL": f"{final_plan['stop_loss']:.5f}",
                        "TP": f"{final_plan['take_profit']:.5f}",
                        "R/R": f"1:{final_plan['rr']:.2f}",
                    })
                    if not mute_alerts:
                        play_voice_alert(VOICE_STRONG_BULL if direction == "BULL" else VOICE_STRONG_BEAR)
                    if email_alerts_enabled:
                        sent, status = send_email_alert(subject, body)
                        if not sent:
                            st.warning(status)
                    st.success(f"{pair} {timeframe} : entrée confirmée après retest. Trade virtuel activé.")
                    completed_trade = True
                    break

                if meta["bars_elapsed"] >= max_wait:
                    expired_note = "Configuration expirée : retest observé, mais aucune reprise confirmée dans le délai prévu."
                    break

            if completed_trade:
                continue
            if expired_note:
                update_pending_setup(pending["id"], meta, status="EXPIRED", note=expired_note)
                st.info(f"{pair} {timeframe} : {expired_note}")
            else:
                update_pending_setup(pending["id"], meta)
                if meta.get("retest_seen"):
                    st.info(
                        f"{pair} {timeframe} : retest détecté à {trigger:.5f}; "
                        "attente d'une nouvelle chandelle clôturée de confirmation."
                    )
                else:
                    st.info(
                        f"{pair} {timeframe} : configuration en attente du retest de {trigger:.5f}."
                    )
        except Exception as exc:
            st.warning(f"Erreur de suivi du retest {pair} {timeframe} : {exc}")


# MAIN DASHBOARD — en-tête visuel uniquement
now_ny = datetime.now(pytz.timezone("America/New_York"))
st.markdown(
    f"""
    <div style="display:flex;align-items:center;justify-content:space-between;gap:18px;
      padding:18px 22px;margin:0 0 14px 0;border:1px solid #1b4d78;border-radius:18px;
      background:linear-gradient(105deg,rgba(10,39,68,.98),rgba(5,17,32,.98));
      box-shadow:0 12px 30px rgba(0,0,0,.22);">
      <div>
        <div style="font-size:27px;font-weight:800;color:#f3f8ff;letter-spacing:-.8px;">
          <span style="color:#18a8ff;">◆</span> Trading Monitor <span style="color:#22b8ff;">— Smart Money</span>
        </div>
        <div style="font-size:13px;color:#9bb9d8;margin-top:4px;letter-spacing:1.2px;">ANALYSE&nbsp;&nbsp; • &nbsp;&nbsp;CONFIRMATION&nbsp;&nbsp; • &nbsp;&nbsp;OPPORTUNITÉ</div>
      </div>
      <div style="text-align:right;min-width:170px;">
        <div style="display:inline-block;padding:7px 13px;border-radius:30px;
          border:1px solid rgba(32,214,138,.45);background:rgba(32,214,138,.10);
          color:#45e6a0;font-weight:700;font-size:13px;">● MODE SURVEILLANCE</div>
        <div style="color:#9bb9d8;font-size:12px;margin-top:7px;">{now_ny.strftime('%d %B %Y — %H:%M:%S')} NY&nbsp; • &nbsp;Actualisation 60 s</div>
      </div>
    </div>
    """, unsafe_allow_html=True
)
st.markdown("""
<style>
/* Contraste renforcé pour les libellés, options et chiffres */
[data-testid="stMetricLabel"] p { color: #c8d7e8 !important; font-weight: 700 !important; }
[data-testid="stMetricValue"] { color: #ffffff !important; font-weight: 750 !important; }
[data-testid="stRadio"] label, [data-testid="stRadio"] p { color: #edf4fb !important; }
[data-testid="stRadio"] [role="radiogroup"] label { color: #edf4fb !important; }
</style>
""", unsafe_allow_html=True)

summary = st.columns(4)
selected_pairs = list(dict.fromkeys(config["pair"] for config in instruments_config))
summary[0].metric(
    "INSTRUMENTS SUIVIS", str(len(selected_pairs)),
    " • ".join(pair_labels.get(pair, pair) for pair in selected_pairs)
)
summary[1].metric("UNITÉS DE TEMPS", "M30 / M5", "Analyse + exécution")
summary[2].metric("DONNÉES", "OANDA", "Actualisation automatique")
summary[3].metric("MODE", "Surveillance", "Aucun ordre automatique")
st.caption(
    "Alertes basées sur le dernier swing confirmé, le retracement Fibonacci "
    "50–61,8 %, un rejet puis la cassure de son extrême, avec filtre anti-entrée tardive. "
    "Une deuxième confirmation après retest est exigée avant toute entrée."
)

for config in instruments_config:
    pair = config["pair"]
    timeframe = config["timeframe"]
    st.markdown("---")

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

        if supabase_configured():
            try:
                monitor_virtual_trades(pair, timeframe, closed_df)
            except Exception as exc:
                st.warning(f"Erreur Supabase — suivi des trades virtuels ({pair}) : {exc}")

        df = add_indicators(closed_df)
        m30_context = get_m30_market_context(pair) if timeframe == "M5" else None
        # Utilise la dernière chandelle reçue (potentiellement en formation) comme prix courant.
        # Cela évite une requête M1 OANDA supplémentaire pour chaque instrument.
        current_price = float(raw_df.iloc[-1]["close"])
        last = df.iloc[-1]

        # Carte de contrôle regroupant instrument, prix et méthode Fibonacci.
        with st.container(border=True):
            st.markdown(
                f"""<div style="background:#14243a;padding:12px 16px;border-radius:10px;
                border-left:5px solid #35b6e8;margin-bottom:12px;">
                <div style="color:#f4f7fb;font-size:20px;font-weight:700;">
                {pair_labels.get(pair, pair)} <span style="color:#9fc5df;font-size:15px;">— {timeframe}</span>
                </div><div style="color:#c6d5e4;font-size:12px;margin-top:3px;">SURVEILLANCE DU MARCHÉ</div>
                </div>""",
                unsafe_allow_html=True
            )
            price_col, mode_col = st.columns([1, 2])
            with price_col:
                price_decimals = 2 if ("BTC" in pair.upper() or "XAU" in pair.upper() or "SPX" in pair.upper()) else 5
                formatted_price = f"{current_price:,.{price_decimals}f}"
                st.metric(label="PRIX ACTUEL · OANDA", value=formatted_price)
            with mode_col:
                fib_mode = st.radio(
                    "MÉTHODE FIBONACCI", ["Automatique", "Manuel"],
                    horizontal=True, key=f"fib_mode_{pair}_{timeframe}",
                    help="En mode manuel, choisis les chandelles du sommet et du creux, puis ajuste leurs prix."
                )
        fib_override = None
        if fib_mode == "Manuel":
            st.caption(
                "Choisis la chandelle du sommet et celle du creux. Ajuste ensuite leurs prix. "
                "L'ordre chronologique détermine automatiquement le sens du swing."
            )
            time_options = [str(value) for value in df["time"].tolist()]
            time_labels = {
                str(value): pd.Timestamp(value).strftime("%Y-%m-%d %H:%M NY")
                for value in df["time"].tolist()
            }
            hi_default, lo_default = int(df["high"].idxmax()), int(df["low"].idxmin())
            hi_t_key, lo_t_key = f"fib_hi_t_{pair}_{timeframe}", f"fib_lo_t_{pair}_{timeframe}"
            hi_p_key, lo_p_key = f"fib_hi_p_{pair}_{timeframe}", f"fib_lo_p_{pair}_{timeframe}"

            if hi_t_key not in st.session_state:
                st.session_state[hi_t_key] = str(df.loc[hi_default, "time"])
            if lo_t_key not in st.session_state:
                st.session_state[lo_t_key] = str(df.loc[lo_default, "time"])
            if hi_p_key not in st.session_state:
                st.session_state[hi_p_key] = float(df.loc[hi_default, "high"])
            if lo_p_key not in st.session_state:
                st.session_state[lo_p_key] = float(df.loc[lo_default, "low"])

            def update_hi_price():
                selected = st.session_state[hi_t_key]
                row = df[df["time"].astype(str) == selected].iloc[0]
                st.session_state[hi_p_key] = float(row["high"])

            def update_lo_price():
                selected = st.session_state[lo_t_key]
                row = df[df["time"].astype(str) == selected].iloc[0]
                st.session_state[lo_p_key] = float(row["low"])

            c_hi, c_lo = st.columns(2)
            with c_hi:
                st.selectbox("Chandelle du sommet (0)", time_options,
                             format_func=lambda v: time_labels.get(v, v),
                             key=hi_t_key, on_change=update_hi_price)
                st.number_input("Prix du sommet", key=hi_p_key, format="%.5f")
            with c_lo:
                st.selectbox("Chandelle du creux (1)", time_options,
                             format_func=lambda v: time_labels.get(v, v),
                             key=lo_t_key, on_change=update_lo_price)
                st.number_input("Prix du creux", key=lo_p_key, format="%.5f")

            fib_override, manual_status = build_manual_fibonacci(
                df, st.session_state[hi_t_key], st.session_state[hi_p_key],
                st.session_state[lo_t_key], st.session_state[lo_p_key]
            )
            if fib_override is None:
                st.warning(manual_status)

        if fib_mode == "Manuel" and fib_override is None:
            setup = {
                "state": "WAIT",
                "label": "⚪ Fibonacci manuel à corriger",
                "color": "gray",
                "details": "Aucun signal calculé : vérifie les deux chandelles et les prix des ancrages manuels.",
                "fib": None
            }
        else:
            setup = evaluate_fibonacci_setup(df, current_price, fib_override=fib_override)

        if (timeframe == "M5" and setup.get("state") in ("BULL_CONFIRMED", "BEAR_CONFIRMED")):
            required_bias = "BULL" if setup["state"] == "BULL_CONFIRMED" else "BEAR"
            if not m30_context or m30_context.get("bias") != required_bias:
                setup = {
                    **setup,
                    "state": "M30_FILTERED",
                    "label": "⚪ CONFIGURATION M5 BLOQUÉE — CONTEXTE M30 NON ALIGNÉ",
                    "color": "gray",
                    "details": (
                        setup.get("details", "") + " Filtre M30 : "
                        + (m30_context.get("details", "Contexte M30 indisponible.") if m30_context else "Contexte M30 indisponible.")
                        + " Aucune configuration M5 n'est enregistrée."
                    )
                }

        candle_time = last["time"].strftime("%Y-%m-%d %H:%M NY")
        trade_plan, trade_message = build_trade_plan(setup, current_price)


        process_fibonacci_alert(
            pair, timeframe, setup, candle_time, current_price, trade_plan
        )
        process_pending_entries(pair, timeframe, closed_df, current_price, m30_context)

        st.markdown(
            f"<h4 style='color:{setup['color']};'>{setup['label']}</h4>",
            unsafe_allow_html=True
        )
        st.write(setup["details"])
        st.caption(f"Signal calculé sur la dernière chandelle clôturée : {candle_time}")

        if timeframe == "M5" and m30_context:
            context_label = {"BULL": "HAUSSIER", "BEAR": "BAISSIER", "NEUTRAL": "NEUTRE"}.get(m30_context["bias"], "N/D")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("BIAIS M30", context_label)
            col2.metric("FORCE M30", m30_context.get("strength", "N/D"))
            col3.metric("ADX M30", "N/D" if m30_context.get("adx") is None else f"{m30_context['adx']:.1f}")
            col4.metric("ADX M5", "N/D" if pd.isna(last["ADX14"]) else f"{last['ADX14']:.1f}")
            st.caption(m30_context.get("details", ""))
            st.caption("Filtre actif : une configuration M5 doit être dans le même sens que le biais M30.")
        else:
            col1, col2 = st.columns(2)
            col1.metric("ADX14", "N/D" if pd.isna(last["ADX14"]) else f"{last['ADX14']:.1f}")
            col2.metric("Fibonacci", "Valide" if setup.get("fib") else "En attente")
        if setup.get("fib"):
            fib = setup["fib"]
            zone_name = setup.get("zone_name", "ZONE DE RETRACEMENT")
            st.write(f"**{zone_name} Fibonacci 50–61,8 % :** {fib['zone_low']:.5f} – {fib['zone_high']:.5f}")
            st.write(f"**Origine du swing :** {fib['origin']['price']:.5f}  |  **Extrémité :** {fib['endpoint']['price']:.5f}")

        st.markdown("#### Plan de trade Fibonacci")
        if trade_plan:
            st.success(
                f"PLAN INDICATIF {trade_plan['side']} — "
                f"R/R 1:{trade_plan['rr']:.2f}"
            )
            plan_c1, plan_c2, plan_c3 = st.columns(3)
            plan_c1.metric("Entrée indicative", f"{trade_plan['entry']:.5f}")
            plan_c2.metric("Stop-loss", f"{trade_plan['stop_loss']:.5f}")
            plan_c3.metric("Take-profit", f"{trade_plan['take_profit']:.5f}")
            st.caption(
                f"SL placé au-delà de la zone avec une marge de 0,20 ATR. "
                f"TP placé à l'extrémité du swing. Risque : "
                f"{trade_plan['risk_distance']:.5f} | Récompense : "
                f"{trade_plan['reward_distance']:.5f}. "
                "À valider manuellement; aucun ordre n'est envoyé."
            )
        else:
            st.info(trade_message)

        # CHART
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            row_heights=[0.7, 0.3], vertical_spacing=0.05
        )

        # Ligne Close des chandelles clôturées, prolongée jusqu'au prix actuel.
        # Le dernier point correspond à la chandelle OANDA encore en formation.
        live_time = None
        close_x = df["time"].tolist()
        close_y = df["close"].astype(float).tolist()

        if not raw_df.empty and not bool(raw_df.iloc[-1]["complete"]):
            live_time = pd.to_datetime(
                raw_df.iloc[-1]["time"], utc=True
            ).tz_convert("America/New_York")
            live_price = float(raw_df.iloc[-1]["close"])

            close_x.append(live_time)
            close_y.append(live_price)

        fig.add_trace(
            go.Scatter(
                x=close_x,
                y=close_y,
                name="Close",
                line=dict(color="#B8C7D9", dash="dot", width=2),
                hoverinfo="none"
            ),
            row=1, col=1
        )

        if show_emas:
            for ema_name, ema_color, ema_dash in [
                ("EMA50", "#35B6FF", "solid"),
                ("EMA100", "#B8C7D9", "dash"),
                ("EMA200", "#FFB454", "solid")
            ]:
                fig.add_trace(
                    go.Scatter(x=df["time"], y=df[ema_name], name=ema_name,
                               line=dict(color=ema_color, dash=ema_dash, width=2), hoverinfo="none"), row=1, col=1
                )
        if setup.get("fib"):
            fib = setup["fib"]
            x0 = fib["origin"]["time"]
            x1 = live_time if live_time is not None else df["time"].iloc[-1]

            # Affichage classique : seulement les niveaux 0, 0.5 et 1.
            # Les calculs internes du setup (zone 50–61,8 %, signaux et plans)
            # restent inchangés.
            visible_levels = [
                (0.0, float(fib["endpoint"]["price"]), "Fibonacci 0", "#35B6FF", "solid", 2),
                (0.5, float(fib["levels"][0.5]), "Fibonacci 0.5", "#FFC857", "solid", 3),
                (1.0, float(fib["origin"]["price"]), "Fibonacci 1", "#42E8D4", "solid", 2),
            ]

            for ratio, level, level_name, fib_color, fib_dash, fib_width in visible_levels:
                fig.add_trace(go.Scatter(
                    x=[x0, x1], y=[level, level], mode="lines",
                    name=level_name,
                    line=dict(color=fib_color, width=fib_width, dash=fib_dash),
                    hoverinfo="none"
                ), row=1, col=1)
            if fib.get("manual"):
                fig.add_trace(go.Scatter(
                    x=[fib["origin"]["time"], fib["endpoint"]["time"]],
                    y=[fib["origin"]["price"], fib["endpoint"]["price"]],
                    mode="markers+text",
                    text=["Ancrage 1", "Ancrage 0"],
                    textposition="top center",
                    marker=dict(size=11, color="white", line=dict(color="black", width=2)),
                    name="Ancrages manuels",
                    hoverinfo="none"
                ), row=1, col=1)

        fig.add_trace(
            go.Bar(
                x=df["time"], y=df["volume"], name="Volume",
                marker_color="rgba(53,182,255,0.48)", hoverinfo="none"
            ), row=2, col=1
        )
        # Palette graphique harmonisée avec le thème bleu nuit du Dashboard.
        fig.update_layout(
            height=700,
            template="plotly_dark",
            paper_bgcolor="#071426",
            plot_bgcolor="#091B30",
            font=dict(family="Inter, Arial, sans-serif", color="#DCE8F5", size=12),
            margin=dict(l=20, r=20, t=55, b=20),
            legend=dict(
                orientation="h", y=1.08, x=0,
                bgcolor="rgba(7,20,38,0.72)",
                font=dict(color="#DCE8F5", size=11)
            ),
            hovermode="x",
            hoverlabel=dict(
                bgcolor="#102A45", bordercolor="#247DB5",
                font=dict(color="#F4F8FC")
            )
        )
        fig.update_xaxes(
            showgrid=True, gridcolor="rgba(76,115,153,0.20)",
            zeroline=False, showline=True, linecolor="#29445F",
            tickfont=dict(color="#AFC2D8"),
            title_font=dict(color="#AFC2D8")
        )
        fig.update_yaxes(
            showgrid=True, gridcolor="rgba(76,115,153,0.20)",
            zeroline=False, showline=True, linecolor="#29445F",
            tickfont=dict(color="#AFC2D8"),
            title_font=dict(color="#AFC2D8")
        )
        # Panneau fixe de lecture : les valeurs suivent la chandelle survolée,
        # sans afficher l'info-bulle Plotly flottante au milieu du graphique.
        chart_id = "chart_" + hashlib.md5(f"{pair}_{timeframe}".encode("utf-8")).hexdigest()[:10]
        chart_html = fig.to_html(
            full_html=False,
            include_plotlyjs="cdn",
            config={"responsive": True, "displaylogo": False},
            div_id=chart_id
        )
        price_decimals = 2 if any(token in pair.upper() for token in ("BTC", "XAU", "SPX")) else 5
        panel_script = f"""
        <style>
          html, body {{ margin:0; padding:0; background:#071426; overflow:hidden; }}
          .chart-wrap {{ position:relative; width:100%; }}
          .hover-readout {{ position:absolute; z-index:20; top:66px; left:88px;
            min-width:205px; max-width:260px; padding:10px 12px;
            border:1px solid #2873a8; border-radius:9px;
            background:rgba(7,20,38,.94); color:#edf6ff;
            box-shadow:0 5px 18px rgba(0,0,0,.28);
            font:12px Inter,Arial,sans-serif; pointer-events:none; }}
          .hover-readout .heading {{ color:#70caff; font-weight:700; margin-bottom:6px; }}
          .hover-readout .row {{ display:flex; justify-content:space-between; gap:16px;
            padding:2px 0; white-space:nowrap; }}
          .hover-readout .muted {{ color:#9db8d4; }}
        </style>
        <div class="chart-wrap">
          <div class="hover-readout" id="readout_{chart_id}">
            <div class="heading">LECTURE DE LA CHANDELLE</div>
            <div class="muted">Survole une chandelle pour afficher ses valeurs ici.</div>
          </div>
          {chart_html}
        </div>
        <script>
        (function() {{
          const chart = document.getElementById("{chart_id}");
          const panel = document.getElementById("readout_{chart_id}");
          if (!chart || !panel || !chart.on) return;
          const decimals = {price_decimals};
          const order = ["Close", "EMA50", "EMA100", "EMA200"];
          const colors = {{"Close":"#B8C7D9", "EMA50":"#35B6FF", "EMA100":"#B8C7D9", "EMA200":"#FFB454"}};
          chart.on("plotly_hover", function(ev) {{
            if (!ev || !ev.points || !ev.points.length) return;
            const values = {{}};
            let x = ev.points[0].x;
            ev.points.forEach(function(pt) {{
              const name = (pt.data && pt.data.name) || "";
              if (order.includes(name) && Number.isFinite(Number(pt.y))) values[name] = Number(pt.y);
            }});
            const date = new Date(x);
            const dateText = Number.isNaN(date.getTime()) ? String(x) :
              new Intl.DateTimeFormat("fr-CA", {{timeZone:"America/New_York", dateStyle:"medium", timeStyle:"short"}}).format(date) + " NY";
            let html = '<div class="heading">' + dateText + '</div>';
            order.forEach(function(name) {{
              if (values[name] !== undefined) {{
                html += '<div class="row"><span style="color:' + colors[name] + '">' + name + '</span><strong>' +
                  values[name].toLocaleString("en-US", {{minimumFractionDigits:decimals, maximumFractionDigits:decimals}}) + '</strong></div>';
              }}
            }});
            if (Object.keys(values).length) panel.innerHTML = html;
          }});
        }})();
        </script>
        """
        components.html(panel_script, height=740, scrolling=False)

    except Exception as exc:
        st.error(f"Erreur pour {pair} ({timeframe}) : {exc}")


# SUIVI DES TRADES VIRTUELS SUPABASE
st.markdown("---")
st.subheader("📊 Suivi des trades virtuels Fibonacci")
if not supabase_configured():
    st.warning("Connexion Supabase non disponible. Vérifie les deux secrets dans Streamlit.")
else:
    try:
        virtual_trades = load_virtual_trade_stats()
        virtual_df = pd.DataFrame(virtual_trades)
        if virtual_df.empty:
            st.info("Aucun trade virtuel enregistré pour le moment.")
        else:
            counts = virtual_df["status"].value_counts()
            pending_count = int(counts.get("PENDING", 0))
            opened = int(counts.get("OPEN", 0))
            wins = int(counts.get("WIN", 0))
            losses = int(counts.get("LOSS", 0))
            ambiguous = int(counts.get("AMBIGUOUS", 0))
            expired = int(counts.get("EXPIRED", 0))
            completed = wins + losses
            win_rate = (wins / completed * 100) if completed else 0.0

            # Conversion des résultats en R vers des dollars théoriques.
            # Le risque utilisé est celui configuré dans la barre latérale.
            risk_per_trade = risk_amount
            virtual_df["result_r"] = pd.to_numeric(
                virtual_df["result_r"], errors="coerce"
            )
            closed_mask = virtual_df["status"].isin(["WIN", "LOSS"])
            virtual_df["pnl_usd"] = 0.0
            virtual_df.loc[closed_mask, "pnl_usd"] = (
                virtual_df.loc[closed_mask, "result_r"] * risk_per_trade
            )
            # Les configurations en attente, trades ouverts, ambigus et expirés ne sont pas inclus au P&L réalisé.
            virtual_df.loc[~closed_mask, "pnl_usd"] = float("nan")

            closed_df = virtual_df.loc[closed_mask].copy()
            gross_profit = float(closed_df.loc[closed_df["pnl_usd"] > 0, "pnl_usd"].sum())
            gross_loss = abs(float(closed_df.loc[closed_df["pnl_usd"] < 0, "pnl_usd"].sum()))
            net_profit = gross_profit - gross_loss
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else (
                float("inf") if gross_profit > 0 else 0.0
            )
            average_trade = net_profit / completed if completed else 0.0
            return_pct = (net_profit / capital * 100) if capital > 0 else 0.0

            stat_cols = st.columns(6)
            stat_cols[0].metric("Configurations en attente", pending_count)
            stat_cols[1].metric("Trades ouverts", opened)
            stat_cols[2].metric("Gagnants", wins)
            stat_cols[3].metric("Perdants", losses)
            stat_cols[4].metric("Taux de réussite", f"{win_rate:.1f}%" if completed else "N/D")
            stat_cols[5].metric("Ambigus / expirés", f"{ambiguous} / {expired}")

            st.markdown("#### 💵 Rentabilité simulée")
            st.caption(
                f"Calcul basé sur un risque fixe de {risk_per_trade:.2f} $ par trade "
                f"({risk_percent:.2f} % du capital configuré de {capital:.2f} $). "
                "Les configurations en attente, trades ouverts, ambigus et expirés sont exclues du résultat réalisé."
            )
            pnl_cols = st.columns(4)
            pnl_cols[0].metric("Profit net", f"{net_profit:+,.2f} $")
            pnl_cols[1].metric("Gains bruts", f"{gross_profit:,.2f} $")
            pnl_cols[2].metric("Pertes brutes", f"-{gross_loss:,.2f} $")
            pnl_cols[3].metric("Rendement du capital", f"{return_pct:+.2f} %")
            extra_cols = st.columns(2)
            pf_text = f"{profit_factor:.2f}" if profit_factor != float("inf") else "∞"
            extra_cols[0].metric("Profit factor", pf_text)
            extra_cols[1].metric("Gain / perte moyen par trade", f"{average_trade:+,.2f} $")

            if completed:
                equity_df = closed_df.copy()
                equity_df["_sort_time"] = pd.to_datetime(
                    equity_df["close_time"], errors="coerce", utc=True
                )
                equity_df = equity_df.sort_values("_sort_time")
                equity_df["capital_simule"] = capital + equity_df["pnl_usd"].cumsum()
                equity_df["trade_num"] = range(1, len(equity_df) + 1)

                st.markdown("#### 📈 Évolution du capital simulé")
                fig_equity = go.Figure()
                fig_equity.add_trace(go.Scatter(
                    x=equity_df["trade_num"],
                    y=equity_df["capital_simule"],
                    mode="lines+markers",
                    name="Capital simulé",
                    line=dict(width=3),
                    hovertemplate="Trade %{x}<br>Capital : %{y:,.2f} $<extra></extra>"
                ))
                fig_equity.add_hline(
                    y=capital, line_dash="dash", line_color="gray",
                    annotation_text="Capital initial"
                )
                fig_equity.update_layout(
                    height=320, template="plotly_dark",
                    margin=dict(l=20, r=20, t=30, b=20),
                    xaxis_title="Nombre de trades clôturés",
                    yaxis_title="Capital ($)",
                    showlegend=False
                )
                st.plotly_chart(fig_equity, width="stretch")

                # GRAPHIQUES COMPLEMENTAIRES — statistiques issues des trades Supabase
                st.markdown("#### 📊 Répartition des résultats et performance")

                chart_col1, chart_col2 = st.columns(2)

                # 1) Répartition des trades terminés
                with chart_col1:
                    outcome_values = {
                        "Gagnants": wins,
                        "Perdants": losses,
                        "Ambigus": ambiguous,
                        "Expirés": expired,
                    }
                    outcome_values = {
                        label: value for label, value in outcome_values.items()
                        if value > 0
                    }
                    if outcome_values:
                        fig_outcomes = go.Figure(data=[go.Pie(
                            labels=list(outcome_values.keys()),
                            values=list(outcome_values.values()),
                            hole=0.62,
                            sort=False,
                            textinfo="label+percent",
                            marker=dict(
                                colors=["#20d68a", "#ff5b6e", "#ffbf47", "#8294aa"],
                                line=dict(color="#071426", width=2),
                            ),
                            hovertemplate="%{label}<br>%{value} trade(s)<br>%{percent}<extra></extra>",
                        )])
                        fig_outcomes.update_layout(
                            title="Répartition des trades",
                            height=340,
                            template="plotly_dark",
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            margin=dict(l=15, r=15, t=55, b=15),
                            showlegend=False,
                        )
                        st.plotly_chart(fig_outcomes, width="stretch")
                    else:
                        st.info("Aucun résultat terminé à répartir pour le moment.")

                # 2) Résultat net par instrument, exprimé en R
                with chart_col2:
                    if not closed_df.empty and "instrument" in closed_df.columns:
                        by_instrument = (
                            closed_df.groupby("instrument", dropna=False)["result_r"]
                            .sum()
                            .sort_values()
                            .reset_index()
                        )
                        by_instrument = by_instrument.dropna(subset=["result_r"])
                        if not by_instrument.empty:
                            fig_instruments = go.Figure(go.Bar(
                                x=by_instrument["instrument"].astype(str),
                                y=by_instrument["result_r"],
                                marker=dict(
                                    color=[
                                        "#20d68a" if value >= 0 else "#ff5b6e"
                                        for value in by_instrument["result_r"]
                                    ]
                                ),
                                text=[f"{value:+.2f} R" for value in by_instrument["result_r"]],
                                textposition="outside",
                                hovertemplate="%{x}<br>Résultat : %{y:+.2f} R<extra></extra>",
                            ))
                            fig_instruments.update_layout(
                                title="Performance par instrument",
                                height=340,
                                template="plotly_dark",
                                paper_bgcolor="rgba(0,0,0,0)",
                                plot_bgcolor="rgba(0,0,0,0)",
                                margin=dict(l=15, r=15, t=55, b=35),
                                yaxis_title="Résultat net (R)",
                                xaxis_title="",
                                showlegend=False,
                                yaxis=dict(zeroline=True, zerolinecolor="#7890aa"),
                            )
                            st.plotly_chart(fig_instruments, width="stretch")
                        else:
                            st.info("Pas encore assez de résultats par instrument.")
                    else:
                        st.info("Les résultats par instrument apparaîtront après les premiers trades clôturés.")

                # 3) Résultat hebdomadaire en R
                if not closed_df.empty and "close_time" in closed_df.columns:
                    weekly_df = closed_df.copy()
                    weekly_df["_close_date"] = pd.to_datetime(
                        weekly_df["close_time"], errors="coerce", utc=True
                    )
                    weekly_df["result_r"] = pd.to_numeric(
                        weekly_df["result_r"], errors="coerce"
                    )
                    weekly_df = weekly_df.dropna(subset=["_close_date", "result_r"])
                    if not weekly_df.empty:
                        weekly_df["_week"] = (
                            weekly_df["_close_date"]
                            .dt.tz_convert("America/New_York")
                            .dt.to_period("W")
                            .astype(str)
                        )
                        weekly_results = (
                            weekly_df.groupby("_week")["result_r"]
                            .sum()
                            .reset_index()
                        )
                        fig_weekly = go.Figure(go.Bar(
                            x=weekly_results["_week"],
                            y=weekly_results["result_r"],
                            marker=dict(
                                color=[
                                    "#20d68a" if value >= 0 else "#ff5b6e"
                                    for value in weekly_results["result_r"]
                                ]
                            ),
                            text=[f"{value:+.2f} R" for value in weekly_results["result_r"]],
                            textposition="outside",
                            hovertemplate="Semaine %{x}<br>Résultat : %{y:+.2f} R<extra></extra>",
                        ))
                        fig_weekly.update_layout(
                            title="Résultat par semaine",
                            height=320,
                            template="plotly_dark",
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            margin=dict(l=20, r=20, t=55, b=45),
                            xaxis_title="Semaine de clôture (heure de New York)",
                            yaxis_title="Résultat net (R)",
                            showlegend=False,
                            yaxis=dict(zeroline=True, zerolinecolor="#7890aa"),
                        )
                        st.plotly_chart(fig_weekly, width="stretch")

            display_columns = [
                "created_at", "instrument", "timeframe", "direction", "fib_mode",
                "entry_price", "stop_loss", "take_profit", "rr", "status",
                "close_price", "close_time", "result_r", "pnl_usd", "notes"
            ]
            available_columns = [c for c in display_columns if c in virtual_df.columns]
            st.dataframe(
                virtual_df[available_columns],
                width="stretch",
                hide_index=True,
                column_config={
                    "pnl_usd": st.column_config.NumberColumn(
                        "P&L simulé ($)", format="%.2f $"
                    ),
                    "result_r": st.column_config.NumberColumn(
                        "Résultat (R)", format="%.2f R"
                    ),
                }
            )
            st.download_button(
                "⬇️ Télécharger l'historique des trades virtuels (CSV)",
                data=virtual_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"trades_virtuels_{datetime.now(pytz.timezone('America/New_York')).strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
    except Exception as exc:
        st.error(f"Impossible de charger les trades virtuels depuis Supabase : {exc}")


# RECENT ALERTS AND DOWNLOADABLE HISTORY
st.markdown("---")
st.subheader("🔔 Alertes Fibonacci récentes")
recent_alerts = st.session_state.get("fib_new_alerts", [])
if recent_alerts:
    st.dataframe(pd.DataFrame(recent_alerts[::-1]), width="stretch", hide_index=True)
else:
    st.info("Aucune nouvelle alerte Fibonacci depuis l'ouverture du dashboard.")

st.markdown("#### 📚 Journal complet des alertes")
alert_history = load_alert_history()
if not alert_history.empty:
    st.caption(
        f"{len(alert_history)} alerte(s) enregistrée(s) dans le journal local. "
        "Les colonnes Résultat et Notes sont prévues pour ton analyse après coup."
    )
    st.dataframe(alert_history.iloc[::-1], width="stretch", hide_index=True)
    csv_data = alert_history.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="⬇️ Télécharger le journal Fibonacci (CSV / Excel)",
        data=csv_data,
        file_name=f"journal_fibonacci_{datetime.now(pytz.timezone('America/New_York')).strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True
    )
else:
    st.info("Le journal sera créé automatiquement à la première nouvelle alerte confirmée.")
