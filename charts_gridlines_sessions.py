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
SCAN_INTERVAL_SECONDS = 1800
SYMBOLS = ['BTCUSDT', 'ETHUSDT']
SESSION_TIME = '00:00'  # NEW session
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
    return df[['open', 'high', 'low', 'close', 'volume']]


# Session vertical line (00:00)
def get_session_lines(df):
    return [ts for ts in df.index if ts.strftime('%H:%M') == SESSION_TIME]


# ✅ Previous day/session high/low WITHOUT shifting
def get_session_extremes_with_index(df):
    df_copy = df.copy()

    df_copy['date'] = df_copy.index.floor('1D')

    if df_copy['date'].nunique() < 2:
        return None

    prev_date = df_copy['date'].unique()[-2]
    session_data = df_copy[df_copy['date'] == prev_date]

    high_idx = session_data['high'].idxmax()
    low_idx = session_data['low'].idxmin()

    return {
        'high': float(session_data.loc[high_idx, 'high']),
        'low': float(session_data.loc[low_idx, 'low']),
        'high_idx': high_idx,
        'low_idx': low_idx
    }


def check_break_condition(df, sh, sl, lookback=5, shift=7):
    if sh is None or sl is None:
        return False, None, None, None

    if len(df) < (lookback + 2 + shift):
        return False, None, None, None

    last_idx = -2 - shift
    last = df.iloc[last_idx]
    last_close = last['close']

    recent = df.iloc[-(lookback + 2 + shift):-(2 + shift)]

    # -------- BEARISH SWEEP --------
    if (recent['close'] > sh).any() and last_close < sh:
      q_idx = df.index[last_idx]

      df_before_q = df.loc[:q_idx]

      p_candidates = df_before_q[df_before_q['close'] > sh]

      if p_candidates.empty:
         return False, None, None, None

      p_idx = p_candidates.index[-1]

      return True, 'bearish_sweep', p_idx, q_idx


    # -------- BULLISH SWEEP --------
    if (recent['close'] < sl).any() and last_close > sl:
     q_idx = df.index[last_idx]

      # find p ONLY before q
     df_before_q = df.loc[:q_idx]

     p_candidates = df_before_q[df_before_q['close'] < sl]

     if p_candidates.empty:
       return False, None, None, None

     p_idx = p_candidates.index[-1]

     return True, 'bullish_sweep', p_idx, q_idx

    return False, None, None, None

def build_trade_message(df, symbol, direction, p_idx, q_idx, sh, sl):
    segment = df.loc[p_idx:q_idx]

    q_close = df.loc[q_idx, 'close']

    if direction == 'bearish_sweep':
        x = segment['high'].max()

        entry_low = q_close
        entry_high = sh

        risk = x - q_close

        trade_a = (10 * q_close) / risk
        trade_b = (2.5 * q_close) / risk

        sl_price = x + (0.0005 * x)
        tp = q_close - (2 * (sl_price - q_close))

        msg = f"""
Pair: {symbol}
Trade: Short (Sell)
Entry price: between {entry_low:.4f} and {entry_high:.4f}

Trade size:
  Trade A: {trade_a:.4f}
  Trade B: {trade_b:.4f}

SL: {sl_price:.4f}
TP: {tp:.4f}
"""

    elif direction == 'bullish_sweep':
        x = segment['low'].min()

        entry_low = sl
        entry_high = q_close

        risk = q_close - x

        trade_a = (10 * q_close) / risk
        trade_b = (2.5 * q_close) / risk

        sl_price = x - (0.0005 * x)
        tp = q_close + (2 * (q_close - sl_price))

        msg = f"""
Pair: {symbol}
Trade: Long (Buy)
Entry price: between {entry_low:.4f} and {entry_high:.4f}

Trade size:
  Trade A: {trade_a:.4f}
  Trade B: {trade_b:.4f}

SL: {sl_price:.4f}
TP: {tp:.4f}
"""

    else:
        return None

    return msg


def save_candlestick_image(df, symbol):
    session_data = get_session_extremes_with_index(df)

    if session_data is None:
        return None

    sh = session_data['high']
    sl = session_data['low']

    valid, direction, p_idx, q_idx = check_break_condition(df, sh, sl)

    if not valid:
        return None

    trade_message = build_trade_message(df, symbol, direction, p_idx, q_idx, sh, sl)
    timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M')
    filename = f"{symbol}_{direction}_{timestamp}.png"
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

    fig.suptitle(f"{symbol} ({INTERVAL})", fontsize=12)
    
    ax = axes[0]
    vax = axes[2]

    # Horizontal lines (index-based)
    high_pos = df.index.get_loc(session_data['high_idx'])
    start_high = max(0, high_pos - 3)

    ax.hlines(
        y=sh,
        xmin=start_high,
        xmax=len(df) - 1,
        colors='orange',
        linestyles='dotted',
        linewidth=1
    )

    low_pos = df.index.get_loc(session_data['low_idx'])
    start_low = max(0, low_pos - 3)

    ax.hlines(
        y=sl,
        xmin=start_low,
        xmax=len(df) - 1,
        colors='green',
        linestyles='dotted',
        linewidth=1
    )

    # Formatting
    ax.xaxis.set_major_locator(MaxNLocator(10))
    ax.yaxis.set_major_locator(MaxNLocator(10))

    ax.set_xticklabels([])
    ax.set_yticklabels([])
    vax.set_xticklabels([])
    vax.set_yticklabels([])

    ax.tick_params(length=0)
    vax.tick_params(length=0)

    fig.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close(fig)

    if trade_message:
        send_telegram_message(trade_message)

    return outpath


#def main():
    #while True:
        #run_scan()
        #print(f'\nSleeping for {SCAN_INTERVAL_SECONDS / 60} minutes...')
        #time.sleep(SCAN_INTERVAL_SECONDS)
        
def send_telegram_photo(file_path):
    import os
    import requests

    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    with open(file_path, "rb") as f:
        r = requests.post(url, data={"chat_id": chat_id}, files={"photo": f})

    print("Telegram status:", r.status_code)

def send_telegram_message(text):
    import os
    import requests

    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    r = requests.post(url, data={"chat_id": chat_id, "text": text})

    print("\n--- TRADE SIGNAL ---")
    print(text)
    print("--------------------")

    print("Telegram message status:", r.status_code)

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

            if outpath:
                print(f'[ok] {symbol} -> {outpath}')
                send_telegram_photo(outpath)
                processed += 1
            else:
                print(f'[skip] {symbol} no valid setup')
                skipped.append(symbol)

        except Exception as e:
            print(f'[skip] {symbol} plot error: {e}')
            skipped.append(symbol)

        time.sleep(SLEEP_BETWEEN_CALLS)

    print('\nScan complete')
    print('Saved:', processed)
    print('Skipped:', len(skipped))

def main():
    run_scan()

if __name__ == '__main__':
    main()
