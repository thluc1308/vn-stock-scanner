"""
VN Stock MA/VA Scanner - Data Fetcher
CHỈ HOSE + Xử lý song song để nhanh hơn

Yêu cầu: pip install vnstock3 pandas numpy
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import pandas as pd
import numpy as np

try:
    from vnstock3 import Vnstock
except ImportError:
    try:
        from vnstock import Vnstock
    except ImportError:
        print("Cài đặt vnstock: pip install vnstock3")
        exit(1)


# ============== CẤU HÌNH ==============
OUTPUT_DIR = Path("data")
DAILY_DIR = OUTPUT_DIR / "daily"
YEARS_HISTORY = 2
ADMF_LENGTH = 14
MAX_WORKERS = 5  # Số luồng song song
EXCHANGES = ['HOSE']  # Chỉ HOSE trước, thêm 'HNX', 'UPCOM' sau nếu cần

# Thread-safe counter
lock = threading.Lock()
progress = {'success': 0, 'failed': 0, 'total': 0}


def rma(series, length):
    """RMA (Relative Moving Average) - Wilder's Smoothing"""
    alpha = 1.0 / length
    return series.ewm(alpha=alpha, adjust=False).mean()


def get_all_symbols():
    """Lấy danh sách mã chứng khoán theo sàn"""
    all_stocks = []
    
    try:
        stock = Vnstock().stock(symbol='VNM', source='VCI')
        
        for exchange in EXCHANGES:
            try:
                # Thử nhiều cách lấy symbols
                symbols = None
                
                # Cách 1: symbols_by_group
                try:
                    symbols = stock.listing.symbols_by_group(exchange)
                except:
                    pass
                
                # Cách 2: all_symbols rồi filter
                if symbols is None or len(symbols) == 0:
                    try:
                        all_syms = stock.listing.all_symbols()
                        if isinstance(all_syms, pd.DataFrame):
                            # Filter theo exchange
                            if 'exchange' in all_syms.columns:
                                symbols = all_syms[all_syms['exchange'] == exchange]
                            elif 'comGroupCode' in all_syms.columns:
                                symbols = all_syms[all_syms['comGroupCode'] == exchange]
                            else:
                                symbols = all_syms
                    except:
                        pass
                
                if symbols is not None:
                    if isinstance(symbols, pd.DataFrame):
                        for _, row in symbols.iterrows():
                            sym = None
                            for col in ['symbol', 'ticker', 'code']:
                                if col in row.index and pd.notna(row[col]):
                                    sym = str(row[col]).upper()
                                    break
                            if sym is None and len(row) > 0:
                                sym = str(row.iloc[0]).upper()
                            if sym and len(sym) <= 5 and sym.isalpha():
                                all_stocks.append({'symbol': sym, 'exchange': exchange})
                    elif isinstance(symbols, list):
                        for sym in symbols:
                            sym = str(sym).upper()
                            if len(sym) <= 5 and sym.isalpha():
                                all_stocks.append({'symbol': sym, 'exchange': exchange})
                
                print(f"  ✓ {exchange}: {len([s for s in all_stocks if s['exchange']==exchange])} mã")
                
            except Exception as e:
                print(f"  ⚠ {exchange}: {e}")
        
    except Exception as e:
        print(f"Lỗi: {e}")
    
    # Loại bỏ trùng
    seen = set()
    unique = []
    for s in all_stocks:
        if s['symbol'] not in seen:
            seen.add(s['symbol'])
            unique.append(s)
    
    return unique


