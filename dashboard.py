
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from email.message import EmailMessage
import smtplib
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
    page_title="Trading Monitor - Décision",
    layout="wide"
)

st_autorefresh(interval=60 * 1000, key="refresh")

NY_TZ = pytz.timezone("America/New_York")

try:
    ACCESS_TOKEN = st.secrets["OANDA_ACCESS_TOKEN"]
    ACCOUNT_ID = st.secrets["OANDA_ACCOUNT_ID"]

    client = API(
        access_token=ACCESS_TOKEN,
        environment="practice"
    )

except Exception:
    st.error("Configuration OANDA manquante dans les Secrets Streamlit.")
    st.stop()


# =========================================================
# INSTRUMENTS DISPONIBLES
# =========================================================

PAIRS = {
    "XAU/USD - Gold": "XAU_USD",
    "SPX500 - S&P 500": "SPX500_USD",
    "EUR/USD": "EUR_USD",
    "AUD/USD": "AUD_USD",
    "GBP/USD": "GBP_USD",
    "BTC/USD": "BTC_USD",
    "ETH/USD": "ETH_USD",
    "USD/CAD": "USD_CAD"
}

TIMEFRAMES = [
    "M1",
    "M5",
    "M15",
    "M30",
    "H1",
    "H4",
    "D",
    "W"
]

TIMEFRAME_DURATION = {
    "M1": pd.Timedelta(minutes=1),
    "M5": pd.Timedelta(minutes=5),
    "M15": pd.Timedelta(minutes=15),
    "M30": pd.Timedelta(minutes=30),
    "H1": pd.Timedelta(hours=1),
    "H4": pd.Timedelta(hours=4),
    "D": pd.Timedelta(days=1),
    "W": pd.Timedelta(days=7)
}

CANDLE_COUNT = 300


# =========================================================
# SIDEBAR : SÉLECTION DES INSTRUMENTS
# =========================================================

st.sidebar.title("Trading Monitor")

st.sidebar.subheader("Configuration des instruments")

instrument_options = ["Aucun"] + list(PAIRS.keys())

default_instruments = [
    "XAU/USD - Gold",
    "SPX500 - S&P 500",
    "EUR/USD",
    "GBP/USD"
]

instruments_config = []

for i in range(4):

    st.sidebar.markdown(f"**Instrument {i + 1}**")

    default_pair = default_instruments[i]

    pair = st.sidebar.selectbox(
        f"Instrument {i + 1}",
        instrument_options,
        index=instrument_options.index(default_pair),
        key=f"pair_select_{i}"
    )

    timeframe = st.sidebar.selectbox(
        f"Intervalle {i + 1}",
        TIMEFRAMES,
        index=TIMEFRAMES.index("M30"),
        key=f"timeframe_select_{i}"
    )

    if pair != "Aucun":

        instruments_config.append({
            "label": pair,
            "pair": PAIRS[pair],
            "timeframe": timeframe
        })

    st.sidebar.markdown("---")


# =========================================================
# OPTIONS GRAPHIQUES
# =========================================================

st.sidebar.subheader("Indicateurs Smart Money")

mute_alerts = st.sidebar.checkbox(
    "Désactiver les alertes vocales",
    value=False
)

st.sidebar.markdown("#### Alertes d'entrée confirmée")
enable_entry_sound = st.sidebar.checkbox(
    "Son à la confirmation d'entrée",
    value=True
)
enable_entry_email = st.sidebar.checkbox(
    "Courriel à la confirmation d'entrée",
    value=True
)
email_recipient_default = st.secrets.get("ALERT_EMAIL_TO", "")
email_recipient = st.sidebar.text_input(
    "Adresse courriel destinataire",
    value=email_recipient_default,
    placeholder="exemple@domaine.com"
)

show_ema = st.sidebar.checkbox(
    "Afficher EMA 50 / 100 / 200",
    value=False
)

show_fvg = st.sidebar.checkbox(
    "Afficher les Fair Value Gaps",
    value=True
)

show_structure = st.sidebar.checkbox(
    "Afficher BOS / CHoCH",
    value=False
)


# =========================================================
# CALCULATEUR DE RISQUE
# =========================================================

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


# =========================================================
# ALERTES VOCALES
# =========================================================

VOICE_STRONG_BULL = (
    "https://cdn.pixabay.com/download/audio/2023/03/22/"
    "audio_7e47f7d88e.mp3?filename=alert-female-strong-bullish.mp3"
)

