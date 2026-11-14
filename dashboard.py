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

st.set_page_config(page_title="Trading Monitor - Fibonacci Alerts", layout="wide")
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


def evaluate_fibonacci_setup(
    df,
    current_price=None,
    max_close_extension_atr=0.50,
    max_live_extension_atr=0.35
):
    """Détecte un retracement Fibonacci confirmé et écarte les entrées trop tardives.

    Le signal est refusé si la chandelle de confirmation clôture trop loin
    de la zone, ou si le prix en direct a déjà trop prolongé le mouvement.
    Les seuils sont exprimés en multiples de l'ATR14 du timeframe sélectionné.
    """
    fib, fib_message = find_last_fibonacci(df)
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
    previous = data.iloc[-2]
    live = current_price if current_price is not None else float(last["close"])

    endpoint_index = int(fib["endpoint"]["index"])
    touch_start = max(endpoint_index + 1, len(data) - 9)
    retest_candles = data.iloc[touch_start:]
    touch = any(
        float(row["low"]) <= zone_high and float(row["high"]) >= zone_low
        for _, row in retest_candles.iterrows()
    )

    if direction == "BULL":
        confirmed = (
            touch and float(last["close"]) > float(last["open"])
            and float(last["close"]) > float(previous["high"])
            and float(last["close"]) > zone_high
        )
        in_zone = zone_low <= live <= zone_high
        label = "🟢 ACHAT — REBOND FIBONACCI CONFIRMÉ"
        wait_label = "🟡 Zone d'achat Fibonacci — attente du rebond"
        zone_name = "ZONE D'ACHAT"
        details = "Swing haussier : le prix doit revenir dans la zone 50–61,8 %, puis clôturer à la hausse avec une cassure de la chandelle précédente."
    else:
        confirmed = (
            touch and float(last["close"]) < float(last["open"])
            and float(last["close"]) < float(previous["low"])
            and float(last["close"]) < zone_low
        )
        in_zone = zone_low <= live <= zone_high
        label = "🔴 VENTE — REJET FIBONACCI CONFIRMÉ"
        wait_label = "🟡 Zone de vente Fibonacci — attente du rejet"
        zone_name = "ZONE DE VENTE"
        details = "Swing baissier : le prix doit remonter dans la zone 50–61,8 %, puis clôturer à la baisse avec une cassure de la chandelle précédente."

    if confirmed:
        # Distance entre la clôture de confirmation et le bord de la zone.
        # Une extension trop grande signifie que le mouvement est déjà parti.
        close_price = float(last["close"])
        if direction == "BEAR":
            close_extension = max(0.0, zone_low - close_price)
            live_extension = max(0.0, close_price - float(live))
        else:
            close_extension = max(0.0, close_price - zone_high)
            live_extension = max(0.0, float(live) - close_price)

        atr_value = float(fib["atr"])
        close_limit = max_close_extension_atr * atr_value
        live_limit = max_live_extension_atr * atr_value

        too_late_reasons = []
        if close_extension > close_limit:
            too_late_reasons.append(
                f"La chandelle de confirmation a déjà dépassé la zone de "
                f"{close_extension:.5f} (limite {close_limit:.5f})."
            )
        if live_extension > live_limit:
            too_late_reasons.append(
                f"Depuis la clôture de confirmation, le prix a prolongé le "
                f"mouvement de {live_extension:.5f} (limite {live_limit:.5f})."
            )

        if too_late_reasons:
            return {
                "state": direction + "_TOO_LATE",
                "label": (
                    "⚠️ VENTE — REJET CONFIRMÉ, ENTRÉE TROP TARDIVE"
                    if direction == "BEAR"
                    else "⚠️ ACHAT — REBOND CONFIRMÉ, ENTRÉE TROP TARDIVE"
                ),
                "color": "orange",
                "details": "Le signal technique est apparu, mais le prix est "
                           "déjà trop éloigné pour proposer une entrée prudente. "
                           + " ".join(too_late_reasons)
                           + " Attendre un nouveau retracement; ne pas poursuivre le prix.",
                "fib": fib, "zone_name": zone_name, "touch": touch,
                "in_zone": in_zone, "close_extension": close_extension,
                "live_extension": live_extension,
                "close_extension_limit": close_limit,
                "live_extension_limit": live_limit
            }

        return {
            "state": direction + "_CONFIRMED", "label": label,
            "color": "green" if direction == "BULL" else "red",
            "details": details + " Filtre anti-retard validé : le prix reste "
                       "suffisamment proche de la zone pour étudier une entrée.",
            "fib": fib, "zone_name": zone_name,
            "touch": touch, "in_zone": in_zone,
            "close_extension": close_extension,
            "live_extension": live_extension,
            "close_extension_limit": close_limit,
            "live_extension_limit": live_limit
        }

    if in_zone or touch:
        extra = "Le prix actuel est dans la zone. " if in_zone else "La zone a été visitée récemment; la confirmation manque encore. "
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
def process_fibonacci_alert(pair, timeframe, setup, candle_time):
    state_key = f"fib_alert_state_{pair}_{timeframe}"
    previous_state = st.session_state.get(state_key, "INIT")
    st.session_state[state_key] = setup["state"]

    is_new_signal = setup["state"] in ("BULL_CONFIRMED", "BEAR_CONFIRMED") and setup["state"] != previous_state
    if not is_new_signal:
        return

    bullish = setup["state"] == "BULL_CONFIRMED"
    subject = f"{'🟢 Signal ACHAT' if bullish else '🔴 Signal VENTE'} Fibonacci — {pair} {timeframe}"
    fib = setup["fib"]
    body = (
        f"Configuration Fibonacci confirmée sur {pair} en {timeframe}.\n"
        f"Direction : {'haussière' if bullish else 'baissière'}.\n"
        f"Zone 50–61,8 % : {fib['zone_low']:.5f} à {fib['zone_high']:.5f}.\n"
        f"Dernière chandelle clôturée : {candle_time}.\n\n"
        "Signal de configuration à valider manuellement; aucun ordre automatique."
    )
    voice_url = VOICE_STRONG_BULL if bullish else VOICE_STRONG_BEAR

    st.session_state.setdefault("fib_new_alerts", [])
    st.session_state["fib_new_alerts"].append({
        "Heure": datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d %H:%M:%S"),
        "Instrument": pair, "Timeframe": timeframe, "Signal": subject
    })
    if not mute_alerts:
        play_voice_alert(voice_url)
    if email_alerts_enabled:
        sent, status = send_email_alert(subject, body)
        if not sent and "non configurés" not in status:
            st.warning(status)


