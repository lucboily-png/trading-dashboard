
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


def get_confluence_analysis(pair):

    result = {
        "Prix": "N/D",
        "EMA50": "N/D",
        "EMA100": "N/D",
        "EMA200": "N/D",
        "Prix_vs_EMA50": "N/D",
        "Prix_vs_EMA100": "N/D",
        "Prix_vs_EMA200": "N/D",
        "H4": "N/D",
        "H1": "N/D",
        "M30": "N/D",
        "FVG": "Aucun",
        "FVG_actifs": 0,
        "Zones_FVG_actives": "Aucune",
        "Setup_M30": "En attente",
        "Prix_dans_FVG": "Non",
        "Rejet_M30": "Aucun",
        "Plan_direction": "N/D",
        "Plan_entree": None,
        "Plan_stop": None,
        "Plan_tp": None,
        "Plan_rr": None,
        "Plan_target_method": "N/D",
        "Plan_fvg_zone": "Aucune",
        "Plan_status": "Niveaux indisponibles",
        "Alerte_autorisee": False,
        "Raisons_blocage_alerte": [],
        "Distance_entree_atr": None,
        "Support_resistance_proche": None,
        "score": 0,
        "bullish_score": 0,
        "bearish_score": 0,
        "decision": "ATTENTE",
        "details": ""
    }

    try:

        df_h4 = get_data(pair, "H4", CANDLE_COUNT)
        df_h1 = get_data(pair, "H1", CANDLE_COUNT)
        df_m30 = get_data(pair, "M30", CANDLE_COUNT)

        if (
            len(df_h4) < 210
            or len(df_h1) < 210
            or len(df_m30) < 210
        ):
            result["details"] = "Données insuffisantes"
            return result

        df_h4 = calculate_indicators(df_h4)
        df_h1 = calculate_indicators(df_h1)
        df_m30 = calculate_indicators(df_m30)

        df_h1, events_h1 = detect_market_structure(df_h1)
        df_m30, events_m30 = detect_market_structure(df_m30)

        # Prix actuel obtenu sur M1
        current_price = get_current_price(pair)

        if current_price is None:
            current_price = float(df_h4["close"].iloc[-1])

        # EMA H4
        last_h4 = df_h4.iloc[-1]

        ema50 = float(last_h4["EMA50"])
        ema100 = float(last_h4["EMA100"])
        ema200 = float(last_h4["EMA200"])

        result["Prix"] = current_price
        result["EMA50"] = ema50
        result["EMA100"] = ema100
        result["EMA200"] = ema200

        result["Prix_vs_EMA50"] = (
            "Au-dessus" if current_price > ema50 else "En dessous"
        )

        result["Prix_vs_EMA100"] = (
            "Au-dessus" if current_price > ema100 else "En dessous"
        )

        result["Prix_vs_EMA200"] = (
            "Au-dessus" if current_price > ema200 else "En dessous"
        )

        # Tendances
        h4_direction = get_ema_direction(df_h4)

        h1_direction = get_structure_bias(
            events_h1,
            len(df_h1)
        )

        m30_direction = get_structure_bias(
            events_m30,
            len(df_m30)
        )

        result["H4"] = h4_direction
        result["H1"] = h1_direction
        result["M30"] = m30_direction

        # FVG actifs
        active_gaps = get_active_fvgs(df_m30)

        bullish_fvg = any(
            gap["type"] == "Bullish FVG"
            for gap in active_gaps
        )

        bearish_fvg = any(
            gap["type"] == "Bearish FVG"
            for gap in active_gaps
        )

        if bullish_fvg and bearish_fvg:
            fvg_direction = "Mixte"
        elif bullish_fvg:
            fvg_direction = "Haussier"
        elif bearish_fvg:
            fvg_direction = "Baissier"
        else:
            fvg_direction = "Aucun"

        result["FVG"] = fvg_direction
        result["FVG_actifs"] = len(active_gaps)

        if active_gaps:
            zone_descriptions = []
            for gap in active_gaps[-5:]:
                zone_descriptions.append(
                    f'{gap["type"]}: {gap["bottom"]:.5f} à {gap["top"]:.5f}'
                )
            result["Zones_FVG_actives"] = " | ".join(zone_descriptions)

        # Validation du retour dans un FVG et du rejet sur la dernière M30 complète.
        last_m30 = df_m30.iloc[-1]
        result["M30_candle_time"] = str(last_m30["time"])
        price_in_bullish_fvg = False
        price_in_bearish_fvg = False
        bullish_rejection = False
        bearish_rejection = False

        for gap in active_gaps:
            price_inside = gap["bottom"] <= current_price <= gap["top"]
            candle_touched_zone = (
                float(last_m30["low"]) <= gap["top"]
                and float(last_m30["high"]) >= gap["bottom"]
            )

            if gap["type"] == "Bullish FVG":
                price_in_bullish_fvg = price_in_bullish_fvg or price_inside
                if (
                    candle_touched_zone
                    and float(last_m30["close"]) > float(last_m30["open"])
                    and float(last_m30["close"]) > gap["top"]
                ):
                    bullish_rejection = True

            elif gap["type"] == "Bearish FVG":
                price_in_bearish_fvg = price_in_bearish_fvg or price_inside
                if (
                    candle_touched_zone
                    and float(last_m30["close"]) < float(last_m30["open"])
                    and float(last_m30["close"]) < gap["bottom"]
                ):
                    bearish_rejection = True

        if price_in_bullish_fvg or price_in_bearish_fvg:
            result["Prix_dans_FVG"] = "Oui"

        if bullish_rejection:
            result["Rejet_M30"] = "Haussier"
        elif bearish_rejection:
            result["Rejet_M30"] = "Baissier"

        # Confluence
        bullish_score = 0
        bearish_score = 0

        if h4_direction == "Haussière":
            bullish_score += 1
        elif h4_direction == "Baissière":
            bearish_score += 1

        if h1_direction == "Haussière":
            bullish_score += 1
        elif h1_direction == "Baissière":
            bearish_score += 1

        if m30_direction == "Haussière":
            bullish_score += 1
        elif m30_direction == "Baissière":
            bearish_score += 1

        if fvg_direction == "Haussier":
            bullish_score += 1
        elif fvg_direction == "Baissier":
            bearish_score += 1

        result["bullish_score"] = bullish_score
        result["bearish_score"] = bearish_score
        result["score"] = max(bullish_score, bearish_score)

        if bullish_score >= 3 and bullish_score > bearish_score:
            result["decision"] = "ACHAT POTENTIEL"
            result["details"] = f"{bullish_score}/4 confirmations haussières"

        elif bearish_score >= 3 and bearish_score > bullish_score:
            result["decision"] = "VENTE POTENTIELLE"
            result["details"] = f"{bearish_score}/4 confirmations baissières"

        else:
            result["decision"] = "ATTENTE"
            result["details"] = "Confluence insuffisante ou contradictoire"

        # La tendance seule ne constitue pas un signal d'entrée.
        if result["decision"] == "ACHAT POTENTIEL":
            if bullish_rejection:
                result["Setup_M30"] = "ACHAT À VALIDER"
            elif price_in_bullish_fvg:
                result["Setup_M30"] = "ZONE HAUSSIÈRE ATTEINTE — attendre rejet"
            else:
                result["Setup_M30"] = "ATTENDRE RETOUR DANS FVG HAUSSIER"

        elif result["decision"] == "VENTE POTENTIELLE":
            if bearish_rejection:
                result["Setup_M30"] = "VENTE À VALIDER"
            elif price_in_bearish_fvg:
                result["Setup_M30"] = "ZONE BAISSIÈRE ATTEINTE — attendre rejet"
            else:
                result["Setup_M30"] = "ATTENDRE RETOUR DANS FVG BAISSIER"

        else:
            result["Setup_M30"] = "PAS DE SETUP — confluence insuffisante"

        trade_direction = None
        if result["decision"] == "ACHAT POTENTIEL":
            trade_direction = "LONG"
        elif result["decision"] == "VENTE POTENTIELLE":
            trade_direction = "SHORT"

        # Revalidation stricte : le rejet doit provenir du FVG précis
        # le plus récent dans le sens du scénario, et non de n'importe quel FVG.
        selected_gap = None
        exact_rejection = None
        if trade_direction:
            wanted_type = "Bullish FVG" if trade_direction == "LONG" else "Bearish FVG"
            fresh_matching = [
                gap for gap in active_gaps
                if gap.get("type") == wanted_type
                and len(df_m30) - 1 - gap.get("index", -9999) <= 40
            ]
            if fresh_matching:
                candidate_gap = fresh_matching[-1]
                candle_touched = (
                    float(last_m30["low"]) <= float(candidate_gap["top"])
                    and float(last_m30["high"]) >= float(candidate_gap["bottom"])
                )
                if trade_direction == "LONG":
                    valid_rejection = (
                        candle_touched
                        and float(last_m30["close"]) > float(last_m30["open"])
                        and float(last_m30["close"]) > float(candidate_gap["top"])
                    )
                    if valid_rejection:
                        exact_rejection = "Haussier"
                else:
                    valid_rejection = (
                        candle_touched
                        and float(last_m30["close"]) < float(last_m30["open"])
                        and float(last_m30["close"]) < float(candidate_gap["bottom"])
                    )
                    if valid_rejection:
                        exact_rejection = "Baissier"

                if valid_rejection:
                    selected_gap = candidate_gap

            # Une réaction récente et opposée dans un FVG neutralise le setup.
            opposite_type = "Bearish FVG" if trade_direction == "LONG" else "Bullish FVG"
            opposite_gaps = [
                gap for gap in active_gaps
                if gap.get("type") == opposite_type
                and len(df_m30) - 1 - gap.get("index", -9999) <= 8
            ]
            for opposite_gap in opposite_gaps:
                touched = (
                    float(last_m30["low"]) <= float(opposite_gap["top"])
                    and float(last_m30["high"]) >= float(opposite_gap["bottom"])
                )
                opposite_rejection = (
                    touched
                    and (
                        (float(last_m30["close"]) < float(last_m30["open"])
                         and float(last_m30["close"]) < float(opposite_gap["bottom"]))
                        if trade_direction == "LONG"
                        else
                        (float(last_m30["close"]) > float(last_m30["open"])
                         and float(last_m30["close"]) > float(opposite_gap["top"]))
                    )
                )
                if opposite_rejection:
                    selected_gap = None
                    exact_rejection = None
                    result["Raisons_blocage_alerte"].append(
                        "Réaction opposée récente dans un FVG"
                    )
                    break

        result["Rejet_M30"] = exact_rejection or "Aucun"
        if trade_direction == "LONG":
            result["Setup_M30"] = (
                "ACHAT À VALIDER" if exact_rejection
                else "ATTENDRE — retest/rejet du FVG haussier précis"
            )
        elif trade_direction == "SHORT":
            result["Setup_M30"] = (
                "VENTE À VALIDER" if exact_rejection
                else "ATTENDRE — retest/rejet du FVG baissier précis"
            )

        trade_plan = calculate_trade_levels(
            df_m30,
            active_gaps,
            trade_direction if selected_gap else None,
            current_price,
            selected_gap=selected_gap
        )

        result["Plan_direction"] = trade_plan["direction"] or "N/D"
        result["Plan_entree"] = trade_plan["entry"]
        result["Plan_stop"] = trade_plan["stop_loss"]
        result["Plan_tp"] = trade_plan["take_profit"]
        result["Plan_rr"] = trade_plan["rr"]
        result["Plan_target_method"] = trade_plan["target_method"]
        result["Plan_fvg_zone"] = trade_plan["fvg_zone"]
        result["Plan_status"] = trade_plan["status"]

        # Filtres stricts avant toute alerte.
        block_reasons = []
        alert_direction = trade_direction

        if alert_direction:
            expected_bias = "Baissière" if alert_direction == "SHORT" else "Haussière"
            expected_structure = -1 if alert_direction == "SHORT" else 1

            if h4_direction != expected_bias:
                block_reasons.append(f"Tendance H4 non alignée ({h4_direction})")

            latest_h1_event = events_h1[-1] if events_h1 else None
            if (
                latest_h1_event is None
                or latest_h1_event.get("direction") != expected_structure
                or latest_h1_event.get("type") not in ("BOS", "CHoCH")
                or (len(df_h1) - 1 - latest_h1_event.get("index", -999)) > 12
            ):
                block_reasons.append("Structure H1 absente, opposée ou trop ancienne")

            latest_m30_event = events_m30[-1] if events_m30 else None
            if (
                latest_m30_event is None
                or latest_m30_event.get("direction") != expected_structure
                or latest_m30_event.get("type") not in ("BOS", "CHoCH")
                or (len(df_m30) - 1 - latest_m30_event.get("index", -999)) > 8
            ):
                block_reasons.append("Structure M30 absente, opposée ou trop ancienne")

            required_rejection = "Baissier" if alert_direction == "SHORT" else "Haussier"
            if result["Rejet_M30"] != required_rejection:
                block_reasons.append("Rejet M30 confirmé manquant")

            if trade_plan["entry"] is None or trade_plan["stop_loss"] is None:
                block_reasons.append("Niveaux d'entrée/stop indisponibles")
            else:
                prev_close = df_m30["close"].shift(1)
                true_range = pd.concat(
                    [
                        df_m30["high"] - df_m30["low"],
                        (df_m30["high"] - prev_close).abs(),
                        (df_m30["low"] - prev_close).abs()
                    ],
                    axis=1
                ).max(axis=1)
                atr_alert = float(true_range.tail(14).mean())
                entry_distance_atr = (
                    abs(float(current_price) - float(trade_plan["entry"])) / atr_alert
                    if atr_alert > 0 else float("inf")
                )
                result["Distance_entree_atr"] = entry_distance_atr

                if entry_distance_atr > 1.0:
                    block_reasons.append(
                        "Prix trop éloigné de l'entrée théorique (plus de 1 ATR)"
                    )

                # Exiger une cible basée sur un vrai pivot, pas une projection 2R.
                if "Prochain swing" not in trade_plan["target_method"]:
                    block_reasons.append(
                        "Aucun support/résistance structurel utilisable comme cible"
                    )

                recent_alert = df_m30.tail(120).copy()
                highs_alert = recent_alert["high"].astype(float)
                lows_alert = recent_alert["low"].astype(float)
                swing_high_mask = highs_alert.eq(highs_alert.rolling(5, center=True).max())
                swing_low_mask = lows_alert.eq(lows_alert.rolling(5, center=True).min())

                if alert_direction == "SHORT":
                    supports = lows_alert[
                        swing_low_mask & (lows_alert < float(current_price))
                    ].dropna()
                    nearest_level = float(supports.max()) if not supports.empty else None
                    result["Support_resistance_proche"] = nearest_level
                    if nearest_level is None:
                        block_reasons.append("Aucun support M30 identifiable sous le prix")
                    else:
                        risk_distance = float(trade_plan["stop_loss"]) - float(trade_plan["entry"])
                        free_space = float(current_price) - nearest_level
                        if free_space < risk_distance * 1.5:
                            block_reasons.append(
                                "Prix trop proche d'un support M30 : vente bloquée"
                            )
                else:
                    resistances = highs_alert[
                        swing_high_mask & (highs_alert > float(current_price))
                    ].dropna()
                    nearest_level = float(resistances.min()) if not resistances.empty else None
                    result["Support_resistance_proche"] = nearest_level
                    if nearest_level is None:
                        block_reasons.append(
                            "Aucune résistance M30 identifiable au-dessus du prix"
                        )
                    else:
                        risk_distance = float(trade_plan["entry"]) - float(trade_plan["stop_loss"])
                        free_space = nearest_level - float(current_price)
                        if free_space < risk_distance * 1.5:
                            block_reasons.append(
                                "Prix trop proche d'une résistance M30 : achat bloqué"
                            )

            if trade_plan["rr"] is None or trade_plan["rr"] < 1.5:
                block_reasons.append("Ratio risque/rendement inférieur à 1:1,5")

        result["Raisons_blocage_alerte"] = block_reasons
        result["Alerte_autorisee"] = bool(alert_direction and not block_reasons)

    except Exception as e:
        result["details"] = str(e)

    return result