VOICE_STRONG_BEAR = (
    "https://cdn.pixabay.com/download/audio/2023/03/22/"
    "audio_2ac24c3bd2.mp3?filename=alert-female-strong-bearish.mp3"
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


def send_entry_email(subject, body, recipient):
    """
    Envoie un courriel si les paramètres SMTP sont définis dans st.secrets.
    Secrets requis : SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
    ALERT_EMAIL_FROM. ALERT_EMAIL_TO peut servir d'adresse par défaut.
    """
    required = [
        "SMTP_SERVER", "SMTP_PORT", "SMTP_USERNAME",
        "SMTP_PASSWORD", "ALERT_EMAIL_FROM"
    ]
    missing = [key for key in required if key not in st.secrets]
    if missing:
        raise RuntimeError(
            "Paramètres SMTP manquants dans les Secrets Streamlit : "
            + ", ".join(missing)
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = st.secrets["ALERT_EMAIL_FROM"]
    message["To"] = recipient
    message.set_content(body)

    server_name = st.secrets["SMTP_SERVER"]
    server_port = int(st.secrets["SMTP_PORT"])
    username = st.secrets["SMTP_USERNAME"]
    password = st.secrets["SMTP_PASSWORD"]

    if server_port == 465:
        with smtplib.SMTP_SSL(server_name, server_port, timeout=20) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(server_name, server_port, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(username, password)
            server.send_message(message)


# =========================================================
# RÉCUPÉRATION DES DONNÉES OANDA
# =========================================================

@st.cache_data(ttl=45)
def get_data(pair, timeframe="M30", count=300, include_incomplete=False):

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

    # Par défaut, l'analyse utilise uniquement les bougies clôturées.
    # Le graphique peut demander la dernière bougie encore en formation.
    if not include_incomplete:
        candles = [
            c for c in candles
            if c.get("complete", False)
        ]

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

    df["time"] = pd.to_datetime(
        df["time"],
        utc=True
    )

    df["time"] = df["time"].dt.tz_convert(
        "America/New_York"
    )

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
        span=50,
        adjust=False
    ).mean()

    df["EMA100"] = df["close"].ewm(
        span=100,
        adjust=False
    ).mean()

    df["EMA200"] = df["close"].ewm(
        span=200,
        adjust=False
    ).mean()

    return df


# =========================================================
# SMART MONEY : BOS / CHoCH
# =========================================================

def detect_market_structure(df):

    df = df.copy()

    window = 5

    rolling_high = df["high"].rolling(
        window,
        center=True
    ).max()

    rolling_low = df["low"].rolling(
        window,
        center=True
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

        pivot_index = i - 2

        if swing_high.iloc[pivot_index]:
            last_high = df["high"].iloc[pivot_index]

        if swing_low.iloc[pivot_index]:
            last_low = df["low"].iloc[pivot_index]

        close_now = df["close"].iloc[i]
        close_prev = df["close"].iloc[i - 1]

        event = None
        event_price = None

        # Cassure haussière

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

        # Cassure baissière

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
                "price": event_price,
                "index": i
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
                "top": float(df["low"].iloc[i]),
                "bottom": float(df["high"].iloc[i - 2]),
                "index": i
            })

        # FVG baissier
        elif df["high"].iloc[i] < df["low"].iloc[i - 2]:

            gaps.append({
                "time": df["time"].iloc[i - 2],
                "end": df["time"].iloc[i],
                "type": "Bearish FVG",
                "top": float(df["low"].iloc[i - 2]),
                "bottom": float(df["high"].iloc[i]),
                "index": i
            })

    return gaps


# =========================================================
# CONFLUENCE MULTI-TIMEFRAME
# =========================================================

def get_ema_direction(df):
    """Détermine la tendance à partir des EMA."""

    if df.empty or len(df) < 200:
        return "Données insuffisantes"

    last = df.iloc[-1]

    if (
        last["EMA50"] > last["EMA100"]
        and last["EMA100"] > last["EMA200"]
    ):
        return "Haussière"

    if (
        last["EMA50"] < last["EMA100"]
        and last["EMA100"] < last["EMA200"]
    ):
        return "Baissière"

    return "Neutre"


def get_structure_direction(events, max_age=30):
    """
    Retourne la dernière structure si elle est suffisamment récente.
    max_age représente le nombre de chandeliers depuis l'événement.
    """

    if not events:
        return "Neutre"

    last_event = events[-1]

    direction = last_event["direction"]

    if direction == 1:
        return f'{last_event["type"]} haussier'

    return f'{last_event["type"]} baissier'


def get_structure_bias(events, candle_count=None, max_age=30):
    if not events:
        return "Neutre"

    last_event = events[-1]

    if candle_count is not None and "index" in last_event:
        age = candle_count - 1 - last_event["index"]
        if age > max_age:
            return "Neutre"

    if last_event["direction"] == 1:
        return "Haussière"

    return "Baissière"


def get_active_fvgs(df):
    """
    Un FVG haussier est considéré comblé si une bougie
    ultérieure atteint son niveau inférieur.

    Un FVG baissier est considéré comblé si une bougie
    ultérieure atteint son niveau supérieur.
    """

    gaps = detect_fvg(df)
    active_gaps = []

    for gap in gaps:

        gap_end = gap["end"]

        later_candles = df[df["time"] > gap_end]

        if gap["type"] == "Bullish FVG":

            mitigated = (
                not later_candles.empty
                and later_candles["low"].min() <= gap["bottom"]
            )

        else:

            mitigated = (
                not later_candles.empty
                and later_candles["high"].max() >= gap["top"]
            )

        if not mitigated:
            active_gaps.append(gap)

    return active_gaps


def calculate_trade_levels(df_m30, active_gaps, direction, current_price, selected_gap=None):
    """
    Calcule des niveaux indicatifs à partir du FVG actif le plus récent,
    des derniers pivots M30 et d'un coussin basé sur l'ATR.
    Aucun niveau n'est envoyé à OANDA.
    """

    result = {
        "direction": direction,
        "entry": None,
        "stop_loss": None,
        "take_profit": None,
        "risk_distance": None,
        "reward_distance": None,
        "rr": None,
        "target_method": "N/D",
        "fvg_zone": "Aucune",
        "status": "Niveaux indisponibles"
    }

    if direction not in ("LONG", "SHORT") or not active_gaps or len(df_m30) < 10:
        return result

    wanted_type = "Bullish FVG" if direction == "LONG" else "Bearish FVG"
    matching_gaps = [g for g in active_gaps if g.get("type") == wanted_type]

    if not matching_gaps:
        result["status"] = "Aucun FVG actif dans le sens du scénario"
        return result

    # Le plan doit utiliser le FVG exact ayant généré le rejet.
    gap = selected_gap if selected_gap in matching_gaps else matching_gaps[-1]
    gap_bottom = float(gap["bottom"])
    gap_top = float(gap["top"])
    entry = (gap_bottom + gap_top) / 2.0

    # Pivots M30 confirmés (rolling window centré de 5 bougies)
    recent = df_m30.tail(120).iloc[:-2].copy()
    highs = recent["high"].astype(float)
    lows = recent["low"].astype(float)

    swing_high_mask = highs.eq(highs.rolling(5, center=True).max())
    swing_low_mask = lows.eq(lows.rolling(5, center=True).min())

    swing_highs = highs[swing_high_mask].dropna().tolist()
    swing_lows = lows[swing_low_mask].dropna().tolist()

    # ATR simplifié sur 14 bougies pour éviter un stop collé au niveau.
    prev_close = df_m30["close"].shift(1)
    true_range = pd.concat(
        [
            df_m30["high"] - df_m30["low"],
            (df_m30["high"] - prev_close).abs(),
            (df_m30["low"] - prev_close).abs()
        ],
        axis=1
    ).max(axis=1)
    atr = float(true_range.tail(14).mean())
    buffer = max(atr * 0.10, abs(entry) * 0.0001)

    if direction == "LONG":
        structural_lows = [v for v in swing_lows if v < entry]
        swing_level = max(structural_lows) if structural_lows else None
        stop_reference = min(gap_bottom, swing_level) if swing_level is not None else gap_bottom
        stop_loss = stop_reference - buffer

        structural_targets = [v for v in swing_highs if v > entry]
        valid_targets = sorted(
            v for v in structural_targets
            if (v - entry) >= (entry - stop_loss) * 1.5
        )
        if valid_targets:
            take_profit = valid_targets[0]
            target_method = "Prochain swing high M30"
        else:
            take_profit = entry + (entry - stop_loss) * 2.0
            target_method = "Projection 2R (aucun swing high assez éloigné)"

        risk_distance = entry - stop_loss
        reward_distance = take_profit - entry

    else:
        structural_highs = [v for v in swing_highs if v > entry]
        swing_level = min(structural_highs) if structural_highs else None
        stop_reference = max(gap_top, swing_level) if swing_level is not None else gap_top
        stop_loss = stop_reference + buffer

        structural_targets = [v for v in swing_lows if v < entry]
        valid_targets = sorted(
            (v for v in structural_targets
             if (entry - v) >= (stop_loss - entry) * 1.5),
            reverse=True
        )
        if valid_targets:
            take_profit = valid_targets[0]
            target_method = "Prochain swing low M30"
        else:
            take_profit = entry - (stop_loss - entry) * 2.0
            target_method = "Projection 2R (aucun swing low assez éloigné)"

        risk_distance = stop_loss - entry
        reward_distance = entry - take_profit

    if risk_distance <= 0 or reward_distance <= 0:
        result["status"] = "Calcul impossible : niveaux incohérents"
        return result

    rr_value = reward_distance / risk_distance

    result.update({
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_distance": risk_distance,
        "reward_distance": reward_distance,
        "rr": rr_value,
        "target_method": target_method,
        "fvg_zone": f"{gap_bottom:.5f} à {gap_top:.5f}",
        "status": "Plan indicatif — à valider"
    })

    if rr_value < 1.5:
        result["status"] = "Ratio inférieur à 1,5 — configuration à éviter"

    return result


def calculate_atr(df, period=14):
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    value = float(tr.tail(period).mean())
    return value if pd.notna(value) and value > 0 else 0.0


def detect_supply_demand_zones(df, lookback=100):
    """Repère des zones M30 à partir de pivots confirmés suivis d'un déplacement.
    Les pivots sont confirmés avec deux bougies à droite : pas de pivot futur utilisé.
    """
    if len(df) < 20:
        return {"demand": None, "supply": None}

    data = df.tail(lookback).reset_index(drop=True).copy()
    atr = calculate_atr(data)
    if atr <= 0:
        return {"demand": None, "supply": None}

    demand_candidates, supply_candidates = [], []
    for i in range(2, len(data) - 4):
        pivot_low = float(data.loc[i, "low"])
        pivot_high = float(data.loc[i, "high"])
        is_low = pivot_low <= float(data.loc[i-2:i+2, "low"].min())
        is_high = pivot_high >= float(data.loc[i-2:i+2, "high"].max())
        future = data.iloc[i+1:i+5]
        if future.empty:
            continue
        # Une zone n'est retenue que si elle a provoqué un déplacement notable.
        if is_low and float(future["high"].max()) - pivot_low >= 0.8 * atr:
            base_low = min(float(data.loc[i, "low"]), float(data.loc[i, "open"]), float(data.loc[i, "close"]))
            base_high = max(float(data.loc[i, "open"]), float(data.loc[i, "close"]))
            demand_candidates.append({"bottom": base_low, "top": max(base_high, base_low + 0.12 * atr), "index": i})
        if is_high and pivot_high - float(future["low"].min()) >= 0.8 * atr:
            base_high = max(float(data.loc[i, "high"]), float(data.loc[i, "open"]), float(data.loc[i, "close"]))
            base_low = min(float(data.loc[i, "open"]), float(data.loc[i, "close"]))
            supply_candidates.append({"bottom": min(base_low, base_high - 0.12 * atr), "top": base_high, "index": i})

    def latest_valid(candidates, kind):
        for zone in reversed(candidates):
            later = data.iloc[zone["index"] + 1:]
            if kind == "demand":
                # Zone invalidée seulement après deux clôtures consécutives sous le bas.
                closes = later["close"].astype(float).tail(2).tolist()
                broken = any(
                    float(later["close"].iloc[j]) < zone["bottom"]
                    and float(later["close"].iloc[j + 1]) < zone["bottom"]
                    for j in range(0, max(0, len(later) - 1))
                )
                if broken:
                    continue
            else:
                closes = later["close"].astype(float).tail(2).tolist()
                broken = any(
                    float(later["close"].iloc[j]) > zone["top"]
                    and float(later["close"].iloc[j + 1]) > zone["top"]
                    for j in range(0, max(0, len(later) - 1))
                )
                if broken:
                    continue
            return zone
        return None

    return {
        "demand": latest_valid(demand_candidates, "demand"),
        "supply": latest_valid(supply_candidates, "supply")
    }


def calculate_zone_trade_plan(df, zone, direction, current_price):
    """Plan indicatif basé sur une zone S/D. Pas d'ordre envoyé."""
    out = {"entry": None, "stop": None, "target": None, "rr": None,
           "status": "Niveaux indisponibles", "distance_atr": None,
           "zone_text": "Aucune", "target_method": "N/D"}
    if zone is None or len(df) < 20:
        return out
    atr = calculate_atr(df)
    if atr <= 0:
        return out
    bottom, top = float(zone["bottom"]), float(zone["top"])
    entry = (bottom + top) / 2
    buffer = max(atr * 0.12, abs(entry) * 0.0001)
    recent = df.tail(100).iloc[:-2]
    if direction == "LONG":
        stop = bottom - buffer
        candidates = recent.loc[recent["high"] > entry, "high"].astype(float)
        candidates = candidates[candidates >= entry + (entry-stop)*1.5]
        target = float(candidates.min()) if not candidates.empty else entry + (entry-stop)*2
        risk, reward = entry-stop, target-entry
        distance = (float(current_price)-entry)/atr
    else:
        stop = top + buffer
        candidates = recent.loc[recent["low"] < entry, "low"].astype(float)
        candidates = candidates[candidates <= entry - (stop-entry)*1.5]
        target = float(candidates.max()) if not candidates.empty else entry - (stop-entry)*2
        risk, reward = stop-entry, entry-target
        distance = (entry-float(current_price))/atr
    rr_value = reward/risk if risk > 0 else None
    if direction == "LONG":
        if current_price > entry + 0.65*atr:
            status = "OCCASION DÉPASSÉE — attendre un nouveau retest"
        elif current_price < bottom - buffer:
            status = "ZONE INVALIDÉE"
        else:
            status = "ENTRÉE ACCESSIBLE À VALIDER" if abs(distance) <= 0.65 else "ATTENDRE LE RETOUR DANS LA ZONE"
    else:
        if current_price < entry - 0.65*atr:
            status = "OCCASION DÉPASSÉE — attendre un nouveau retest"
        elif current_price > top + buffer:
            status = "ZONE INVALIDÉE"
        else:
            status = "ENTRÉE ACCESSIBLE À VALIDER" if abs(distance) <= 0.65 else "ATTENDRE LE RETOUR DANS LA ZONE"
    if rr_value is not None and rr_value < 1.5:
        status = "R/R INSUFFISANT"
    out.update({"entry": entry, "stop": stop, "target": target, "rr": rr_value,
                "status": status, "distance_atr": abs(distance),
                "zone_text": f"{bottom:.5f} à {top:.5f}",
                "target_method": "Pivot M30" if not candidates.empty else "Projection 2R (indicative)"})
    return out


def get_confluence_analysis(pair):
    result = {
        "Prix": "N/D", "EMA50": "N/D", "EMA100": "N/D", "EMA200": "N/D",
        "Prix_vs_EMA50": "N/D", "Prix_vs_EMA100": "N/D", "Prix_vs_EMA200": "N/D",
        "H4": "N/D", "H1": "N/D", "M30": "N/D", "FVG": "Aucun",
        "FVG_actifs": 0, "Zones_FVG_actives": "Aucune", "Setup_M30": "En attente",
        "Prix_dans_FVG": "Non", "Rejet_M30": "Aucun", "Plan_direction": "N/D",
        "Plan_entree": None, "Plan_stop": None, "Plan_tp": None, "Plan_rr": None,
        "Plan_target_method": "N/D", "Plan_fvg_zone": "Aucune", "Plan_status": "Niveaux indisponibles",
        "Alerte_autorisee": False, "Raisons_blocage_alerte": [], "Distance_entree_atr": None,
        "Confirmation_M5": False, "Structure_M5": "N/D", "M5_candle_time": "N/D",
        "Support_resistance_proche": None, "score": 0, "bullish_score": 0,
        "bearish_score": 0, "decision": "ATTENTE", "details": "",
        "Demand_zone": None, "Supply_zone": None, "Scenario_achat": "Aucun setup",
        "Scenario_vente": "Aucun setup", "Scenario_actif": "ATTENDRE"
    }
    try:
        df_h4 = get_data(pair, "H4", CANDLE_COUNT)
        df_h1 = get_data(pair, "H1", CANDLE_COUNT)
        df_m30 = get_data(pair, "M30", CANDLE_COUNT)
        df_m5 = get_data(pair, "M5", CANDLE_COUNT)

        if min(len(df_h4), len(df_h1), len(df_m30)) < 210:
            result["details"] = "Données insuffisantes en H4, H1 ou M30"
            return result
        if len(df_m5) < 30:
            result["details"] = "Données M5 insuffisantes pour confirmer l'entrée"
            return result

        df_h4, df_h1, df_m30 = map(calculate_indicators, (df_h4, df_h1, df_m30))
        df_h1, events_h1 = detect_market_structure(df_h1)
        df_m30, events_m30 = detect_market_structure(df_m30)
        df_m5, events_m5 = detect_market_structure(df_m5)
        current_price = get_current_price(pair)
        if current_price is None:
            current_price = float(df_m30["close"].iloc[-1])
        result["Prix"] = float(current_price)
        last_h4 = df_h4.iloc[-1]
        for n in (50, 100, 200):
            result[f"EMA{n}"] = float(last_h4[f"EMA{n}"])
            result[f"Prix_vs_EMA{n}"] = "Au-dessus" if current_price > last_h4[f"EMA{n}"] else "En dessous"
        h4 = get_ema_direction(df_h4)
        h1 = get_structure_bias(events_h1, len(df_h1), max_age=12)
        m30 = get_structure_bias(events_m30, len(df_m30), max_age=8)

        # M5 sert uniquement de déclencheur d'entrée, jamais de biais principal.
        last_m5 = df_m5.iloc[-1]
        last_m30_time = df_m30["time"].iloc[-1]
        recent_m5_event = next(
            (
                event for event in reversed(events_m5)
                if len(df_m5) - 1 - event["index"] <= 8
                and event["time"] >= last_m30_time
            ),
            None
        )
        m5_structure = "Neutre"
        if recent_m5_event:
            m5_structure = (
                f'{recent_m5_event["type"]} haussier'
                if recent_m5_event["direction"] == 1
                else f'{recent_m5_event["type"]} baissier'
            )

        result.update({
            "H4": h4, "H1": h1, "M30": m30,
            "Structure_M5": m5_structure,
            "M5_candle_time": str(last_m5["time"])
        })

        gaps = get_active_fvgs(df_m30)
        bull_gaps = [g for g in gaps if g["type"] == "Bullish FVG"]
        bear_gaps = [g for g in gaps if g["type"] == "Bearish FVG"]
        fvg = "Mixte" if bull_gaps and bear_gaps else "Haussier" if bull_gaps else "Baissier" if bear_gaps else "Aucun"
        result["FVG"] = fvg
        result["FVG_actifs"] = len(gaps)
        result["Zones_FVG_actives"] = " | ".join(f'{g["type"]}: {g["bottom"]:.5f}-{g["top"]:.5f}' for g in gaps[-4:]) or "Aucune"

        zones = detect_supply_demand_zones(df_m30)
        demand, supply = zones["demand"], zones["supply"]
        result["Demand_zone"] = demand
        result["Supply_zone"] = supply
        atr = calculate_atr(df_m30)
        last = df_m30.iloc[-1]
        prev = df_m30.iloc[-2]
        demand_near = bool(demand and float(current_price) >= demand["bottom"] - 0.15*atr and float(current_price) <= demand["top"] + 1.5*atr)
        supply_near = bool(supply and float(current_price) <= supply["top"] + 0.15*atr and float(current_price) >= supply["bottom"] - 1.5*atr)
        demand_broken = bool(demand and len(df_m30) >= 3 and all(float(v) < demand["bottom"] for v in df_m30["close"].tail(2)))
        supply_broken = bool(supply and len(df_m30) >= 3 and all(float(v) > supply["top"] for v in df_m30["close"].tail(2)))

        # Rejet réel sur la zone: la bougie clôturée touche la zone et clôture hors de celle-ci.
        bull_zone_rejection = bool(demand and float(last["low"]) <= demand["top"] and float(last["close"]) > demand["top"] and float(last["close"]) > float(last["open"]))
        bear_zone_rejection = bool(supply and float(last["high"]) >= supply["bottom"] and float(last["close"]) < supply["bottom"] and float(last["close"]) < float(last["open"]))
        bull_fvg_rejection = any(
            float(last["low"]) <= g["top"] and float(last["high"]) >= g["bottom"]
            and float(last["close"]) > float(last["open"]) and float(last["close"]) > g["top"]
            for g in bull_gaps
        )
        bear_fvg_rejection = any(
            float(last["low"]) <= g["top"] and float(last["high"]) >= g["bottom"]
            and float(last["close"]) < float(last["open"]) and float(last["close"]) < g["bottom"]
            for g in bear_gaps
        )
        recent_bull_structure = bool(events_m30 and events_m30[-1]["direction"] == 1 and len(df_m30)-1-events_m30[-1]["index"] <= 8)
        recent_bear_structure = bool(events_m30 and events_m30[-1]["direction"] == -1 and len(df_m30)-1-events_m30[-1]["index"] <= 8)

        # Un support/demande défendu interdit une vente tant qu'il n'est pas cassé par 2 clôtures.
        block_short_at_demand = demand_near and not demand_broken
        block_long_at_supply = supply_near and not supply_broken
        buy_confirmed = (bull_zone_rejection or bull_fvg_rejection) and recent_bull_structure and not block_long_at_supply
        sell_confirmed = (bear_zone_rejection or bear_fvg_rejection) and recent_bear_structure and not block_short_at_demand

        # Validation M5 : un BOS/CHoCH récent doit confirmer le sens du setup M30.
        # L'événement doit appartenir à la période de la dernière bougie M30 clôturée.
        m5_buy_confirmed = bool(
            buy_confirmed and recent_m5_event
            and recent_m5_event["direction"] == 1
        )
        m5_sell_confirmed = bool(
            sell_confirmed and recent_m5_event
            and recent_m5_event["direction"] == -1
        )
        result["Confirmation_M5"] = bool(m5_buy_confirmed or m5_sell_confirmed)

        # Confluence est informative; elle ne remplace plus le déclencheur de prix.
        bull_score = sum([h4 == "Haussière", h1 == "Haussière", m30 == "Haussière", fvg == "Haussier"])
        bear_score = sum([h4 == "Baissière", h1 == "Baissière", m30 == "Baissière", fvg == "Baissier"])
        result["bullish_score"], result["bearish_score"] = int(bull_score), int(bear_score)
        result["score"] = max(bull_score, bear_score)
        result["decision"] = "ATTENTE" if buy_confirmed and sell_confirmed else "ACHAT POTENTIEL" if buy_confirmed else "VENTE POTENTIELLE" if sell_confirmed else "ATTENTE"
        result["Rejet_M30"] = "Haussier" if buy_confirmed else "Baissier" if sell_confirmed else "Aucun"
        buy_source = "FVG haussier" if bull_fvg_rejection and not bull_zone_rejection else "demande" 
        sell_source = "FVG baissier" if bear_fvg_rejection and not bear_zone_rejection else "offre"
        result["Scenario_achat"] = f"ACHAT À SURVEILLER — rejet {buy_source} + structure" if buy_confirmed else "Demande défendue : attendre confirmation" if demand_near and not demand_broken else "Aucune confirmation acheteuse"
        result["Scenario_vente"] = f"VENTE À SURVEILLER — rejet {sell_source} + structure" if sell_confirmed else "Offre à surveiller" if supply_near and not supply_broken else "Aucune confirmation vendeuse"
        result["Scenario_actif"] = "ACHAT À SURVEILLER" if buy_confirmed else "VENTE À SURVEILLER" if sell_confirmed else "ATTENDRE — scénarios contradictoires ou incomplets"
        result["Setup_M30"] = "ACHAT À VALIDER" if buy_confirmed else "VENTE À VALIDER" if sell_confirmed else "ATTENDRE — zone, rejet et structure non alignés"
        result["details"] = f"{bull_score}/4 haussières contre {bear_score}/4 baissières; déclencheur S/D indépendant du score."

        direction = "LONG" if buy_confirmed and not sell_confirmed else "SHORT" if sell_confirmed and not buy_confirmed else None
        zone = demand if direction == "LONG" else supply if direction == "SHORT" else None
        plan = calculate_zone_trade_plan(df_m30, zone, direction, float(current_price)) if direction and zone else {}
        if direction and zone is None:
            matching = bull_gaps if direction == "LONG" else bear_gaps
            selected_gap = matching[-1] if matching else None
            old_plan = calculate_trade_levels(df_m30, gaps, direction, float(current_price), selected_gap=selected_gap)
            if old_plan.get("entry") is not None:
                atr_now = calculate_atr(df_m30)
                dist = abs(float(current_price) - float(old_plan["entry"])) / atr_now if atr_now else 999
                if direction == "LONG":
                    status = "OCCASION DÉPASSÉE — attendre un nouveau retest" if current_price > old_plan["entry"] + 0.65*atr_now else "ENTRÉE ACCESSIBLE À VALIDER"
                else:
                    status = "OCCASION DÉPASSÉE — attendre un nouveau retest" if current_price < old_plan["entry"] - 0.65*atr_now else "ENTRÉE ACCESSIBLE À VALIDER"
                plan = {"entry": old_plan["entry"], "stop": old_plan["stop_loss"], "target": old_plan["take_profit"],
                        "rr": old_plan["rr"], "status": status if old_plan["rr"] and old_plan["rr"] >= 1.5 else "R/R INSUFFISANT",
                        "distance_atr": dist, "zone_text": old_plan["fvg_zone"], "target_method": old_plan["target_method"]}
        if plan:
            result.update({"Plan_direction": direction, "Plan_entree": plan.get("entry"), "Plan_stop": plan.get("stop"),
                           "Plan_tp": plan.get("target"), "Plan_rr": plan.get("rr"), "Plan_target_method": plan.get("target_method", "N/D"),
                           "Plan_fvg_zone": plan.get("zone_text", "Aucune"), "Plan_status": plan.get("status", "Niveaux indisponibles"), "Distance_entree_atr": plan.get("distance_atr")})

        blocks = []
        if not direction:
            if buy_confirmed and sell_confirmed:
                blocks.append("Signaux acheteur et vendeur simultanés : attendre, aucune alerte")
            if demand_near and not demand_broken:
                blocks.append("Zone de demande défendue : vente bloquée tant que 2 clôtures M30 ne cassent pas son bas")
            if supply_near and not supply_broken:
                blocks.append("Zone d'offre défendue : achat bloqué tant que 2 clôtures M30 ne cassent pas son haut")
            if not (bull_zone_rejection or bear_zone_rejection or bull_fvg_rejection or bear_fvg_rejection):
                blocks.append("Aucun rejet M30 confirmé dans un FVG ou une zone d'offre/demande")
            if not recent_bull_structure and not recent_bear_structure:
                blocks.append("Aucun BOS/CHoCH M30 récent dans le sens du rejet")
        else:
            if direction == "LONG" and not m5_buy_confirmed:
                blocks.append("Attendre un BOS/CHoCH haussier M5 récent après la clôture M30")
            if direction == "SHORT" and not m5_sell_confirmed:
                blocks.append("Attendre un BOS/CHoCH baissier M5 récent après la clôture M30")
            if plan.get("entry") is None:
                blocks.append("Niveaux de risque non calculables")
            if plan.get("status", "").startswith("OCCASION DÉPASSÉE"):
                blocks.append("Le prix a déjà quitté la zone d'entrée : ne pas poursuivre le mouvement")
            if plan.get("status") == "ZONE INVALIDÉE":
                blocks.append("La zone de déclenchement est invalidée")
            if plan.get("rr") is None or plan.get("rr", 0) < 1.5:
                blocks.append("R/R inférieur à 1:1,5")
            if plan.get("target_method", "").startswith("Projection"):
                blocks.append("Cible structurelle absente : projection 2R seulement, pas d'alerte automatique")
        result["Raisons_blocage_alerte"] = blocks
        result["Alerte_autorisee"] = bool(
            direction and not blocks
            and plan.get("status") == "ENTRÉE ACCESSIBLE À VALIDER"
            and (
                (direction == "LONG" and m5_buy_confirmed)
                or (direction == "SHORT" and m5_sell_confirmed)
            )
        )
        result["M30_candle_time"] = str(last["time"])
        result["Prix_dans_FVG"] = "Oui" if any(g["bottom"] <= current_price <= g["top"] for g in gaps) else "Non"
        result["Support_resistance_proche"] = demand if demand_near else supply if supply_near else None
        return result
    except Exception as e:
        result["details"] = f"Erreur analyse : {e}"
        return result


def build_decision_assistant(analysis):
    """
    Distingue le biais de marché d'une configuration d'entrée.
    Aucun ordre n'est envoyé automatiquement.
    """

    decision = analysis.get("decision", "ATTENTE")
    setup = analysis.get("Setup_M30", "En attente")
    scenario_buy = analysis.get("Scenario_achat", "Aucun setup")
    scenario_sell = analysis.get("Scenario_vente", "Aucun setup")
    price_vs_200 = analysis.get("Prix_vs_EMA200", "N/D")
    h4 = analysis.get("H4", "N/D")
    h1 = analysis.get("H1", "N/D")
    m30 = analysis.get("M30", "N/D")
    fvg = analysis.get("FVG", "Aucun")
    bull = analysis.get("bullish_score", 0)
    bear = analysis.get("bearish_score", 0)
    zones = analysis.get("Zones_FVG_actives", "Aucune")
    rejection = analysis.get("Rejet_M30", "Aucun")
    m5_confirmed = analysis.get("Confirmation_M5", False)
    m5_structure = analysis.get("Structure_M5", "N/D")

    if decision == "ACHAT POTENTIEL":
        if setup == "ACHAT À VALIDER" and m5_confirmed:
            verdict = "CONFIGURATION D'ACHAT — VALIDATION MANUELLE"
            confirmation = (
                "La zone a été rejetée à la hausse, la structure M30 est favorable "
                "et un BOS/CHoCH haussier M5 confirme le déclenchement. "
                "Vérifier l'accessibilité de l'entrée, le stop et le R/R."
            )
        elif setup == "ACHAT À VALIDER":
            verdict = "ACHAT À SURVEILLER — ATTENTE CONFIRMATION M5"
            confirmation = (
                "Le rejet et la structure M30 sont présents, mais le M5 n'a pas "
                "encore confirmé par un BOS/CHoCH haussier clôturé. Ne pas anticiper."
            )
        elif setup.startswith("ZONE HAUSSIÈRE"):
            verdict = "ZONE D'ACHAT ATTEINTE — ATTENDRE"
            confirmation = (
                "Le prix se trouve dans un FVG haussier actif. "
                "Attendre une bougie M30 haussière qui rejette la zone."
            )
        else:
            verdict = "BIAIS HAUSSIER — PAS ENCORE D'ENTRÉE"
            confirmation = (
                "Attendre un retour du prix dans un FVG haussier actif, "
                "puis une confirmation de rejet haussier en M30."
            )
        invalidation = (
            "Réévaluer le scénario si la structure M30 devient baissière "
            "ou si le prix clôture sous l'EMA 200 H4."
        )

    elif decision == "VENTE POTENTIELLE":
        if setup == "VENTE À VALIDER" and m5_confirmed:
            verdict = "CONFIGURATION DE VENTE — VALIDATION MANUELLE"
            confirmation = (
                "La zone a été rejetée à la baisse, la structure M30 est favorable "
                "et un BOS/CHoCH baissier M5 confirme le déclenchement. "
                "Vérifier l'accessibilité de l'entrée, le stop et le R/R."
            )
        elif setup == "VENTE À VALIDER":
            verdict = "VENTE À SURVEILLER — ATTENTE CONFIRMATION M5"
            confirmation = (
                "Le rejet et la structure M30 sont présents, mais le M5 n'a pas "
                "encore confirmé par un BOS/CHoCH baissier clôturé. Ne pas anticiper."
            )
        elif setup.startswith("ZONE BAISSIÈRE"):
            verdict = "ZONE DE VENTE ATTEINTE — ATTENDRE"
            confirmation = (
                "Le prix se trouve dans un FVG baissier actif. "
                "Attendre une bougie M30 baissière qui rejette la zone."
            )
        else:
            verdict = "BIAIS BAISSIER — PAS ENCORE D'ENTRÉE"
            confirmation = (
                "Attendre un retour du prix dans un FVG baissier actif, "
                "puis une confirmation de rejet baissier en M30."
            )
        invalidation = (
            "Réévaluer le scénario si la structure M30 devient haussière "
            "ou si le prix clôture au-dessus de l'EMA 200 H4."
        )

    else:
        verdict = "ATTENTE — CONFLUENCE INSUFFISANTE"
        confirmation = (
            "Attendre un alignement plus clair entre H4, H1 et M30. "
            "Ne pas transformer un mouvement isolé en signal d'entrée."
        )
        invalidation = "Aucun scénario directionnel prioritaire pour le moment."

    return {
        "verdict": verdict,
        "confirmation": confirmation,
        "invalidation": invalidation,
        "lecture": (
            f"Confluence : {bull}/4 haussières contre {bear}/4 baissières. "
            f"H4 : {h4} | H1 : {h1} | M30 : {m30} | M5 : {m5_structure}. FVG : {fvg}."
        ),
        "setup": setup,
        "scenario_buy": scenario_buy,
        "scenario_sell": scenario_sell,
        "rejection": rejection,
        "zones": zones,
        "entry": analysis.get("Plan_entree"),
        "stop": analysis.get("Plan_stop"),
        "target": analysis.get("Plan_tp"),
        "rr": analysis.get("Plan_rr"),
        "target_method": analysis.get("Plan_target_method", "N/D"),
        "plan_status": analysis.get("Plan_status", "Niveaux indisponibles"),
        "plan_direction": analysis.get("Plan_direction", "N/D"),
        "plan_fvg_zone": analysis.get("Plan_fvg_zone", "Aucune")
    }


def trigger_confirmed_entry_alert(pair, label, analysis):
    """
    Déclenche une seule alerte par instrument, direction et bougie M30.
    Une configuration n'est considérée confirmée que si le rejet M30 est
    présent et que le plan offre au moins 1,5R avec des niveaux calculés.
    """
    setup = analysis.get("Setup_M30")

    # Les alertes sont bloquées tant que tous les filtres renforcés ne passent pas.
    if not analysis.get("Alerte_autorisee", False):
        return

    if setup == "ACHAT À VALIDER":
        direction = "ACHAT"
        voice = VOICE_STRONG_BULL
        emoji = "🟢"
    elif setup == "VENTE À VALIDER":
        direction = "VENTE"
        voice = VOICE_STRONG_BEAR
        emoji = "🔴"
    else:
        return

    entry = analysis.get("Plan_entree")
    stop = analysis.get("Plan_stop")
    target = analysis.get("Plan_tp")
    rr_value = analysis.get("Plan_rr")

    if (
        entry is None or stop is None or target is None
        or rr_value is None or rr_value < 1.5
    ):
        return

    candle_time = analysis.get("M30_candle_time", "M30-courante")
    alert_key = f"entry_{pair}_{direction}_{candle_time}"

    if st.session_state.get(alert_key):
        return

    # Marquer immédiatement pour éviter les répétitions à chaque actualisation.
    st.session_state[alert_key] = True

    message_lines = [
        f"{emoji} CONFIGURATION À SURVEILLER {direction} — {label}",
        f"Instrument : {pair}",
        f"Prix actuel : {analysis.get('Prix', 'N/D')}",
        f"Entrée indicative (milieu zone offre/demande) : {entry}",
        f"Stop Loss indicatif : {stop}",
        f"Take Profit indicatif : {target}",
        f"Ratio risque/rendement : 1:{rr_value:.2f}",
        f"Zone offre/demande : {analysis.get('Plan_fvg_zone', 'N/D')}",
        f"Confirmation : rejet M30 + structure M30 + BOS/CHoCH M5",
        f"Structure M5 : {analysis.get('Structure_M5', 'N/D')}",
        f"Bougie M30 : {candle_time}",
        "",
        "Signal informatif seulement : vérifier le graphique et les niveaux "
        "avant toute décision. Aucun ordre n'a été envoyé."
    ]
    email_body = "\n".join(message_lines)

    st.session_state["last_entry_alert_message"] = (
        f"{emoji} **Configuration {direction} à surveiller — {label}** "
        f"| R/R : 1:{rr_value:.2f}"
    )

    if enable_entry_sound and not mute_alerts:
        play_voice_alert(voice)

    if enable_entry_email:
        if not email_recipient.strip():
            st.session_state["last_entry_email_status"] = (
                "Courriel non envoyé : ajoute une adresse destinataire dans la barre latérale."
            )
        else:
            try:
                send_entry_email(
                    f"Configuration {direction} à surveiller — {label}",
                    email_body,
                    email_recipient.strip()
                )
                st.session_state["last_entry_email_status"] = (
                    f"Courriel envoyé à {email_recipient.strip()}."
                )
            except Exception as exc:
                st.session_state["last_entry_email_status"] = (
                    f"Échec de l'envoi du courriel : {exc}"
                )


def create_chart(
    df,
    gaps,
    events,
    timeframe,
    show_ema,
    show_fvg,
    show_structure
):

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

        fig.add_trace(
            go.Scatter(
                x=df["time"],
                y=df["EMA50"],
                name="EMA 50",
                line=dict(color="blue", width=1.5)
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df["time"],
                y=df["EMA100"],
                name="EMA 100",
                line=dict(color="gray", width=1.5)
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df["time"],
                y=df["EMA200"],
                name="EMA 200",
                line=dict(color="orange", width=2)
            )
        )

    # FVG

    if show_fvg:

        for gap in gaps[-8:]:

            color = (
                "rgba(0,200,83,0.16)"
                if gap["type"] == "Bullish FVG"
                else "rgba(255,82,82,0.16)"
            )

            fig.add_shape(
                type="rect",
                x0=gap["time"],
                x1=df["time"].iloc[-1]
                + TIMEFRAME_DURATION[timeframe],
                y0=gap["bottom"],
                y1=gap["top"],
                fillcolor=color,
                line=dict(width=1, color=color),
                layer="below"
            )

    # BOS / CHoCH

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
                font=dict(
                    color=color,
                    size=11
                ),
                bgcolor="rgba(0,0,0,0.65)",
                ax=0,
                ay=-35 if bullish else 35
            )

    fig.update_layout(
        height=520,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        title=f"Smart Money Concepts - {timeframe}",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(
            l=40,
            r=30,
            t=80,
            b=40
        )
    )

    return fig