# MAIN DASHBOARD
st.title("Trading Monitor — Fibonacci Setup Alerts")
st.caption(
    "Alertes basées sur le dernier swing confirmé, le retracement Fibonacci "
    "50–61,8 %, une chandelle de confirmation et un filtre anti-entrée tardive "
    "(extension maximale de 0,50 ATR à la clôture et 0,35 ATR en direct)."
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
        # Utilise la dernière chandelle reçue (potentiellement en formation) comme prix courant.
        # Cela évite une requête M1 OANDA supplémentaire pour chaque instrument.
        current_price = float(raw_df.iloc[-1]["close"])
        setup = evaluate_fibonacci_setup(df, current_price)
        last = df.iloc[-1]
        candle_time = last["time"].strftime("%Y-%m-%d %H:%M NY")

        process_fibonacci_alert(pair, timeframe, setup, candle_time)

        if current_price is not None:
            st.write(f"💵 Prix actuel OANDA : **{current_price:.5f}**")

        st.markdown(
            f"<h4 style='color:{setup['color']};'>{setup['label']}</h4>",
            unsafe_allow_html=True
        )
        st.write(setup["details"])
        st.caption(f"Signal calculé sur la dernière chandelle clôturée : {candle_time}")

        col1, col2 = st.columns(2)
        col1.metric("ADX14", "N/D" if pd.isna(last["ADX14"]) else f"{last['ADX14']:.1f}")
        col2.metric("Fibonacci", "Valide" if setup.get("fib") else "En attente")
        if setup.get("fib"):
            fib = setup["fib"]
            zone_name = setup.get("zone_name", "ZONE DE RETRACEMENT")
            st.write(f"**{zone_name} Fibonacci 50–61,8 % :** {fib['zone_low']:.5f} – {fib['zone_high']:.5f}")
            st.write(f"**Origine du swing :** {fib['origin']['price']:.5f}  |  **Extrémité :** {fib['endpoint']['price']:.5f}")

        st.markdown("#### Plan de trade Fibonacci")
        trade_plan, trade_message = build_trade_plan(setup, current_price)
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
        fig.add_trace(
            go.Scatter(x=df["time"], y=df["close"], name="Close",
                       line=dict(color="gray", dash="dot")), row=1, col=1
        )
        if show_emas:
            for ema_name, ema_color, ema_dash in [
                ("EMA50", "blue", "solid"),
                ("EMA100", "gray", "dash"),
                ("EMA200", "orange", "solid")
            ]:
                fig.add_trace(
                    go.Scatter(x=df["time"], y=df[ema_name], name=ema_name,
                               line=dict(color=ema_color, dash=ema_dash, width=2)), row=1, col=1
                )
        if setup.get("fib"):
            fib = setup["fib"]
            x0 = fib["origin"]["time"]
            x1 = df["time"].iloc[-1]
            fib_styles = {
                0.382: ("#00C8FF", "dash", 2),
                0.5: ("#FFD000", "solid", 3),
                0.618: ("#FF4B4B", "solid", 3),
                0.786: ("#F2F2F2", "longdashdot", 2),
            }
            for ratio, level in fib["levels"].items():
                fib_color, fib_dash, fib_width = fib_styles[ratio]
                fig.add_trace(go.Scatter(
                    x=[x0, x1], y=[level, level], mode="lines",
                    name=("Fib 78,6 % — niveau secondaire" if ratio == 0.786 else f"Fib {ratio * 100:.1f}%"),
                    line=dict(color=fib_color, width=fib_width, dash=fib_dash)
                ), row=1, col=1)

            if fib["direction"] == "BEAR":
                zone_fill, zone_border = "rgba(220, 35, 55, 0.30)", "#FF5268"
                zone_label = "ZONE DE VENTE 50–61,8 %"
            else:
                zone_fill, zone_border = "rgba(0, 170, 105, 0.30)", "#00D68F"
                zone_label = "ZONE D'ACHAT 50–61,8 %"

            fig.add_hrect(
                y0=fib["zone_low"], y1=fib["zone_high"],
                fillcolor=zone_fill, line_color=zone_border, line_width=2,
                annotation_text=zone_label, annotation_position="top left",
                annotation_font=dict(color=zone_border, size=13),
                row=1, col=1
            )
        fig.add_trace(
            go.Bar(
                x=df["time"], y=df["volume"], name="Volume",
                marker_color="rgba(150,150,150,0.6)"
            ), row=2, col=1
        )
        fig.update_layout(
            height=700, template="plotly_dark",
            margin=dict(l=20, r=20, t=55, b=20),
            legend=dict(orientation="h", y=1.08, x=0),
            hovermode="x unified"
        )
        st.plotly_chart(fig, width="stretch")

    except Exception as exc:
        st.error(f"Erreur pour {pair} ({timeframe}) : {exc}")


# RECENT ALERTS
st.markdown("---")
st.subheader("🔔 Alertes Fibonacci récentes")
recent_alerts = st.session_state.get("fib_new_alerts", [])
if recent_alerts:
    st.dataframe(pd.DataFrame(recent_alerts[::-1]), width="stretch", hide_index=True)
else:
    st.info("Aucune nouvelle alerte Fibonacci depuis l'ouverture du dashboard.")


# PROFIT / LOSS LAST 7 DAYS
st.markdown("---")
st.subheader("📅 Profits / Pertes (7 derniers jours)")
try:
    since = (datetime.now(pytz.UTC) - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
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
        st.dataframe(pnl_df, width="stretch", hide_index=True)
    else:
        st.info("Aucune transaction enregistrée dans les 7 derniers jours.")
except Exception as exc:
    st.error(f"Erreur OANDA dans l'historique des transactions : {exc}")

now = datetime.now(pytz.timezone("America/New_York"))
st.caption(f"🕒 Dernière mise à jour : {now.strftime('%Y-%m-%d %H:%M:%S')} NY")
