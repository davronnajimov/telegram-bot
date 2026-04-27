import telebot
from telebot import types
import requests
import io
import pandas as pd
import mplfinance as mpf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


import os

TOKEN = os.getenv("TOKEN")
bot = telebot.TeleBot(TOKEN)
user_last_binance = {}  # chat_id -> "BTCUSDT" kabi
# ------------------- GLOBAL STATE -------------------
user_state = {}        # chat_id -> "WAITING_CRYPTO" yoki None
user_last_coin = {}    # chat_id -> coin_id
user_last_name = {}    # chat_id -> ko'rinadigan nom (BTC/ETH/bitcoin...)

# ------------------- CONSTANTS -------------------
CBU_JSON_ALL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"

COINGECKO_SIMPLE = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_CHART = "https://api.coingecko.com/api/v3/coins/{id}/market_chart"

SYMBOL_TO_ID = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "TON": "the-open-network",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
}


# ------------------- MENU (START) -------------------
def send_main_menu(chat_id: int):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🪙 Kriptovalyuta", "💱 Valyutalar kursi")
    kb.row("📰 Yangiliklar kanali", "📞 Aloqa")
    kb.row("📌 Ko‘rsatmalar")

    bot.send_message(
        chat_id,
        "Botimizga xush kelibsiz 😊\nIltimos pastdan kerakli xizmatlarimizni tanlang:",
        reply_markup=kb
    )


@bot.message_handler(commands=["start"])
def start(message):
    user_state[message.chat.id] = None
    send_main_menu(message.chat.id)


@bot.message_handler(commands=["menu"])
def menu_cmd(message):
    send_main_menu(message.chat.id)


# ------------------- KO‘RSATMALAR -------------------
@bot.message_handler(func=lambda m: m.text == "📌 Ko‘rsatmalar")
def korsatmalar(message):
    bot.send_message(
        message.chat.id,
        "📌 Ko‘rsatmalar:\n"
        "1) 🪙 Kriptovalyuta — BTC, ETH, TON kabi yozsangiz narx + chart chiqadi.\n"
        "2) 💱 Valyutalar kursi — Markaziy bank kurslari chiqadi.\n"
        "3) 📰 Yangiliklar kanali — kanal havolasi.\n"
        "4) 📞 Aloqa — bog‘lanish ma’lumotlari."
    )


# ------------------- NEWS + CONTACT -------------------
@bot.message_handler(func=lambda m: m.text == "📰 Yangiliklar kanali")
def news_channel(message):
    bot.send_message(message.chat.id, "📰 Yangiliklar kanali:\nhttps://t.me/UranusNewsRu")


@bot.message_handler(func=lambda m: m.text == "📞 Aloqa")
def contact(message):
    bot.send_message(
        message.chat.id,
        "📞 Aloqa:\n"
        "Admin: @davronnajimov1\n"
        "Telefon: +998 953999074\n"
        "Email: davronnajimov1@gmail.com"
    )


# ------------------- VALYUTA KURSI (INLINE) -------------------
@bot.message_handler(func=lambda m: m.text == "💱 Valyutalar kursi")
def valyuta_kursi_menu(message):
    try:
        data = requests.get(CBU_JSON_ALL, timeout=10).json()

        kb = types.InlineKeyboardMarkup()
        for item in data:
            code = item.get("Ccy")
            name = item.get("CcyNm_UZ")
            if code and name:
                kb.add(types.InlineKeyboardButton(
                    text=f"{code} — {name}",
                    callback_data=f"CUR_{code}"
                ))

        kb.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data="CUR_BACK"))
        bot.send_message(message.chat.id, "Valyutani tanlang:", reply_markup=kb)

    except Exception:
        bot.send_message(message.chat.id, "Xatolik: valyutalar ro‘yxatini olib bo‘lmadi.")


@bot.callback_query_handler(func=lambda call: call.data == "CUR_BACK")
def currency_back(call):
    send_main_menu(call.message.chat.id)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("CUR_") and call.data != "CUR_BACK")
def currency_detail(call):
    code = call.data.replace("CUR_", "").strip()

    try:
        data = requests.get(CBU_JSON_ALL, timeout=10).json()
        item = next((x for x in data if x.get("Ccy") == code), None)

        if not item:
            bot.answer_callback_query(call.id, "Valyuta topilmadi.")
            return

        name = item.get("CcyNm_UZ")
        rate = item.get("Rate")
        date = item.get("Date")
        diff = item.get("Diff")

        text = (
            f"💱 {code} — {name}\n"
            f"📅 Sana: {date}\n"
            f"💰 Kurs: {rate} so'm\n"
            f"📈 O'zgarish: {diff}"
        )

        bot.send_message(call.message.chat.id, text)
        bot.answer_callback_query(call.id)

    except Exception:
        bot.answer_callback_query(call.id, "Xatolik yuz berdi.")


# ------------------- CRYPTO: MENU -> WAITING -------------------
@bot.message_handler(func=lambda m: m.text == "🪙 Kriptovalyuta")
def crypto_menu(message):
    user_state[message.chat.id] = "WAITING_CRYPTO"
    bot.send_message(
        message.chat.id,
        "Kriptovalyuta nomi yoki qisqa nomini yozing (BTC, ETH, TON yoki bitcoin):"
    )


# ------------------- CHART HELPERS -------------------
def get_prices_1d(coin_id: str):
    r = requests.get(
        COINGECKO_CHART.format(id=coin_id),
        params={"vs_currency": "usd", "days": 1},
        timeout=15
    ).json()
    return r.get("prices", [])