# =========================================================
# PAGE PRINCIPALE
# =========================================================

st.title("Trading Monitor")

st.caption(
    "Smart Money Lite | OANDA | "
    "Sélection personnalisée des instruments et timeframes"
)

st.markdown("---")

if st.session_state.get("last_entry_alert_message"):
    st.success(st.session_state["last_entry_alert_message"])
if st.session_state.get("last_entry_email_status"):
    st.caption(st.session_state["last_entry_email_status"])


# =========================================================
# TABLEAU DE CONFLUENCE MULTI-TIMEFRAME
# =========================================================

if instruments_config:
    st.subheader("Vue d'ensemble")
    summary_rows = []
    seen_pairs = set()
    for config in instruments_config:
        pair = config["pair"]
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        a = get_confluence_analysis(pair)
        summary_rows.append({
            "Marché": config["label"],
            "Biais": a["decision"],
            "H4": a["H4"],
            "H1": a["H1"],
            "M30": a["M30"],
            "Configuration M30": a["Setup_M30"],
            "Confirmation M5": "Confirmée" if a.get("Confirmation_M5") else "En attente",
            "R/R": f'1:{a["Plan_rr"]:.2f}' if a["Plan_rr"] is not None else "—"
        })
    if summary_rows:
        st.dataframe(
            pd.DataFrame(summary_rows),
            use_container_width=True,
            hide_index=True
        )
        st.caption("Les alertes exigent un rejet M30 confirmé sur une zone d’offre/demande, une structure récente, une entrée encore accessible et un R/R suffisant.")



