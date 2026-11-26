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

st.set_page_config(page_title="Trading Monitor - Fibonacci & FVG", layout="wide")
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


def create_virtual_trade(pair, timeframe, setup, candle_time, trade_plan, fib_mode):
    """Enregistre un ordre limite virtuel PENDING, sans simuler une entrée immédiate."""
    if not supabase_configured():
        return False, "Supabase non configuré."
    if not trade_plan or not setup.get("fib"):
        return False, "Aucun plan complet à enregistrer."
    fib = setup["fib"]
    candle_iso = pd.Timestamp(candle_time.replace(" NY", "")).tz_localize("America/New_York").isoformat()
    signal_key = _signal_identity(pair, timeframe, fib, fib_mode.upper())
    signal_time_iso = datetime.now(pytz.UTC).isoformat()
    payload = {
        "signal_key": signal_key, "instrument": pair, "timeframe": timeframe,
        "direction": fib["direction"], "fib_mode": fib_mode.upper(),
        "signal_time": signal_time_iso, "candle_time": candle_iso,
        "entry_price": float(trade_plan["entry"]), "stop_loss": float(trade_plan["stop_loss"]),
        "take_profit": float(trade_plan["take_profit"]), "rr": float(trade_plan["rr"]),
        "status": "PENDING",
        "notes": "Ordre limite virtuel en attente d'un retour dans la zone Fibonacci; aucun ordre OANDA envoyé.",
    }
    result = supabase_request(
        "POST", payload=payload, params={"on_conflict": "signal_key"},
        prefer="resolution=ignore-duplicates,return=representation",
    )
    if result:
        return True, "Ordre limite virtuel en attente."

    # Met à jour un ancien dossier PENDING portant la même identité de swing.
    existing = supabase_request(
        "GET", params={"select": "id,status", "signal_key": f"eq.{signal_key}", "limit": "1"}
    )
    if existing:
        previous = existing[0]
        if str(previous.get("status", "")).upper() == "PENDING":
            supabase_request(
                "PATCH", params={"id": f"eq.{previous['id']}"}, payload=payload,
                prefer="return=minimal",
            )
            return True, "Ordre limite en attente actualisé."
        return False, f"Signal déjà enregistré ({previous.get('status', 'statut inconnu')})."
    return False, "Signal déjà enregistré."