def build_decision_assistant(analysis):
    """
    Distingue le biais de marché d'une configuration d'entrée.
    Aucun ordre n'est envoyé automatiquement.
    """

    decision = analysis.get("decision", "ATTENTE")
    setup = analysis.get("Setup_M30", "En attente")
    price_vs_200 = analysis.get("Prix_vs_EMA200", "N/D")
    h4 = analysis.get("H4", "N/D")
    h1 = analysis.get("H1", "N/D")
    m30 = analysis.get("M30", "N/D")
    fvg = analysis.get("FVG", "Aucun")
    bull = analysis.get("bullish_score", 0)
    bear = analysis.get("bearish_score", 0)
    zones = analysis.get("Zones_FVG_actives", "Aucune")
    rejection = analysis.get("Rejet_M30", "Aucun")

    if decision == "ACHAT POTENTIEL":
        if price_vs_200 != "Au-dessus":
            verdict = "BIAIS HAUSSIER — ATTENDRE"
            confirmation = (
                "Le prix n'est pas au-dessus de l'EMA 200 H4. "
                "Attendre une reprise confirmée au-dessus de cette moyenne."
            )
        elif setup == "ACHAT À VALIDER":
            verdict = "CONFIGURATION D'ACHAT — VALIDATION MANUELLE"
            confirmation = (
                "Un FVG haussier actif a été retesté et la dernière bougie M30 "
                "montre un rejet haussier. Vérifier le contexte, le stop-loss "
                "et le ratio risque/rendement avant toute décision."
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
        if price_vs_200 != "En dessous":
            verdict = "BIAIS BAISSIER — ATTENDRE"
            confirmation = (
                "Le prix n'est pas sous l'EMA 200 H4. "
                "Attendre une faiblesse confirmée sous cette moyenne."
            )
        elif setup == "VENTE À VALIDER":
            verdict = "CONFIGURATION DE VENTE — VALIDATION MANUELLE"
            confirmation = (
                "Un FVG baissier actif a été retesté et la dernière bougie M30 "
                "montre un rejet baissier. Vérifier le contexte, le stop-loss "
                "et le ratio risque/rendement avant toute décision."
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
            f"H4 : {h4} | H1 : {h1} | M30 : {m30}. FVG : {fvg}."
        ),
        "setup": setup,
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
        if analysis.get("Prix_vs_EMA200") != "Au-dessus":
            return
    elif setup == "VENTE À VALIDER":
        direction = "VENTE"
        voice = VOICE_STRONG_BEAR
        emoji = "🔴"
        if analysis.get("Prix_vs_EMA200") != "En dessous":
            return
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
        f"Entrée théorique (milieu FVG) : {entry}",
        f"Stop Loss indicatif : {stop}",
        f"Take Profit indicatif : {target}",
        f"Ratio risque/rendement : 1:{rr_value:.2f}",
        f"Zone FVG : {analysis.get('Plan_fvg_zone', 'N/D')}",
        f"Confirmation : rejet M30 détecté",
        f"Bougie M30 : {candle_time}",
        "",
        "Signal informatif seulement : vérifier le graphique et les niveaux "
        "avant toute décision. Aucun ordre n'a été envoyé."
    ]
    email_body = "\\n".join(message_lines)

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
            "Configuration": a["Setup_M30"],
            "R/R": f'1:{a["Plan_rr"]:.2f}' if a["Plan_rr"] is not None else "—"
        })
    if summary_rows:
        st.dataframe(
            pd.DataFrame(summary_rows),
            use_container_width=True,
            hide_index=True
        )
        st.caption("Une alerte exige une structure récente, un retest et un rejet dans le FVG retenu.")



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
                    f"Zone FVG utilisée : {assistant['plan_fvg_zone']} | "
                    f"Cible : {assistant['target_method']} | "
                    f"{assistant['plan_status']}"
                )
            else:
                st.info(assistant["plan_status"])

            with st.expander("Détails et raisons d'attendre"):
                st.write(f"**H4 :** {assistant_analysis['H4']} | **H1 :** {assistant_analysis['H1']} | **M30 :** {assistant_analysis['M30']}")
                st.write(f"**Setup :** {assistant['setup']}")
                st.write(f"**Rejet M30 :** {assistant['rejection']}")
                st.write(f"**FVG retenu :** {assistant['plan_fvg_zone']}")
                st.write(f"**Cible :** {assistant['target_method']}")
                st.write(f"**Zones FVG actives :** {assistant['zones']}")
                st.write(f"**Confirmation :** {assistant['confirmation']}")
                st.write(f"**Invalidation :** {assistant['invalidation']}")
                for reason in assistant_analysis.get("Raisons_blocage_alerte", []):
                    st.write(f"• {reason}")
            st.caption("Aucun ordre n'est envoyé automatiquement. Les niveaux restent indicatifs.")

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