def filter_by_timeframe(prices, tf: str):
    if not prices:
        return []

    now_ms = prices[-1][0]

    if tf == "15m":
        delta = 15 * 60 * 1000
    elif tf == "1h":
        delta = 60 * 60 * 1000
    elif tf == "4h":
        delta = 4 * 60 * 60 * 1000
    else:  # "1d"
        delta = 24 * 60 * 60 * 1000

    start_ms = now_ms - delta
    return [p for p in prices if p[0] >= start_ms]


def build_tf_kb():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("15m", callback_data="TF_15m"),
        types.InlineKeyboardButton("1h", callback_data="TF_1h"),
        types.InlineKeyboardButton("4h", callback_data="TF_4h"),
        types.InlineKeyboardButton("1d", callback_data="TF_1d"),
    )
    return kb


def send_chart(chat_id: int, coin_id: str, title: str, tf: str):
    prices = get_prices_1d(coin_id)
    prices = filter_by_timeframe(prices, tf)

    if not prices:
        bot.send_message(chat_id, "Chart uchun ma'lumot topilmadi.")
        return

    x = [p[0] / 1000 for p in prices]
    y = [p[1] for p in prices]

    plt.figure()
    plt.plot(x, y)
    plt.title(f"{title} | {tf}")
    plt.xlabel("time")
    plt.ylabel("price (USD)")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=160)
    plt.close()
    buf.seek(0)

    bot.send_photo(
        chat_id,
        buf,
        caption=f"📊 {title} chart ({tf})",
        reply_markup=build_tf_kb()
    )


# ------------------- CRYPTO: PRICE + CHART -------------------
@bot.message_handler(func=lambda m: user_state.get(m.chat.id) == "WAITING_CRYPTO")
def crypto_price(message):
    raw = (message.text or "").strip()
    if not raw:
        return

    sym = raw.upper()

    if sym in SYMBOL_TO_ID:
        coin_id = SYMBOL_TO_ID[sym]
        show_name = sym
    else:
        coin_id = raw.lower().replace(" ", "-")
        show_name = raw

    try:
        r = requests.get(
            COINGECKO_SIMPLE,
            params={"ids": coin_id, "vs_currencies": "usd"},
            timeout=10
        ).json()

        usd = r.get(coin_id, {}).get("usd")
        if usd is None:
            bot.send_message(message.chat.id, "Topilmadi. Masalan: BTC, ETH, TON yoki bitcoin")
            return

        # 1) narx chiqadi
        bot.send_message(message.chat.id, f"🪙 {show_name} narxi: ${usd}")

        # 2) 5) SHU YER (narxdan KEYIN)
        if sym in SYMBOL_TO_BINANCE:
            bsym = SYMBOL_TO_BINANCE[sym]
            user_last_binance[message.chat.id] = bsym
            user_last_name[message.chat.id] = sym
            send_candle_chart(message.chat.id, bsym, sym, "1h")   # default 1h
        else:
            user_last_coin[message.chat.id] = coin_id
            user_last_name[message.chat.id] = show_name
            send_chart(message.chat.id, coin_id, show_name, "1h") # fallback line chart

        # 3) state tugaydi
        user_state[message.chat.id] = None

    except Exception:
        bot.send_message(message.chat.id, "Xatolik: narxni olib bo‘lmadi.")

# ------------------- TIMEFRAME CALLBACK -------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("TF_"))
def tf_change(call):
    tf = call.data.replace("TF_", "").strip()  # 15m / 1h / 4h / 1d
    chat_id = call.message.chat.id

    # Eski chart xabarini o‘chiramiz (inline tugmalar turgan xabar)
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except Exception:
        pass

    # Qaysi chart turini ishlatyapmiz (candlestick bo‘lsa shuni, bo‘lmasa oddiy line)
    bsym = user_last_binance.get(chat_id)
    coin_id = user_last_coin.get(chat_id)
    title = user_last_name.get(chat_id, bsym or coin_id or "CRYPTO")

    try:
        if bsym:
            send_candle_chart(chat_id, bsym, title, tf)
        elif coin_id:
            send_chart(chat_id, coin_id, title, tf)
        else:
            bot.send_message(chat_id, "Avval kriptovalyuta tanlang.")

        bot.answer_callback_query(call.id)
    except Exception:
        bot.answer_callback_query(call.id, "Xatolik yuz berdi.")

# ------------------- RUN -------------------
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"

SYMBOL_TO_BINANCE = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "BNB": "BNBUSDT",
    "SOL": "SOLUSDT",
    "XRP": "XRPUSDT",
    "TON": "TONUSDT",
}

def send_candle_chart(chat_id: int, binance_symbol: str, title: str, interval: str):
    r = requests.get(
        BINANCE_KLINES,
        params={"symbol": binance_symbol, "interval": interval, "limit": 200},
        timeout=15
    ).json()

    # r: [ [open_time, open, high, low, close, volume, close_time, ...], ... ]
    df = pd.DataFrame(r, columns=[
        "OpenTime","Open","High","Low","Close","Volume",
        "CloseTime","QAV","Trades","TBAV","TBQAV","Ignore"
    ])

    df["OpenTime"] = pd.to_datetime(df["OpenTime"], unit="ms")
    df.set_index("OpenTime", inplace=True)
    df[["Open","High","Low","Close","Volume"]] = df[["Open","High","Low","Close","Volume"]].astype(float)

    buf = io.BytesIO()
    mpf.plot(
        df,
        type="candle",
        volume=False,
        style="charles",
        title=f"{title} | {interval}",
        ylabel="Price",
        savefig=dict(fname=buf, dpi=160, bbox_inches="tight")
    )
    buf.seek(0)
    bot.send_photo(chat_id, buf, caption=f"🕯️ {title} shamcha chart ({interval})", reply_markup=build_tf_kb())
bot.infinity_polling()
