"""
VN Stock MA/VA Scanner - Data Fetcher
Fetch 2 năm dữ liệu tất cả mã chứng khoán VN
Tính MA5, MA20, MA60, VA5, VA20, VA60
Tính ADMF (Accumulation/Distribution Money Flow)
Export ra JSON để dùng cho blog/web app

Yêu cầu: pip install vnstock pandas numpy --break-system-packages
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

try:
    from vnstock import Vnstock
except ImportError:
    print("Cài đặt vnstock: pip install vnstock --break-system-packages")
    exit(1)


# ============== CẤU HÌNH ==============
OUTPUT_DIR = Path("data")
DAILY_DIR = OUTPUT_DIR / "daily"
YEARS_HISTORY = 2
SLEEP_BETWEEN_REQUESTS = 0.3  # Tránh bị rate limit
ADMF_LENGTH = 14  # Chu kỳ RMA cho ADMF

# ============== HELPER FUNCTIONS ==============

def rma(series: pd.Series, length: int) -> pd.Series:
    """
    RMA (Relative Moving Average) - Same as Wilder's Smoothing / SMMA
    RMA = (Previous RMA * (length-1) + Current Value) / length
    """
    alpha = 1.0 / length
    return series.ewm(alpha=alpha, adjust=False).mean()


def calculate_true_range(df: pd.DataFrame) -> pd.Series:
    """Tính True Range"""
    high = df['h']
    low = df['l']
    close_prev = df['c'].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close_prev)
    tr3 = abs(low - close_prev)
    
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def calculate_admf(df: pd.DataFrame, length: int = 14, price_enable: bool = True, ad_weight: float = 0.0) -> pd.Series:
    """
    Tính ADMF (Accumulation/Distribution Money Flow)
    
    Công thức từ TradingView Pine Script:
    - AD_ratio = change(close) / tr(true)
    - AD_ratio = (1-AD_weight)*AD_ratio + sign(AD_ratio)*AD_weight
    - vol = volume * hlc3 (if price_enable) else volume
    - ADMF = rma(vol * AD_ratio, length)
    
    Returns:
        Series ADMF values
    """
    # True Range
    tr = calculate_true_range(df)
    
    # AD Ratio = Change(Close) / True Range
    close_change = df['c'].diff()
    ad_ratio = close_change / tr.replace(0, np.nan)
    ad_ratio = ad_ratio.fillna(0)
    
    # Điều chỉnh AD_ratio theo weight
    ad_ratio = (1 - ad_weight) * ad_ratio + np.sign(ad_ratio) * ad_weight
    
    # Volume hoặc Money Flow
    if price_enable:
        hlc3 = (df['h'] + df['l'] + df['c']) / 3
        vol = df['v'] * hlc3
    else:
        vol = df['v']
    
    # ADMF = RMA(vol * ad_ratio, length)
    admf = rma(vol * ad_ratio, length)
    
    return admf


def calculate_admf_oscillation(admf_series: pd.Series, period_days: int) -> dict:
    """
    Tính mức độ dao động của ADMF quanh đường 0 trong khoảng thời gian
    
    Returns:
        dict với các metrics:
        - oscillation_score: điểm đánh giá (càng nhỏ càng gần 0)
        - zero_cross_count: số lần cắt đường 0
        - avg_distance: khoảng cách trung bình từ 0
        - max_distance: khoảng cách max từ 0
        - pct_near_zero: % thời gian ADMF gần 0 (trong ngưỡng ±10% của max)
    """
    recent = admf_series.tail(period_days).dropna()
    
    if len(recent) < period_days * 0.5:  # Cần ít nhất 50% dữ liệu
        return None
    
    # Normalize ADMF để so sánh giữa các mã
    max_abs = recent.abs().max()
    if max_abs == 0:
        return None
    
    normalized = recent / max_abs
    
    # Số lần cắt đường 0
    signs = np.sign(recent)
    zero_crosses = (signs.diff().abs() > 0).sum()
    
    # Khoảng cách trung bình từ 0 (normalized)
    avg_distance = normalized.abs().mean()
    
    # Khoảng cách max
    max_distance = normalized.abs().max()
    
    # % thời gian gần 0 (trong ngưỡng ±20%)
    threshold = 0.2
    near_zero = (normalized.abs() < threshold).sum() / len(normalized) * 100
    
    # Oscillation score (càng nhỏ càng tốt = càng sideway)
    # Kết hợp: avg_distance thấp + nhiều zero crosses + % gần 0 cao
    oscillation_score = avg_distance * 100 - zero_crosses * 2 - near_zero * 0.5
    
    return {
        'oscillation_score': round(oscillation_score, 2),
        'zero_cross_count': int(zero_crosses),
        'avg_distance': round(avg_distance * 100, 2),
        'max_distance': round(max_distance * 100, 2),
        'pct_near_zero': round(near_zero, 1)
    }


def calculate_ma(df: pd.DataFrame, column: str, periods: list) -> pd.DataFrame:
    """Tính Moving Average cho các periods"""
    for period in periods:
        df[f'{column}_ma{period}'] = df[column].rolling(window=period).mean()
    return df


def calculate_convergence(ma5: float, ma20: float, ma60: float) -> dict:
    """Tính % hội tụ giữa các MA"""
    def diff_percent(a, b):
        if a == 0 and b == 0:
            return 0
        avg = (a + b) / 2
        return abs(a - b) / avg * 100 if avg != 0 else 0
    
    def max_deviation(a, b, c):
        avg = (a + b + c) / 3
        if avg == 0:
            return 0
        return max(
            abs(a - avg) / avg * 100,
            abs(b - avg) / avg * 100,
            abs(c - avg) / avg * 100
        )
    
    return {
        "ma5_20": round(diff_percent(ma5, ma20), 2),
        "ma20_60": round(diff_percent(ma20, ma60), 2),
        "ma5_60": round(diff_percent(ma5, ma60), 2),
        "maConverge": round(max_deviation(ma5, ma20, ma60), 2)
    }


def fetch_stock_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    """Fetch dữ liệu OHLCV của 1 mã"""
    try:
        stock = Vnstock().stock(symbol=symbol, source='VCI')
        df = stock.quote.history(start=start_date, end=end_date, interval='1D')
        
        if df is None or len(df) == 0:
            return None
        
        # Chuẩn hóa column names
        df = df.rename(columns={
            'time': 'date',
            'open': 'o',
            'high': 'h', 
            'low': 'l',
            'close': 'c',
            'volume': 'v'
        })
        
        # Chỉ giữ các cột cần thiết
        required_cols = ['date', 'o', 'h', 'l', 'c', 'v']
        for col in required_cols:
            if col not in df.columns:
                # Thử tìm column tương tự
                for orig_col in df.columns:
                    if col in orig_col.lower():
                        df = df.rename(columns={orig_col: col})
                        break
        
        df = df[['date', 'o', 'h', 'l', 'c', 'v']].copy()
        
        # Tính MA cho giá (close)
        df = calculate_ma(df, 'c', [5, 20, 60])
        
        # Tính VA (Volume Average)
        df = calculate_ma(df, 'v', [5, 20, 60])
        
        # Rename columns
        df = df.rename(columns={
            'c_ma5': 'ma5',
            'c_ma20': 'ma20', 
            'c_ma60': 'ma60',
            'v_ma5': 'va5',
            'v_ma20': 'va20',
            'v_ma60': 'va60'
        })
        
        # Convert date to string
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        
        return df
        
    except Exception as e:
        print(f"  ❌ Error fetching {symbol}: {e}")
        return None


def get_all_symbols() -> list:
    """Lấy danh sách tất cả mã chứng khoán"""
    try:
        stock = Vnstock().stock(symbol='VN30', source='VCI')
        
        all_symbols = []
        
        for exchange in ['HOSE', 'HNX', 'UPCOM']:
            try:
                symbols_df = stock.listing.symbols_by_exchange(exchange=exchange)
                if symbols_df is not None and len(symbols_df) > 0:
                    # Lấy column chứa symbol
                    if 'symbol' in symbols_df.columns:
                        symbols = symbols_df['symbol'].tolist()
                    elif 'ticker' in symbols_df.columns:
                        symbols = symbols_df['ticker'].tolist()
                    else:
                        symbols = symbols_df.iloc[:, 0].tolist()
                    
                    for s in symbols:
                        all_symbols.append({
                            'symbol': s,
                            'exchange': exchange
                        })
                    print(f"  {exchange}: {len(symbols)} mã")
            except Exception as e:
                print(f"  ⚠️ Không thể lấy {exchange}: {e}")
        
        return all_symbols
        
    except Exception as e:
        print(f"❌ Error getting symbols: {e}")
        return []


def process_stock(symbol_info: dict, start_date: str, end_date: str) -> dict | None:
    """Xử lý 1 mã: fetch data, tính MA/VA/ADMF, trả về kết quả"""
    symbol = symbol_info['symbol']
    exchange = symbol_info['exchange']
    
    df = fetch_stock_data(symbol, start_date, end_date)
    
    if df is None or len(df) < 60:
        return None
    
    # Tính ADMF
    df['admf'] = calculate_admf(df, length=ADMF_LENGTH, price_enable=True, ad_weight=0.0)
    
    # Lấy dữ liệu mới nhất cho snapshot
    latest = df.iloc[-1]
    
    # Tính convergence MA
    ma5 = latest.get('ma5', 0) or 0
    ma20 = latest.get('ma20', 0) or 0
    ma60 = latest.get('ma60', 0) or 0
    va5 = latest.get('va5', 0) or 0
    va20 = latest.get('va20', 0) or 0
    va60 = latest.get('va60', 0) or 0
    
    convergence = calculate_convergence(ma5, ma20, ma60)
    
    # VA convergence
    def va_diff(a, b):
        if a == 0 and b == 0:
            return 0
        avg = (a + b) / 2
        return abs(a - b) / avg * 100 if avg != 0 else 0
    
    va_converge = max(
        va_diff(va5, va20),
        va_diff(va20, va60),
        va_diff(va5, va60)
    ) / 3
    
    # Tính ADMF oscillation cho các khoảng thời gian
    # 1 tháng ≈ 22 ngày giao dịch, 2 tháng ≈ 44, 3 tháng ≈ 66, 4 tháng ≈ 88
    admf_1m = calculate_admf_oscillation(df['admf'], 22)
    admf_2m = calculate_admf_oscillation(df['admf'], 44)
    admf_3m = calculate_admf_oscillation(df['admf'], 66)
    admf_4m = calculate_admf_oscillation(df['admf'], 88)
    
    # Snapshot data (cho việc lọc nhanh)
    snapshot = {
        "symbol": symbol,
        "exchange": exchange,
        "price": round(latest['c'], 2),
        "volume": int(latest['v']),
        "ma5": round(ma5, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "va5": int(va5),
        "va20": int(va20),
        "va60": int(va60),
        **convergence,
        "va5_20": round(va_diff(va5, va20), 2),
        "va20_60": round(va_diff(va20, va60), 2),
        "vaConverge": round(va_converge, 2),
        "admf": round(latest.get('admf', 0) or 0, 0),
        "admf_1m": admf_1m,
        "admf_2m": admf_2m,
        "admf_3m": admf_3m,
        "admf_4m": admf_4m,
        "totalDays": len(df)
    }
    
    # Daily data (cho biểu đồ nến)
    # Tối ưu: dùng arrays thay vì objects để giảm size
    daily = {
        "symbol": symbol,
        "exchange": exchange,
        "updated": end_date,
        "columns": ["date", "o", "h", "l", "c", "v", "ma5", "ma20", "ma60", "va5", "va20", "va60", "admf"],
        "data": []
    }
    
    for _, row in df.iterrows():
        daily["data"].append([
            row['date'],
            round(row['o'], 2) if pd.notna(row['o']) else None,
            round(row['h'], 2) if pd.notna(row['h']) else None,
            round(row['l'], 2) if pd.notna(row['l']) else None,
            round(row['c'], 2) if pd.notna(row['c']) else None,
            int(row['v']) if pd.notna(row['v']) else None,
            round(row['ma5'], 2) if pd.notna(row.get('ma5')) else None,
            round(row['ma20'], 2) if pd.notna(row.get('ma20')) else None,
            round(row['ma60'], 2) if pd.notna(row.get('ma60')) else None,
            int(row['va5']) if pd.notna(row.get('va5')) else None,
            int(row['va20']) if pd.notna(row.get('va20')) else None,
            int(row['va60']) if pd.notna(row.get('va60')) else None,
            round(row['admf'], 0) if pd.notna(row.get('admf')) else None,
        ])
    
    return {
        "snapshot": snapshot,
        "daily": daily
    }


def main():
    print("=" * 60)
    print("VN STOCK MA/VA SCANNER - DATA FETCHER")
    print("=" * 60)
    
    # Tạo thư mục output
    OUTPUT_DIR.mkdir(exist_ok=True)
    DAILY_DIR.mkdir(exist_ok=True)
    
    # Tính ngày bắt đầu và kết thúc
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=YEARS_HISTORY * 365)).strftime('%Y-%m-%d')
    
    print(f"\n📅 Khoảng thời gian: {start_date} → {end_date}")
    
    # Lấy danh sách mã
    print("\n📋 Đang lấy danh sách mã chứng khoán...")
    symbols = get_all_symbols()
    print(f"   Tổng cộng: {len(symbols)} mã")
    
    if len(symbols) == 0:
        print("❌ Không lấy được danh sách mã. Thoát.")
        return
    
    # Xử lý từng mã
    print(f"\n🔄 Bắt đầu fetch dữ liệu...")
    
    snapshots = []
    success_count = 0
    error_count = 0
    
    for i, symbol_info in enumerate(symbols):
        symbol = symbol_info['symbol']
        progress = f"[{i+1}/{len(symbols)}]"
        
        print(f"{progress} {symbol}...", end=" ", flush=True)
        
        result = process_stock(symbol_info, start_date, end_date)
        
        if result:
            # Lưu daily data
            daily_file = DAILY_DIR / f"{symbol}.json"
            with open(daily_file, 'w', encoding='utf-8') as f:
                json.dump(result['daily'], f, ensure_ascii=False)
            
            snapshots.append(result['snapshot'])
            success_count += 1
            print(f"✓ {result['snapshot']['totalDays']} ngày")
        else:
            error_count += 1
            print("✗ Bỏ qua")
        
        time.sleep(SLEEP_BETWEEN_REQUESTS)
    
    # Lưu snapshot
    print(f"\n💾 Đang lưu snapshot.json...")
    snapshot_data = {
        "updated": end_date,
        "generated": datetime.now().isoformat(),
        "totalStocks": len(snapshots),
        "stocks": sorted(snapshots, key=lambda x: x['symbol'])
    }
    
    with open(OUTPUT_DIR / "snapshot.json", 'w', encoding='utf-8') as f:
        json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
    
    # Thống kê
    print("\n" + "=" * 60)
    print("📊 KẾT QUẢ")
    print("=" * 60)
    print(f"   ✓ Thành công: {success_count} mã")
    print(f"   ✗ Lỗi/Bỏ qua: {error_count} mã")
    print(f"   📁 snapshot.json: {(OUTPUT_DIR / 'snapshot.json').stat().st_size / 1024:.1f} KB")
    
    # Tính tổng size daily files
    total_daily_size = sum(f.stat().st_size for f in DAILY_DIR.glob("*.json"))
    print(f"   📁 daily/*.json: {total_daily_size / 1024 / 1024:.1f} MB ({success_count} files)")
    
    print("\n✅ HOÀN TẤT!")


if __name__ == "__main__":
    main()