def fetch_stock_data(symbol, start_date, end_date):
    """Fetch dữ liệu lịch sử của 1 mã"""
    try:
        stock = Vnstock().stock(symbol=symbol, source='VCI')
        df = stock.quote.history(start=start_date, end=end_date)
        
        if df is None or len(df) == 0:
            return None
        
        # Chuẩn hóa tên cột
        col_map = {
            'time': 'date', 'open': 'o', 'high': 'h', 
            'low': 'l', 'close': 'c', 'volume': 'v'
        }
        df = df.rename(columns=col_map)
        
        # Đảm bảo có cột date
        if 'date' not in df.columns:
            for col in df.columns:
                if 'time' in col.lower() or 'date' in col.lower():
                    df['date'] = df[col]
                    break
        
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        
        # Tính MA
        df['ma5'] = df['c'].rolling(5).mean()
        df['ma20'] = df['c'].rolling(20).mean()
        df['ma60'] = df['c'].rolling(60).mean()
        
        # Tính VA
        df['va5'] = df['v'].rolling(5).mean()
        df['va20'] = df['v'].rolling(20).mean()
        df['va60'] = df['v'].rolling(60).mean()
        
        # Tính ADMF
        tr = pd.concat([
            df['h'] - df['l'],
            abs(df['h'] - df['c'].shift(1)),
            abs(df['l'] - df['c'].shift(1))
        ], axis=1).max(axis=1)
        
        ad_ratio = df['c'].diff() / tr.replace(0, np.nan)
        ad_ratio = ad_ratio.fillna(0)
        
        hlc3 = (df['h'] + df['l'] + df['c']) / 3
        df['admf'] = rma(df['v'] * hlc3 * ad_ratio, ADMF_LENGTH)
        
        return df
        
    except Exception as e:
        return None


def calculate_convergence(ma5, ma20, ma60):
    """Tính độ hội tụ MA"""
    def pct_diff(a, b):
        if a == 0 and b == 0:
            return 0
        avg = (a + b) / 2
        return abs(a - b) / avg * 100 if avg != 0 else 0
    
    ma5_20 = pct_diff(ma5, ma20)
    ma20_60 = pct_diff(ma20, ma60)
    ma5_60 = pct_diff(ma5, ma60)
    ma_converge = (ma5_20 + ma20_60 + ma5_60) / 3
    
    return {
        'ma5_20': round(ma5_20, 2),
        'ma20_60': round(ma20_60, 2),
        'ma5_60': round(ma5_60, 2),
        'maConverge': round(ma_converge, 2)
    }


def calculate_admf_stats(admf_series, period_days):
    """Tính thống kê ADMF"""
    recent = admf_series.tail(period_days).dropna()
    
    if len(recent) < period_days * 0.5:
        return None
    
    max_abs = recent.abs().max()
    if max_abs == 0:
        return None
    
    normalized = recent / max_abs
    signs = np.sign(recent)
    zero_crosses = int((signs.diff().abs() > 0).sum())
    avg_distance = round(normalized.abs().mean() * 100, 2)
    max_distance = round(normalized.abs().max() * 100, 2)
    pct_near_zero = round((normalized.abs() < 0.2).sum() / len(normalized) * 100, 1)
    
    return {
        'zero_cross_count': zero_crosses,
        'avg_distance': avg_distance,
        'max_distance': max_distance,
        'pct_near_zero': pct_near_zero
    }


