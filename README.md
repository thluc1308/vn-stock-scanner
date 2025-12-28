# 📊 VN Stock MA/VA Scanner

Công cụ lọc cổ phiếu Việt Nam có MA và VA hội tụ - dấu hiệu tích lũy trước breakout.

![Screenshot](screenshot.png)

## ✨ Tính năng

- **Lọc 1,500+ mã** chứng khoán VN (HOSE, HNX, UPCOM)
- **Biểu đồ nến** với MA5, MA20, MA60
- **Volume chart** với VA5, VA20, VA60
- **Bộ lọc tùy chỉnh** ngưỡng % hội tụ
- **Tự động cập nhật** hàng ngày qua GitHub Actions
- **Miễn phí 100%** - host trên GitHub Pages

## 🚀 Cài đặt

### Bước 1: Fork repo này

Click nút **Fork** ở góc trên bên phải.

### Bước 2: Bật GitHub Pages

1. Vào **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / **docs**
4. Save

### Bước 3: Bật GitHub Actions

1. Vào **Settings** → **Actions** → **General**
2. Chọn **Allow all actions**
3. Save

### Bước 4: Chạy fetch data lần đầu

1. Vào tab **Actions**
2. Chọn workflow **Update Stock Data**
3. Click **Run workflow**
4. Chờ 10-20 phút để fetch data

### Bước 5: Truy cập blog

```
https://[username].github.io/vn-stock-scanner
```

## 🛠️ Chạy local

### Yêu cầu

- Python 3.10+
- Node.js (optional, để dev)

### Cài đặt

```bash
# Clone repo
git clone https://github.com/[username]/vn-stock-scanner.git
cd vn-stock-scanner

# Cài đặt dependencies
pip install vnstock pandas

# Fetch data
cd scripts
python fetch_data.py

# Move data
cp -r data ../docs/

# Mở browser
cd ../docs
python -m http.server 8000
# Truy cập http://localhost:8000
```

## 📁 Cấu trúc thư mục

```
vn-stock-scanner/
├── .github/
│   └── workflows/
│       └── update-data.yml    # GitHub Actions workflow
├── scripts/
│   └── fetch_data.py          # Script fetch data từ vnstock
├── docs/
│   ├── index.html             # React app
│   ├── App.jsx                # React component (reference)
│   └── data/
│       ├── snapshot.json      # Dữ liệu mới nhất (500KB)
│       └── daily/
│           ├── VNM.json       # 2 năm OHLCV + MA + VA
│           ├── VCB.json
│           └── ...
└── README.md
```

## 📊 Dữ liệu

### snapshot.json (~500 KB)

Chứa dữ liệu mới nhất của tất cả mã, dùng để lọc nhanh:

```json
{
  "updated": "2024-12-27",
  "totalStocks": 1523,
  "stocks": [
    {
      "symbol": "VNM",
      "exchange": "HOSE",
      "price": 72.5,
      "ma5": 72.1, "ma20": 71.8, "ma60": 70.5,
      "va5": 1300000, "va20": 1180000, "va60": 1050000,
      "ma5_20": 0.4,
      "maConverge": 1.2,
      "vaConverge": 8.5
    }
  ]
}
```

### daily/{SYMBOL}.json (~50 KB/mã)

Chứa 2 năm dữ liệu OHLCV + MA + VA, dùng để vẽ chart:

```json
{
  "symbol": "VNM",
  "columns": ["date", "o", "h", "l", "c", "v", "ma5", "ma20", "ma60", "va5", "va20", "va60"],
  "data": [
    ["2023-01-03", 75.2, 76.0, 74.8, 75.5, 1250000, null, null, null, null, null, null],
    ["2023-01-04", 75.5, 76.2, 75.0, 75.8, 1180000, null, null, null, null, null, null],
    ...
  ]
}
```

## 🔧 Cấu hình

### Thay đổi ngưỡng mặc định

Sửa trong `docs/index.html`:

```javascript
const [thresholds, setThresholds] = React.useState({
  maConverge: 10,    // MA hội tụ <= 10%
  vaConverge: 50,    // VA hội tụ <= 50%
  ma5_20: 5,         // MA5-MA20 <= 5%
  ma20_60: 8,        // MA20-MA60 <= 8%
});
```

### Thay đổi lịch cập nhật

Sửa trong `.github/workflows/update-data.yml`:

```yaml
schedule:
  # Chạy lúc 6:30 AM (GMT+7) = 23:30 UTC
  - cron: '30 23 * * 0-4'
```

### Thay đổi số năm lịch sử

Sửa trong `scripts/fetch_data.py`:

```python
YEARS_HISTORY = 2  # Thay đổi thành 3, 5, v.v.
```

## 📈 Cách đọc kết quả

| Chỉ báo | Ý nghĩa |
|---------|---------|
| **MA5-20 < 3%** | Giá đang sideway mạnh |
| **MA Conv < 5%** | MA5, MA20, MA60 gần nhau - tích lũy |
| **VA Conv < 30%** | Khối lượng ổn định - chưa có sóng |
| **Kết hợp cả hai** | Cơ hội tốt nhất để theo dõi breakout |

## ⚠️ Disclaimer

Công cụ này chỉ mang tính chất tham khảo, không phải khuyến nghị đầu tư. Mọi quyết định đầu tư là trách nhiệm của bạn.

## 📝 License

MIT License

## 🤝 Đóng góp

Mọi đóng góp đều được chào đón! Hãy tạo Pull Request hoặc Issue.
