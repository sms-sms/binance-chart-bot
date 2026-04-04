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
SCAN_INTERVAL_SECONDS = 1800  # 30 minutes
SYMBOLS = ['BTCUSDT', 'ETHUSDT']
SESSION_TIME = '00:00'  # Sri Lanka session time
# ------------------------

os.makedirs(OUTPUT_DIR, exist_ok=True)

session = requests.Session()
session.headers.update({'User-Agent': 'binance-candles-to-png/1.0'})


def fetch_klines(symbol, interval=INTERVAL, limit=CANDLES_LIMIT):
    url = BINANCE_REST + '/api/v3/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    r = session.get(url, params=params, timeout=20)
    r.raise_for_status()
    klines = r.json()

    if not isinstance(klines, list) or len(klines) < limit:
        return None

    df = pd.DataFrame(klines, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'num_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])

    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')

    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df.set_index('open_time', inplace=True)
    df = df[['open', 'high', 'low', 'close', 'volume']]

    return df


# ✅ Session line function (05:30 only)
def get_session_lines(df):
    session_lines = []

    for ts in df.index:
        if ts.strftime('%H:%M') == SESSION_TIME:
            session_lines.append(ts)

    return session_lines


def save_candlestick_image(df, symbol):
    # ✅ timestamp to avoid overwrite
    timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M')
    filename = f"{symbol}_{INTERVAL}_{timestamp}.png"
    outpath = os.path.join(OUTPUT_DIR, filename)

    mc = mpf.make_marketcolors(
        up='g',
        down='r',
        edge='i',
        wick='i',
        volume={'up': 'g', 'down': 'r'}
    )

    style = mpf.make_mpf_style(
        marketcolors=mc,
        gridstyle=':',
        gridcolor='gray',
        rc={
            'axes.grid': True,
            'grid.alpha': 0.4,
            'grid.linewidth': 0.5
        }
    )

    # ✅ Get session vertical lines
    session_lines = get_session_lines(df)

    vlines = dict(
        vlines=session_lines,
        colors='blue',
        linestyle='dashed',
        linewidths=0.7,
        alpha=0.6
    )

    fig, axes = mpf.plot(
        df,
        type='candle',
        style=style,
        volume=True,
        figsize=(8, 6),
        panel_ratios=(4, 1),
        returnfig=True,
        vlines=vlines
    )

    ax = axes[0]
    vax = axes[2]

    # Grid density
    ax.xaxis.set_major_locator(MaxNLocator(10))
    ax.yaxis.set_major_locator(MaxNLocator(10))

    # Remove labels + ticks
    ax.set_xticklabels([])
    ax.set_yticklabels([])
    vax.set_xticklabels([])
    vax.set_yticklabels([])

    ax.tick_params(length=0)
    vax.tick_params(length=0)

    fig.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return outpath


def run_scan():
    print('\n=== NEW SCAN STARTED ===')

    processed = 0
    skipped = []

    for symbol in SYMBOLS:
        try:
            df = fetch_klines(symbol)
        except Exception as e:
            print(f'[skip] {symbol} API error: {e}')
            skipped.append(symbol)
            time.sleep(SLEEP_BETWEEN_CALLS)
            continue

        if df is None:
            print(f'[skip] {symbol} insufficient candles')
            skipped.append(symbol)
            time.sleep(SLEEP_BETWEEN_CALLS)
            continue

        try:
            outpath = save_candlestick_image(df, symbol)
            print(f'[ok] {symbol} -> {outpath}')
            processed += 1
        except Exception as e:
            print(f'[skip] {symbol} plot error: {e}')
            skipped.append(symbol)

        time.sleep(SLEEP_BETWEEN_CALLS)

    print('\nScan complete')
    print('Saved:', processed)
    print('Skipped:', len(skipped))


#def main():
    #while True:
        #run_scan()
        #print(f'\nSleeping for {SCAN_INTERVAL_SECONDS / 60} minutes...')
        #time.sleep(SCAN_INTERVAL_SECONDS)

def main():
    run_scan()


if __name__ == '__main__':
    main()