def process_stock(symbol_info, start_date, end_date):
    """Xử lý 1 mã chứng khoán"""
    symbol = symbol_info['symbol']
    exchange = symbol_info['exchange']
    
    df = fetch_stock_data(symbol, start_date, end_date)
    
    if df is None or len(df) < 60:
        return None
    
    latest = df.iloc[-1]
    
    ma5 = float(latest.get('ma5', 0) or 0)
    ma20 = float(latest.get('ma20', 0) or 0)
    ma60 = float(latest.get('ma60', 0) or 0)
    va5 = float(latest.get('va5', 0) or 0)
    va20 = float(latest.get('va20', 0) or 0)
    va60 = float(latest.get('va60', 0) or 0)
    
    convergence = calculate_convergence(ma5, ma20, ma60)
    
    def va_diff(a, b):
        if a == 0 and b == 0:
            return 0
        avg = (a + b) / 2
        return abs(a - b) / avg * 100 if avg != 0 else 0
    
    va_converge = (va_diff(va5, va20) + va_diff(va20, va60)) / 2
    
    snapshot = {
        "symbol": symbol,
        "exchange": exchange,
        "price": round(float(latest['c']), 2),
        "volume": int(latest['v']),
        "ma5": round(ma5, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        **convergence,
        "vaConverge": round(va_converge, 2),
        "admf": round(float(latest.get('admf', 0) or 0), 0),
        "admf_1m": calculate_admf_stats(df['admf'], 22),
        "admf_2m": calculate_admf_stats(df['admf'], 44),
        "admf_3m": calculate_admf_stats(df['admf'], 66),
        "admf_4m": calculate_admf_stats(df['admf'], 88),
    }
    
    # Daily data
    daily = {
        "symbol": symbol,
        "exchange": exchange,
        "updated": end_date,
        "columns": ["date", "o", "h", "l", "c", "v", "ma5", "ma20", "ma60", "va5", "va20", "va60", "admf"],
        "data": []
    }
    
    for _, row in df.iterrows():
        daily["data"].append([
            row.get('date', ''),
            round(float(row['o']), 2) if pd.notna(row.get('o')) else None,
            round(float(row['h']), 2) if pd.notna(row.get('h')) else None,
            round(float(row['l']), 2) if pd.notna(row.get('l')) else None,
            round(float(row['c']), 2) if pd.notna(row.get('c')) else None,
            int(row['v']) if pd.notna(row.get('v')) else None,
            round(float(row['ma5']), 2) if pd.notna(row.get('ma5')) else None,
            round(float(row['ma20']), 2) if pd.notna(row.get('ma20')) else None,
            round(float(row['ma60']), 2) if pd.notna(row.get('ma60')) else None,
            int(row['va5']) if pd.notna(row.get('va5')) else None,
            int(row['va20']) if pd.notna(row.get('va20')) else None,
            int(row['va60']) if pd.notna(row.get('va60')) else None,
            round(float(row['admf']), 0) if pd.notna(row.get('admf')) else None,
        ])
    
    return {"snapshot": snapshot, "daily": daily}


def process_single_stock(args):
    """Wrapper để xử lý song song"""
    stock, start_date, end_date, idx, total = args
    symbol = stock['symbol']
    
    try:
        result = process_stock(stock, start_date, end_date)
        
        with lock:
            if result:
                progress['success'] += 1
                print(f"   ✓ [{progress['success']+progress['failed']}/{total}] {symbol}")
            else:
                progress['failed'] += 1
        
        return result
        
    except Exception as e:
        with lock:
            progress['failed'] += 1
        return None


def main():
    print("=" * 60)
    print("VN STOCK MA/VA SCANNER - DATA FETCHER")
    print(f"Sàn: {', '.join(EXCHANGES)} | Song song: {MAX_WORKERS} luồng")
    print("=" * 60)
    
    # Tạo thư mục
    OUTPUT_DIR.mkdir(exist_ok=True)
    DAILY_DIR.mkdir(exist_ok=True)
    
    # Khoảng thời gian
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365 * YEARS_HISTORY)).strftime('%Y-%m-%d')
    print(f"\n📅 Khoảng thời gian: {start_date} → {end_date}")
    
    # Lấy danh sách mã
    print("\n📋 Đang lấy danh sách mã chứng khoán...")
    all_stocks = get_all_symbols()
    
    if not all_stocks:
        print("❌ Không lấy được danh sách mã. Thoát.")
        exit(1)
    
    total = len(all_stocks)
    print(f"\n   Tổng cộng: {total} mã")
    
    # Xử lý song song
    print(f"\n🔄 Đang fetch dữ liệu ({MAX_WORKERS} luồng song song)...")
    
    snapshots = []
    args_list = [(stock, start_date, end_date, i, total) for i, stock in enumerate(all_stocks)]
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_single_stock, args): args[0]['symbol'] for args in args_list}
        
        for future in as_completed(futures):
            result = future.result()
            if result:
                snapshots.append(result['snapshot'])
                
                # Lưu daily data
                symbol = result['snapshot']['symbol']
                daily_file = DAILY_DIR / f"{symbol}.json"
                with open(daily_file, 'w', encoding='utf-8') as f:
                    json.dump(result['daily'], f)
    
    # Lưu snapshot
    snapshot_data = {
        "updated": end_date,
        "generated": datetime.now().isoformat(),
        "totalStocks": len(snapshots),
        "stocks": sorted(snapshots, key=lambda x: x['symbol'])
    }
    
    with open(OUTPUT_DIR / "snapshot.json", 'w', encoding='utf-8') as f:
        json.dump(snapshot_data, f, ensure_ascii=False)
    
    print("\n" + "=" * 60)
    print(f"✅ HOÀN TẤT!")
    print(f"   - Thành công: {progress['success']} mã")
    print(f"   - Thất bại: {progress['failed']} mã")
    print(f"   - File: {OUTPUT_DIR}/snapshot.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