if not instruments_config:

    st.warning(
        "Sélectionne au moins un instrument dans le menu de gauche."
    )


# =========================================================
# ANALYSE DE CHAQUE INSTRUMENT SÉLECTIONNÉ
# =========================================================

for config in instruments_config:

    label = config["label"]
    pair = config["pair"]
    timeframe = config["timeframe"]

    st.header(f"{label} — {timeframe}")

    try:

        # Données clôturées : utilisées pour les indicateurs, BOS/CHoCH,
        # FVG et décisions afin d'éviter les faux signaux intrabougie.
        df = get_data(
            pair,
            timeframe,
            CANDLE_COUNT
        )

        # Données incluant la bougie en formation : réservées à l'affichage.
        chart_df = get_data(
            pair,
            timeframe,
            CANDLE_COUNT,
            include_incomplete=True
        )

        if df.empty or len(df) < 210:

            st.warning(
                f"Données insuffisantes pour {label} en {timeframe}."
            )

            continue

        df = calculate_indicators(df)

        df, events = detect_market_structure(df)

        if not chart_df.empty:
            chart_df = calculate_indicators(chart_df)
        else:
            chart_df = df.copy()

        # Affichage et historique : FVG actifs uniquement
        gaps = get_active_fvgs(df)

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
        # STRUCTURE DU MARCHÉ
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

            structure_status = "Aucun événement"

        # ---------------------------------------------
        # Résumé visuel compact
        st.caption(
            f"Prix : {current_price:.5f} | EMA : {ema_status} | "
            f"Structure M30 : {structure_status} | FVG actifs : {len(gaps)}"
        )

        # ASSISTANT DE DÉCISION
        # ---------------------------------------------

        assistant_analysis = get_confluence_analysis(pair)
        assistant = build_decision_assistant(assistant_analysis)

        trigger_confirmed_entry_alert(pair, label, assistant_analysis)

        blocked_reasons = assistant_analysis.get("Raisons_blocage_alerte", [])
        if blocked_reasons and assistant_analysis.get("Setup_M30") in (
            "ACHAT À VALIDER", "VENTE À VALIDER"
        ):
            with st.expander("Pourquoi aucune alerte n'a été envoyée?"):
                for reason in blocked_reasons:
                    st.write(f"• {reason}")

        with st.container(border=True):
            st.subheader("Assistant de décision")
            st.markdown(f"**{assistant['verdict']}**")
            st.write(assistant["lecture"])
            st.markdown("#### Scénarios surveillés")
            st.write(f"🟢 **Achat :** {assistant.get('scenario_buy', 'N/D')}")
            st.write(f"🔴 **Vente :** {assistant.get('scenario_sell', 'N/D')}")
            st.markdown("#### Plan indicatif — niveaux M30")
            if assistant["entry"] is not None:
                p1, p2, p3, p4 = st.columns(4)
                p1.metric("Entrée théorique", f"{assistant['entry']:.5f}")
                p2.metric("Stop Loss", f"{assistant['stop']:.5f}")
                p3.metric("Take Profit", f"{assistant['target']:.5f}")
                p4.metric(
                    "Ratio R/R",
                    f"1:{assistant['rr']:.2f}" if assistant["rr"] is not None else "N/D"
                )
                st.caption(
                    f"Zone offre/demande : {assistant['plan_fvg_zone']} | "
                    f"Cible : {assistant['target_method']} | "
                    f"{assistant['plan_status']}"
                )
            else:
                st.info(assistant["plan_status"])

            with st.expander("Détails et raisons d'attendre"):
                st.write(f"**H4 :** {assistant_analysis['H4']} | **H1 :** {assistant_analysis['H1']} | **M30 :** {assistant_analysis['M30']}")
                st.write(f"**Setup :** {assistant['setup']}")
                st.write(f"**Rejet M30 :** {assistant['rejection']}")
                st.write(f"**Structure M5 :** {assistant_analysis.get('Structure_M5', 'N/D')}")
                st.write(f"**Confirmation M5 :** {'Oui' if assistant_analysis.get('Confirmation_M5') else 'Non — attendre'}")
                st.write(f"**Zone de demande :** {assistant_analysis.get('Demand_zone')}")
                st.write(f"**Zone d’offre :** {assistant_analysis.get('Supply_zone')}")
                st.write(f"**Zone retenue :** {assistant['plan_fvg_zone']}")
                st.write(f"**Cible :** {assistant['target_method']}")
                st.write(f"**Zones FVG actives :** {assistant['zones']}")
                st.write(f"**Confirmation :** {assistant['confirmation']}")
                st.write(f"**Invalidation :** {assistant['invalidation']}")
                for reason in assistant_analysis.get("Raisons_blocage_alerte", []):
                    st.write(f"• {reason}")
            st.caption("Aucun ordre n'est envoyé automatiquement. Les niveaux restent indicatifs et doivent être validés sur le graphique.")

        # ---------------------------------------------
        # HISTORIQUE FVG
        # ---------------------------------------------

        with st.expander("Voir les FVG actifs uniquement"):

            if gaps:

                fvg_df = pd.DataFrame(
                    gaps[-10:][::-1]
                )

                fvg_df = fvg_df[
                    ["time", "type", "top", "bottom"]
                ]

                st.dataframe(
                    fvg_df,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.write("Aucun FVG actif : les zones détectées ont été comblées ou aucune zone ne subsiste.")

        # ---------------------------------------------
        # HISTORIQUE BOS / CHoCH
        # ---------------------------------------------

        with st.expander("Historique BOS / CHoCH"):

            if events:

                events_df = pd.DataFrame(
                    events[-15:][::-1]
                )

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

        fig = create_chart(
            chart_df,
            gaps,
            events,
            timeframe,
            show_ema,
            show_fvg,
            show_structure
        )

        latest_chart_time = chart_df["time"].iloc[-1]
        latest_closed_time = df["time"].iloc[-1]

        if latest_chart_time > latest_closed_time:
            st.caption(
                f"🟡 Bougie en formation depuis "
                f"{latest_chart_time.strftime('%H:%M')} — "
                "elle évolue avec les actualisations du tableau. "
                "Les signaux restent calculés sur les bougies clôturées."
            )
        else:
            st.caption(
                f"Dernière bougie clôturée : "
                f"{latest_closed_time.strftime('%H:%M')} — "
                "aucune bougie active retournée par OANDA pour le moment."
            )

        st.plotly_chart(
            fig,
            use_container_width=True,
            key=f"chart_{pair}_{timeframe}"
        )

        st.markdown("---")

    except Exception as e:

        st.error(
            f"Erreur pour {label} ({timeframe}) : {e}"
        )


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

