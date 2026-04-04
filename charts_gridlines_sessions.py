import matplotlib
matplotlib.use('Agg')

import os
import time
import requests
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

# -------- CONFIG --------
BINANCE_REST = 'https://data-api.binance.vision'
INTERVAL = '30m'
CANDLES_LIMIT = 150
OUTPUT_DIR = 'images'
SLEEP_BETWEEN_CALLS = 0.35
SYMBOLS = ['BTCUSDT', 'ETHUSDT']
SESSION_TIME = '00:00'
# ------------------------

os.makedirs(OUTPUT_DIR, exist_ok=True)

session = requests.Session()


# ---------- TELEGRAM ----------
def send_telegram_photo(file_path, caption=""):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    with open(file_path, "rb") as f:
        r = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": f}
        )

    print("Telegram status:", r.status_code)


# ---------- DATA ----------
def fetch_klines(symbol):
    url = BINANCE_REST + '/api/v3/klines'
    params = {'symbol': symbol, 'interval': INTERVAL, 'limit': CANDLES_LIMIT}

    r = session.get(url, params=params, timeout=20)
    r.raise_for_status()

    df = pd.DataFrame(r.json(), columns=[
        'open_time','open','high','low','close','volume',
        'close_time','qav','trades','tbav','tqav','ignore'
    ])

    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')

    for col in ['open','high','low','close','volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df.set_index('open_time', inplace=True)
    return df[['open','high','low','close','volume']]


# ---------- LOGIC ----------
def get_session_extremes(df):
    df['date'] = df.index.floor('1D')

    if df['date'].nunique() < 2:
        return None

    prev_date = df['date'].unique()[-2]
    session_data = df[df['date'] == prev_date]

    return {
        'high': session_data['high'].max(),
        'low': session_data['low'].min()
    }


def check_setup(df, sh, sl):
    last = df.iloc[-1]

    if last['close'] > sh:
        return 'bullish_break'

    if last['close'] < sl:
        return 'bearish_break'

    return None


# ---------- CHART ----------
def save_chart(df, symbol, direction, sh, sl):
    timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M')
    filename = f"{symbol}_{direction}_{timestamp}.png"
    path = os.path.join(OUTPUT_DIR, filename)

    mc = mpf.make_marketcolors(up='g', down='r')
    style = mpf.make_mpf_style(marketcolors=mc)

    fig, axes = mpf.plot(
        df,
        type='candle',
        style=style,
        volume=True,
        returnfig=True
    )

    ax = axes[0]

    # PDH / PDL lines
    ax.axhline(sh, linestyle='dotted', color='orange')
    ax.axhline(sl, linestyle='dotted', color='green')

    fig.savefig(path)
    plt.close(fig)

    return path


# ---------- MAIN ----------
def run_scan():
    print('\n=== NEW SCAN STARTED ===')

    for symbol in SYMBOLS:
        try:
            df = fetch_klines(symbol)

            session_data = get_session_extremes(df)
            if not session_data:
                print(f'[skip] {symbol} no session data')
                continue

            sh = session_data['high']
            sl = session_data['low']

            direction = check_setup(df, sh, sl)

            if not direction:
                print(f'[skip] {symbol} no setup')
                continue

            path = save_chart(df, symbol, direction, sh, sl)

            print(f'[ok] {symbol} -> {path}')

            send_telegram_photo(
                path,
                caption=f"{symbol} {direction} (30m)"
            )

        except Exception as e:
            print(f'[error] {symbol}: {e}')

        time.sleep(SLEEP_BETWEEN_CALLS)


def main():
    run_scan()


if __name__ == '__main__':
    main()