def monitor_virtual_trades(pair, timeframe, closed_df):
    """Gère les ordres limites PENDING puis suit les trades OPEN sur chandelles clôturées."""
    if not supabase_configured() or closed_df.empty:
        return
    candles = closed_df.copy()
    candles["_utc_time"] = pd.to_datetime(candles["time"], utc=True)
    max_wait = 4 if timeframe == "M30" else 6
    trades = supabase_request(
        "GET", params={
            "select": "*", "status": "in.(PENDING,OPEN)",
            "instrument": f"eq.{pair}", "timeframe": f"eq.{timeframe}",
            "order": "candle_time.asc",
        }
    )
    if not trades:
        return

    for trade in trades:
        direction = trade["direction"]
        entry = float(trade["entry_price"])
        stop = float(trade["stop_loss"])
        target = float(trade["take_profit"])
        signal_candle_time = pd.to_datetime(trade["candle_time"], utc=True)
        signal_time = pd.to_datetime(trade.get("signal_time") or trade["candle_time"], utc=True)
        start_time = max(signal_candle_time, signal_time)
        later = candles[candles["_utc_time"] > start_time]

        if str(trade.get("status", "")).upper() == "PENDING":
            if "Ordre limite virtuel" not in str(trade.get("notes", "")):
                supabase_request(
                    "PATCH", params={"id": f"eq.{trade['id']}", "status": "eq.PENDING"},
                    payload={"status": "EXPIRED", "notes": "Ancienne configuration PENDING expirée; elle ne correspond pas au nouveau suivi par entrée limite.",
                             "updated_at": datetime.now(pytz.UTC).isoformat()},
                    prefer="return=minimal",
                )
                continue
            for age, (_, candle) in enumerate(later.iterrows(), start=1):
                high, low = float(candle["high"]), float(candle["low"])
                if direction == "BULL":
                    entry_touched = low <= entry
                    invalid_before_fill = low <= stop
                    target_passed = high >= target
                else:
                    entry_touched = high >= entry
                    invalid_before_fill = high >= stop
                    target_passed = low <= target

                # Si une même chandelle touche l'entrée et une borne de sortie,
                # l'ordre intrachandelle est inconnu : ne pas inventer un résultat.
                if entry_touched and (invalid_before_fill or target_passed):
                    supabase_request(
                        "PATCH", params={"id": f"eq.{trade['id']}", "status": "eq.PENDING"},
                        payload={"status": "AMBIGUOUS", "close_time": pd.Timestamp(candle["time"]).isoformat(),
                                 "notes": "Entrée limite et niveau de sortie touchés dans la même chandelle; ordre intrachandelle inconnu.",
                                 "updated_at": datetime.now(pytz.UTC).isoformat()},
                        prefer="return=minimal",
                    )
                    break
                if invalid_before_fill or target_passed:
                    supabase_request(
                        "PATCH", params={"id": f"eq.{trade['id']}", "status": "eq.PENDING"},
                        payload={"status": "EXPIRED", "close_time": pd.Timestamp(candle["time"]).isoformat(),
                                 "notes": "Configuration expirée avant le déclenchement de l'entrée limite (SL ou objectif atteint sans remplissage).",
                                 "updated_at": datetime.now(pytz.UTC).isoformat()},
                        prefer="return=minimal",
                    )
                    break
                if entry_touched:
                    fill_time = pd.Timestamp(candle["time"]).isoformat()
                    supabase_request(
                        "PATCH", params={"id": f"eq.{trade['id']}", "status": "eq.PENDING"},
                        payload={"status": "OPEN", "signal_time": fill_time,
                                 "notes": "Entrée limite virtuelle déclenchée; suivi SL/TP à partir de la chandelle clôturée suivante.",
                                 "updated_at": datetime.now(pytz.UTC).isoformat()},
                        prefer="return=minimal",
                    )
                    break
                if age >= max_wait:
                    supabase_request(
                        "PATCH", params={"id": f"eq.{trade['id']}", "status": "eq.PENDING"},
                        payload={"status": "EXPIRED", "close_time": pd.Timestamp(candle["time"]).isoformat(),
                                 "notes": f"Ordre limite expiré après {max_wait} chandelles sans retour au prix d'entrée.",
                                 "updated_at": datetime.now(pytz.UTC).isoformat()},
                        prefer="return=minimal",
                    )
                    break
            continue

        # Trade OPEN : ignorer la chandelle qui contient le remplissage de l'entrée.
        later_open = candles[candles["_utc_time"] > start_time]
        for _, candle in later_open.iterrows():
            high, low = float(candle["high"]), float(candle["low"])
            if direction == "BULL":
                hit_stop, hit_target = low <= stop, high >= target
            else:
                hit_stop, hit_target = high >= stop, low <= target
            if not hit_stop and not hit_target:
                continue
            close_time = pd.Timestamp(candle["time"]).isoformat()
            if hit_stop and hit_target:
                status, close_price, result_r = "AMBIGUOUS", None, None
                note = "TP et SL touchés dans la même chandelle; ordre intrachandelle inconnu."
            elif hit_target:
                status, close_price, result_r = "WIN", target, float(trade["rr"])
                note = "Take-profit atteint."
            else:
                status, close_price, result_r = "LOSS", stop, -1.0
                note = "Stop-loss atteint."
            supabase_request(
                "PATCH", params={"id": f"eq.{trade['id']}", "status": "eq.OPEN"},
                payload={"status": status, "close_price": close_price, "close_time": close_time,
                         "result_r": result_r, "notes": note,
                         "updated_at": datetime.now(pytz.UTC).isoformat()},
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

st.sidebar.caption("Mode analyse visuelle : Fibonacci automatique ou manuel et FVG associé. Aucun signal ni ordre n’est généré.")


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
    """Combine tendance EMA/DI et structure de marché sur M30 clôturé."""
    raw_m30 = get_data(pair, "M30")
    neutral = {"bias": "NEUTRAL", "structure_bias": "NEUTRAL",
               "strength": "Indisponible", "adx": None}
    if raw_m30.empty:
        return {**neutral, "details": "Données M30 indisponibles : aucun signal directionnel validé."}

    closed_m30 = raw_m30[raw_m30["complete"]].copy()
    if len(closed_m30) < 210:
        return {**neutral, "strength": "Données insuffisantes",
                "details": "Au moins 210 chandelles M30 clôturées sont nécessaires."}

    m30 = add_indicators(closed_m30).reset_index(drop=True)
    last = m30.iloc[-1]
    values = [last.get("close"), last.get("EMA50"), last.get("EMA100"),
              last.get("EMA200"), last.get("+DI14"), last.get("-DI14"),
              last.get("ADX14")]
    if any(pd.isna(value) for value in values):
        return {**neutral, "details": "Indicateurs M30 incomplets : aucun signal directionnel validé."}

    close = float(last["close"])
    ema50, ema100, ema200 = (float(last[k]) for k in ("EMA50", "EMA100", "EMA200"))
    plus_di, minus_di = float(last["+DI14"]), float(last["-DI14"])
    adx = float(last["ADX14"])

    if close > ema200 and ema50 > ema100 and plus_di > minus_di:
        trend_bias = "BULL"
        trend_details = "Tendance EMA/DI haussière."
    elif close < ema200 and ema50 < ema100 and minus_di > plus_di:
        trend_bias = "BEAR"
        trend_details = "Tendance EMA/DI baissière."
    else:
        trend_bias = "NEUTRAL"
        trend_details = "Tendance EMA/DI non alignée."

    # Structure sans anticipation : seuls les pivots ayant leurs 3 chandelles
    # de confirmation à droite sont retenus.
    pivot_window = 3
    recent = m30.tail(120).reset_index(drop=True)
    pivot_highs, pivot_lows = [], []
    for i in range(pivot_window, len(recent) - pivot_window):
        row = recent.iloc[i]
        left = recent.iloc[i-pivot_window:i]
        right = recent.iloc[i+1:i+pivot_window+1]
        high = float(row["high"])
        low = float(row["low"])
        if high > float(left["high"].max()) and high >= float(right["high"].max()):
            pivot_highs.append(high)
        if low < float(left["low"].min()) and low <= float(right["low"].min()):
            pivot_lows.append(low)

    structure_bias = "NEUTRAL"
    if len(pivot_highs) >= 2 and len(pivot_lows) >= 2:
        lower_highs = pivot_highs[-1] < pivot_highs[-2]
        lower_lows = pivot_lows[-1] < pivot_lows[-2]
        higher_highs = pivot_highs[-1] > pivot_highs[-2]
        higher_lows = pivot_lows[-1] > pivot_lows[-2]
        if lower_highs and lower_lows:
            structure_bias = "BEAR"
        elif higher_highs and higher_lows:
            structure_bias = "BULL"

    # Pour autoriser un signal M30, la tendance et la structure doivent être
    # d'accord. En cas de désaccord ou de structure indécise, on reste neutre.
    if trend_bias == structure_bias and trend_bias in ("BULL", "BEAR"):
        bias = trend_bias
        details = f"{trend_details} Structure M30 {('haussière' if bias == 'BULL' else 'baissière')} confirmée : " \
                  f"{('sommets et creux ascendants' if bias == 'BULL' else 'sommets et creux descendants')}."
    else:
        bias = "NEUTRAL"
        structure_text = {"BULL": "structure haussière", "BEAR": "structure baissière",
                          "NEUTRAL": "structure indécise"}[structure_bias]
        details = (f"{trend_details} {structure_text.capitalize()} : tendance et structure "
                   "ne sont pas suffisamment alignées. Signal M30 bloqué par prudence.")

    strength = "Faible" if adx < 15 else ("Modérée" if adx < 25 else "Forte")
    return {"bias": bias, "structure_bias": structure_bias, "trend_bias": trend_bias,
            "strength": strength, "adx": adx, "details": details,
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



def find_related_fvg(df, fib):
    """Repère le FVG non entièrement comblé le plus récent dans le swing Fibonacci."""
    if fib is None or df is None or len(df) < 3:
        return None
    data = df.reset_index(drop=True)
    start = max(2, int(fib["origin"]["index"]))
    end = min(len(data) - 1, int(fib["endpoint"]["index"]))
    direction = fib["direction"]
    candidates = []
    for i in range(start, end + 1):
        # FVG trois chandelles : espace entre la première et la troisième.
        if direction == "BULL":
            lower = float(data.iloc[i - 2]["high"])
            upper = float(data.iloc[i]["low"])
            valid = lower < upper
        else:
            lower = float(data.iloc[i]["high"])
            upper = float(data.iloc[i - 2]["low"])
            valid = lower < upper
        if valid:
            candidates.append({
                "direction": direction, "low": lower, "high": upper,
                "start_time": data.iloc[i - 2]["time"],
                "formed_time": data.iloc[i]["time"],
                "index": i,
            })
    # Le plus récent FVG du sens du swing qui n'a pas été entièrement traversé.
    for gap in reversed(candidates):
        later = data.iloc[gap["index"] + 1:]
        if direction == "BULL":
            fully_filled = (not later.empty) and float(later["low"].min()) <= gap["low"]
        else:
            fully_filled = (not later.empty) and float(later["high"].max()) >= gap["high"]
        if not fully_filled:
            gap["status"] = "NON COMBLÉ"
            return gap
    return None


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
    timeframe="M5",
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
        label = ("🟢 ACHAT — REJET FIBONACCI M30 CONFIRMÉ" if timeframe == "M30"
                 else "🟢 ACHAT — CASSURE DU REJET CONFIRMÉE")
        wait_label = "🟡 Zone d'achat Fibonacci — attente du rejet et de la cassure"
        zone_name = "ZONE D'ACHAT"
        if timeframe == "M30":
            # M30 : accepte un rejet haussier depuis le bas de la zone même si
            # la clôture reste à l'intérieur du Fibonacci. La cassure du sommet
            # de cette chandelle par la chandelle suivante sera obligatoire.
            rejection_condition = lambda row: (
                float(row["close"]) > float(row["open"])
                and float(row["close"]) > zone_low
                and (float(row["close"]) - float(row["low"]))
                    >= 0.55 * max(float(row["high"]) - float(row["low"]), 1e-12)
            )
        else:
            rejection_condition = lambda row: (
                float(row["close"]) > float(row["open"])
                and float(row["close"]) > zone_high
            )
        trigger_broken = lambda row, rejection: (
            float(row["close"]) > float(rejection["high"])
        )
        details = (
            "Rejet haussier M30 détecté dans la zone 50–61,8 %. Le signal sera confirmé "
            "uniquement si une chandelle suivante clôture au-dessus du sommet du rejet."
            if timeframe == "M30" else
            "Après le retour dans la zone 50–61,8 %, le système attend une "
            "chandelle de rejet haussière, puis la clôture d'une chandelle "
            "au-dessus de son plus haut."
        )
    else:
        label = ("🔴 VENTE — REJET FIBONACCI M30 CONFIRMÉ" if timeframe == "M30"
                 else "🔴 VENTE — CASSURE DU REJET CONFIRMÉE")
        wait_label = "🟡 Zone de vente Fibonacci — attente du rejet et de la cassure"
        zone_name = "ZONE DE VENTE"
        if timeframe == "M30":
            # M30 : accepte un rejet baissier depuis le haut de la zone même si
            # la clôture reste à l'intérieur du Fibonacci. La cassure du creux
            # de cette chandelle par la chandelle suivante sera obligatoire.
            rejection_condition = lambda row: (
                float(row["close"]) < float(row["open"])
                and float(row["close"]) < zone_high
                and (float(row["high"]) - float(row["close"]))
                    >= 0.55 * max(float(row["high"]) - float(row["low"]), 1e-12)
            )
        else:
            rejection_condition = lambda row: (
                float(row["close"]) < float(row["open"])
                and float(row["close"]) < zone_low
            )
        trigger_broken = lambda row, rejection: (
            float(row["close"]) < float(rejection["low"])
        )
        details = (
            "Rejet baissier M30 détecté dans la zone 50–61,8 %. Le signal sera confirmé "
            "uniquement si une chandelle suivante clôture sous le creux du rejet."
            if timeframe == "M30" else
            "Après le retour dans la zone 50–61,8 %, le système attend une "
            "chandelle de rejet baissière, puis la clôture d'une chandelle "
            "sous son plus bas."
        )

    # M30 et M5 utilisent maintenant une confirmation en deux temps :
    # 1) une chandelle rejette la zone Fibonacci dans le bon sens;
    # 2) une chandelle clôturée suivante casse le haut/bas de cette chandelle.
    # En M30, le rejet peut clôturer à l'intérieur de la zone : cela permet de
    # détecter un rebond propre depuis le bord 61,8 % sans exiger une clôture
    # déjà trop éloignée du niveau de retracement.
    last_overlaps_zone = (
        float(last["low"]) <= zone_high and float(last["high"]) >= zone_low
    )
    rejection = None
    rejection_index = None
    confirmed = False
    trigger_level = None
    candles_waited = None

    # Cherche la dernière chandelle de rejet clôturée AVANT la dernière chandelle.
    # La dernière chandelle doit ensuite casser son extrême dans le bon sens,
    # y compris en M30 : aucune alerte sur la seule couleur d'une chandelle.
    prior = data.iloc[touch_start:-1]
    if not confirmed:
        for idx in range(len(prior) - 1, -1, -1):
            row = prior.iloc[idx]
            overlaps_zone = (
                float(row["low"]) <= zone_high and float(row["high"]) >= zone_low
            )
            if overlaps_zone and rejection_condition(row):
                rejection = row
                rejection_index = touch_start + idx
                break

    if not confirmed and rejection is not None:
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
                    "⚠️ VENTE — CONFIRMATION TROP ÉLOIGNÉE, ENTRÉE TARDIVE"
                    if direction == "BEAR"
                    else "⚠️ ACHAT — CONFIRMATION TROP ÉLOIGNÉE, ENTRÉE TARDIVE"
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
    """Construit un plan à entrée limite au milieu de la zone Fibonacci 50–61,8 %."""
    if setup.get("state") not in ("BULL_CONFIRMED", "BEAR_CONFIRMED"):
        return None, "Aucun plan : attendre une confirmation Fibonacci non tardive."
    fib = setup.get("fib")
    if not fib or current_price is None:
        return None, "Aucun plan : prix courant ou Fibonacci indisponible."

    zone_low, zone_high = float(fib["zone_low"]), float(fib["zone_high"])
    entry = (zone_low + zone_high) / 2.0
    atr = float(fib["atr"])
    buffer = atr * stop_buffer_atr
    target = float(fib["endpoint"]["price"])
    live = float(current_price)

    if fib["direction"] == "BEAR":
        stop = zone_high + buffer
        if live <= target:
            return None, "Signal trop tardif : l'objectif est déjà atteint. Ne pas poursuivre le prix."
        if live >= stop:
            return None, "Configuration invalidée : le prix a déjà dépassé le stop prévu."
        if not (target < entry < stop):
            return None, "Aucun plan : niveaux Fibonacci invalides."
        risk, reward, side = stop - entry, entry - target, "VENTE"
    else:
        stop = zone_low - buffer
        if live >= target:
            return None, "Signal trop tardif : l'objectif est déjà atteint. Ne pas poursuivre le prix."
        if live <= stop:
            return None, "Configuration invalidée : le prix a déjà dépassé le stop prévu."
        if not (stop < entry < target):
            return None, "Aucun plan : niveaux Fibonacci invalides."
        risk, reward, side = entry - stop, target - entry, "ACHAT"

    rr_value = reward / risk if risk > 0 else 0.0
    if rr_value < min_rr:
        return None, (f"Aucun plan proposé : le rendement jusqu'à l'extrémité du swing "
                      f"n'offre que 1:{rr_value:.2f}, sous le minimum de 1:{min_rr:.2f}.")
    return {
        "side": side, "entry": entry, "stop_loss": stop, "take_profit": target,
        "rr": rr_value, "risk_distance": risk, "reward_distance": reward,
        "buffer": buffer, "entry_type": "LIMIT", "zone_low": zone_low,
        "zone_high": zone_high,
    }, "Ordre limite indicatif au milieu de la zone Fibonacci; attente du retour du prix."


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
    """Crée un ordre limite virtuel PENDING après confirmation."""
    if setup.get("state") not in ("BULL_CONFIRMED", "BEAR_CONFIRMED"):
        return
    if not trade_plan or not setup.get("fib"):
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
        st.error("Trade virtuel non créé : vérifie SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY.")
        return

    try:
        saved, message = create_virtual_trade(pair, timeframe, setup, candle_time, trade_plan, fib_mode)
    except Exception as exc:
        st.error(f"Erreur Supabase — création du trade virtuel : {exc}")
        return
    if not saved:
        st.info(f"Supabase : {message}")
        st.session_state[alert_state_key] = signal_key
        return

    zone_low, zone_high = float(fib["zone_low"]), float(fib["zone_high"])
    now_text = datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
    subject = f"{'🟢 ORDRE LIMITE ACHAT' if bullish else '🔴 ORDRE LIMITE VENTE'} Fibonacci — {pair} {timeframe}"
    fmt = lambda value: f"{float(value):.5f}"
    body = (
        f"ORDRE LIMITE VIRTUEL EN ATTENTE — signal Fibonacci confirmé sur {pair} en {timeframe}.\n"
        f"Direction : {direction}.\n"
        f"Zone Fibonacci 50–61,8 % : {fmt(zone_low)} à {fmt(zone_high)}.\n"
        f"Entrée limite à surveiller : {fmt(trade_plan['entry'])}.\n"
        f"Stop-loss : {fmt(trade_plan['stop_loss'])}.\n"
        f"Take-profit : {fmt(trade_plan['take_profit'])}.\n"
        f"Ratio R/R : 1:{float(trade_plan['rr']):.2f}.\n"
        f"Prix observé au signal : {fmt(current_price)}.\n"
        f"Dernière chandelle clôturée : {candle_time}.\n\n"
        f"Ne pas entrer au prix actuel : attendre que le prix revienne à {fmt(trade_plan['entry'])}. "
        "L'ordre reste en attente au maximum 4 chandelles M30 ou 6 chandelles M5. Aucun ordre OANDA n'est envoyé."
    )
    append_alert_history({
        "Heure alerte": now_text, "Heure chandelle": candle_time,
        "Instrument": pair, "Timeframe": timeframe, "Direction": direction,
        "Etat": "ORDRE LIMITE EN ATTENTE", "Zone basse": zone_low, "Zone haute": zone_high,
        "Entree": trade_plan["entry"], "Stop-loss": trade_plan["stop_loss"],
        "Take-profit": trade_plan["take_profit"], "R_R": trade_plan["rr"],
        "Prix au signal": current_price, "Mode Fibonacci": fib_mode,
        "Resultat": "", "Notes": "Ordre limite PENDING; entrée virtuelle seulement au retour du prix dans la zone.",
    })
    st.session_state.setdefault("fib_new_alerts", []).append({
        "Heure": now_text, "Instrument": pair, "Timeframe": timeframe, "Signal": subject,
        "Zone": f"{zone_low:.5f} – {zone_high:.5f}", "Entrée": fmt(trade_plan["entry"]),
        "SL": fmt(trade_plan["stop_loss"]), "TP": fmt(trade_plan["take_profit"]),
        "R/R": f"1:{float(trade_plan['rr']):.2f}",
    })
    if not mute_alerts:
        play_voice_alert(VOICE_STRONG_BULL if bullish else VOICE_STRONG_BEAR)
    if email_alerts_enabled:
        sent, status = send_email_alert(subject, body)
        if not sent:
            st.warning(status)
    st.success(f"{pair} {timeframe} : ordre limite virtuel {direction} en attente du retour du prix.")
    st.session_state[alert_state_key] = signal_key


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
          color:#45e6a0;font-weight:700;font-size:13px;">● SIGNAUX CONFIRMÉS UNIQUEMENT</div>
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
summary[1].metric("UNITÉS DE TEMPS", "M30 / M5", "Analyse visuelle")
summary[2].metric("DONNÉES", "OANDA", "Actualisation automatique")
summary[3].metric("MODE", "Analyse", "Décision manuelle")
st.caption("Le dashboard affiche les swings Fibonacci confirmés, les niveaux 0 / 0,5 / 1 et le FVG non comblé associé. L’analyse et les décisions d’entrée restent entièrement manuelles.")

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

        df = add_indicators(closed_df)
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
                </div><div style="color:#c6d5e4;font-size:12px;margin-top:3px;">ANALYSE DU MARCHÉ</div>
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
            fib = None
            fib_message = manual_status
        else:
            fib, fib_message = (fib_override, "Fibonacci manuel actif.") if fib_override is not None else find_last_fibonacci(df)

        setup = {
            "state": "VISUAL" if fib else "WAIT",
            "label": ("FIBONACCI HAUSSIER" if fib and fib["direction"] == "BULL" else
                      "FIBONACCI BAISSIER" if fib else "EN ATTENTE D’UN SWING CONFIRMÉ"),
            "color": "#20d68a" if fib and fib["direction"] == "BULL" else
                     "#ff6b78" if fib else "#aab8c8",
            "details": fib_message,
            "fib": fib,
        }
        fvg = find_related_fvg(df, fib) if fib else None
        candle_time = last["time"].strftime("%Y-%m-%d %H:%M NY")

        st.markdown(
            f"<h4 style='color:{setup['color']};'>{setup['label']}</h4>",
            unsafe_allow_html=True
        )
        st.caption(f"Dernière chandelle clôturée : {candle_time}")
        if fib:
            fib_col1, fib_col2, fib_col3, fvg_col = st.columns([1, 1, 1, 1.35])
            fib_col1.metric("FIB 0 · EXTRÉMITÉ", f"{float(fib['endpoint']['price']):,.{price_decimals}f}")
            fib_col2.metric("FIB 0,5 · MILIEU", f"{float(fib['levels'][0.5]):,.{price_decimals}f}")
            fib_col3.metric("FIB 1 · ORIGINE", f"{float(fib['origin']['price']):,.{price_decimals}f}")
            if fvg:
                fvg_side = "HAUSSIER" if fvg["direction"] == "BULL" else "BAISSIER"
                fvg_col.metric(
                    f"FVG {fvg_side}",
                    f"{fvg['low']:,.{price_decimals}f} – {fvg['high']:,.{price_decimals}f}",
                    "NON COMBLÉ"
                )
            else:
                fvg_col.metric("FVG ASSOCIÉ", "Non détecté", "Aucun gap valide dans ce swing")
        else:
            st.info(fib_message)

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
            go.Candlestick(
                x=df["time"], open=df["open"], high=df["high"],
                low=df["low"], close=df["close"], name="Chandelles OANDA",
                increasing_line_color="#20b96b", decreasing_line_color="#ef5350",
                increasing_fillcolor="#20b96b", decreasing_fillcolor="#ef5350",
                whiskerwidth=0.5,
            ), row=1, col=1
        )

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

        if setup.get("fib"):
            fib = setup["fib"]
            x0 = fib["origin"]["time"]
            x1 = live_time if live_time is not None else df["time"].iloc[-1]
            # Prolonge les niveaux dans l'espace libre à droite du graphique.
            interval_minutes = {"M1": 1, "M5": 5, "M15": 15, "M30": 30,
                                "H1": 60, "H4": 240, "D": 1440, "W": 10080}.get(timeframe, 5)
            chart_end = pd.Timestamp(x1) + pd.Timedelta(minutes=interval_minutes * 8)
            origin_price = float(fib["origin"]["price"])
            endpoint_price = float(fib["endpoint"]["price"])
            midpoint_price = float(fib["levels"][0.5])

            # Fond discret du swing et zone de retracement, pour lire le Fib d'un coup d'œil.
            fig.add_shape(
                type="rect", xref="x", yref="y",
                x0=x0, x1=chart_end,
                y0=min(origin_price, endpoint_price),
                y1=max(origin_price, endpoint_price),
                fillcolor="rgba(53,182,255,0.055)",
                line=dict(color="rgba(53,182,255,0.25)", width=1, dash="dot"),
                layer="below",
            )
            fig.add_shape(
                type="rect", xref="x", yref="y",
                x0=x0, x1=chart_end,
                y0=min(origin_price, midpoint_price),
                y1=max(origin_price, midpoint_price),
                fillcolor="rgba(255,200,87,0.075)",
                line=dict(width=0),
                layer="below",
            )
            # Diagonale reliant les deux ancrages du mouvement mesuré.
            fig.add_trace(go.Scatter(
                x=[fib["origin"]["time"], fib["endpoint"]["time"]],
                y=[origin_price, endpoint_price],
                mode="lines+markers",
                name="Swing mesuré",
                line=dict(color="#DCE8F5", width=2, dash="dash"),
                marker=dict(size=8, color="#DCE8F5", line=dict(color="#071426", width=1)),
                hovertemplate="Swing Fibonacci<br>Prix: %{y:,.5f}<extra></extra>",
            ), row=1, col=1)

            visible_levels = [
                (0.0, float(fib["endpoint"]["price"]), "0", "#35B6FF", 2),
                (0.5, float(fib["levels"][0.5]), "0,5", "#FFC857", 2.5),
                (1.0, float(fib["origin"]["price"]), "1", "#42E8D4", 2),
            ]
            for ratio, level, level_name, fib_color, fib_width in visible_levels:
                fig.add_trace(go.Scatter(
                    x=[x0, x1], y=[level, level], mode="lines",
                    name=f"Fibonacci {level_name} · {level:,.{price_decimals}f}",
                    line=dict(color=fib_color, width=fib_width),
                    hovertemplate=f"Fibonacci {level_name}<br>Prix: %{{y:,.{price_decimals}f}}<extra></extra>"
                ), row=1, col=1)
                fig.add_annotation(
                    x=chart_end, y=level, xref="x", yref="y",
                    text=f"FIB {level_name}  ·  {level:,.{price_decimals}f}",
                    showarrow=False, xanchor="left", xshift=5,
                    font=dict(color=fib_color, size=11),
                    bgcolor="rgba(7,20,38,0.94)",
                    bordercolor=fib_color, borderwidth=1, borderpad=4,
                )
            if fvg:
                fvg_color = "rgba(32,214,138,0.22)" if fvg["direction"] == "BULL" else "rgba(255,91,110,0.22)"
                fvg_line = "#20d68a" if fvg["direction"] == "BULL" else "#ff5b6e"
                fig.add_shape(
                    type="rect", xref="x", yref="y",
                    x0=fvg["start_time"], x1=chart_end,
                    y0=fvg["low"], y1=fvg["high"],
                    fillcolor=fvg_color, line=dict(color=fvg_line, width=2),
                    layer="above",
                )
                fig.add_annotation(
                    x=fvg["formed_time"], y=fvg["high"], xref="x", yref="y",
                    text=f"FVG {fvg['low']:,.{price_decimals}f} – {fvg['high']:,.{price_decimals}f} · NON COMBLÉ",
                    showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.2,
                    arrowcolor=fvg_line, ax=0, ay=-32, xanchor="left",
                    font=dict(color=fvg_line, size=11),
                    bgcolor="rgba(7,20,38,0.94)",
                    bordercolor=fvg_line, borderwidth=1, borderpad=4,
                )
            if fib.get("manual"):
                fig.add_trace(go.Scatter(
                    x=[fib["origin"]["time"], fib["endpoint"]["time"]],
                    y=[fib["origin"]["price"], fib["endpoint"]["price"]],
                    mode="markers+text", text=["Origine (1)", "Extrémité (0)"],
                    textposition="top center",
                    marker=dict(size=11, color="white", line=dict(color="black", width=2)),
                    name="Ancrages manuels",
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
        if fib:
            fig.update_xaxes(range=[df["time"].iloc[0], chart_end])
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



st.markdown("---")
st.caption("Mode analyse visuelle activé : aucun courriel, signal automatique ou trade virtuel n’est déclenché. Les anciennes données Supabase et l’historique des alertes ne sont pas supprimés.")
