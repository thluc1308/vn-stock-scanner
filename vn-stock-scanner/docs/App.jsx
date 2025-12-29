import React, { useState, useEffect, useMemo, useRef } from 'react';

// ============== CONSTANTS ==============
const DATA_BASE_URL = './data';

// ============== UTILITY FUNCTIONS ==============
const formatNumber = (num, decimals = 1) => {
  if (num === null || num === undefined) return '-';
  if (num >= 1000000000) return (num / 1000000000).toFixed(1) + 'B';
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toFixed(decimals);
};

const formatPrice = (price) => {
  if (price === null || price === undefined) return '-';
  return price.toFixed(2);
};

// ============== CANDLESTICK CHART COMPONENT ==============
const CandlestickChart = ({ data, symbol }) => {
  const containerRef = useRef(null);
  const canvasRef = useRef(null);
  const [tooltip, setTooltip] = useState(null);
  const [viewRange, setViewRange] = useState({ start: 0, end: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState(0);

  useEffect(() => {
    if (!data || data.length === 0) return;
    // Show last 60 days by default
    const end = data.length;
    const start = Math.max(0, end - 60);
    setViewRange({ start, end });
  }, [data]);

  useEffect(() => {
    if (!data || data.length === 0 || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const rect = containerRef.current.getBoundingClientRect();
    
    // Set canvas size
    canvas.width = rect.width * 2; // Retina
    canvas.height = 400 * 2;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = '400px';
    ctx.scale(2, 2);

    const width = rect.width;
    const height = 400;
    const padding = { top: 20, right: 60, bottom: 30, left: 10 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Get visible data
    const visibleData = data.slice(viewRange.start, viewRange.end);
    if (visibleData.length === 0) return;

    // Calculate price range
    const prices = visibleData.flatMap(d => [d.h, d.l, d.ma5, d.ma20, d.ma60].filter(v => v !== null));
    const minPrice = Math.min(...prices) * 0.99;
    const maxPrice = Math.max(...prices) * 1.01;
    const priceRange = maxPrice - minPrice;

    // Calculate candle width
    const candleWidth = Math.max(2, Math.min(12, chartWidth / visibleData.length - 2));
    const gap = (chartWidth - candleWidth * visibleData.length) / (visibleData.length + 1);

    // Clear canvas
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);

    // Draw grid
    ctx.strokeStyle = '#f0f0f0';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
      const y = padding.top + (chartHeight / 5) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();

      // Price labels
      const price = maxPrice - (priceRange / 5) * i;
      ctx.fillStyle = '#666';
      ctx.font = '11px sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(price.toFixed(1), width - padding.right + 5, y + 4);
    }

    // Helper: price to Y
    const priceToY = (price) => {
      return padding.top + (1 - (price - minPrice) / priceRange) * chartHeight;
    };

    // Draw MA lines
    const drawLine = (key, color) => {
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      let started = false;
      visibleData.forEach((d, i) => {
        if (d[key] === null) return;
        const x = padding.left + gap + i * (candleWidth + gap) + candleWidth / 2;
        const y = priceToY(d[key]);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();
    };

    drawLine('ma5', '#f59e0b');   // Yellow
    drawLine('ma20', '#3b82f6');  // Blue  
    drawLine('ma60', '#8b5cf6');  // Purple

    // Draw candles
    visibleData.forEach((d, i) => {
      const x = padding.left + gap + i * (candleWidth + gap);
      const isUp = d.c >= d.o;
      
      ctx.fillStyle = isUp ? '#22c55e' : '#ef4444';
      ctx.strokeStyle = isUp ? '#16a34a' : '#dc2626';
      ctx.lineWidth = 1;

      // Wick
      const wickX = x + candleWidth / 2;
      ctx.beginPath();
      ctx.moveTo(wickX, priceToY(d.h));
      ctx.lineTo(wickX, priceToY(d.l));
      ctx.stroke();

      // Body
      const bodyTop = priceToY(Math.max(d.o, d.c));
      const bodyBottom = priceToY(Math.min(d.o, d.c));
      const bodyHeight = Math.max(1, bodyBottom - bodyTop);
      
      if (isUp) {
        ctx.fillRect(x, bodyTop, candleWidth, bodyHeight);
      } else {
        ctx.fillRect(x, bodyTop, candleWidth, bodyHeight);
      }
      ctx.strokeRect(x, bodyTop, candleWidth, bodyHeight);
    });

    // Draw legend
    ctx.font = '11px sans-serif';
    const legends = [
      { label: 'MA5', color: '#f59e0b' },
      { label: 'MA20', color: '#3b82f6' },
      { label: 'MA60', color: '#8b5cf6' },
    ];
    let legendX = padding.left + 10;
    legends.forEach(leg => {
      ctx.fillStyle = leg.color;
      ctx.fillRect(legendX, 6, 16, 3);
      ctx.fillStyle = '#666';
      ctx.fillText(leg.label, legendX + 20, 12);
      legendX += 60;
    });

  }, [data, viewRange]);

  // Mouse handlers for tooltip and zoom
  const handleMouseMove = (e) => {
    if (!data || !containerRef.current) return;
    
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const padding = { left: 10, right: 60 };
    const chartWidth = rect.width - padding.left - padding.right;
    
    const visibleData = data.slice(viewRange.start, viewRange.end);
    const candleWidth = chartWidth / visibleData.length;
    const index = Math.floor((x - padding.left) / candleWidth);
    
    if (index >= 0 && index < visibleData.length) {
      const d = visibleData[index];
      setTooltip({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        data: d
      });
    } else {
      setTooltip(null);
    }

    // Dragging
    if (isDragging) {
      const diff = Math.round((dragStart - x) / 10);
      const newStart = Math.max(0, viewRange.start + diff);
      const newEnd = Math.min(data.length, viewRange.end + diff);
      if (newEnd - newStart === viewRange.end - viewRange.start) {
        setViewRange({ start: newStart, end: newEnd });
        setDragStart(x);
      }
    }
  };

  const handleWheel = (e) => {
    e.preventDefault();
    if (!data) return;
    
    const zoomFactor = e.deltaY > 0 ? 1.1 : 0.9;
    const currentRange = viewRange.end - viewRange.start;
    const newRange = Math.max(20, Math.min(data.length, Math.round(currentRange * zoomFactor)));
    const center = (viewRange.start + viewRange.end) / 2;
    const newStart = Math.max(0, Math.round(center - newRange / 2));
    const newEnd = Math.min(data.length, newStart + newRange);
    
    setViewRange({ start: newStart, end: newEnd });
  };

  if (!data || data.length === 0) {
    return (
      <div className="h-[400px] flex items-center justify-center bg-gray-50 rounded-lg">
        <div className="text-gray-400">Đang tải dữ liệu...</div>
      </div>
    );
  }

  return (
    <div 
      ref={containerRef} 
      className="relative bg-white rounded-lg border"
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setTooltip(null)}
      onMouseDown={(e) => { setIsDragging(true); setDragStart(e.clientX - containerRef.current.getBoundingClientRect().left); }}
      onMouseUp={() => setIsDragging(false)}
      onWheel={handleWheel}
    >
      <canvas ref={canvasRef} className="cursor-crosshair" />
      
      {/* Tooltip */}
      {tooltip && (
        <div 
          className="absolute bg-gray-900 text-white text-xs rounded px-2 py-1 pointer-events-none z-10"
          style={{ left: tooltip.x + 10, top: tooltip.y - 80 }}
        >
          <div className="font-semibold">{tooltip.data.date}</div>
          <div>O: {formatPrice(tooltip.data.o)} H: {formatPrice(tooltip.data.h)}</div>
          <div>L: {formatPrice(tooltip.data.l)} C: {formatPrice(tooltip.data.c)}</div>
          <div>Vol: {formatNumber(tooltip.data.v)}</div>
          <div className="border-t border-gray-700 mt-1 pt-1">
            <span className="text-yellow-400">MA5: {formatPrice(tooltip.data.ma5)}</span>
            <span className="text-blue-400 ml-2">MA20: {formatPrice(tooltip.data.ma20)}</span>
          </div>
        </div>
      )}

      {/* Zoom controls */}
      <div className="absolute top-2 right-2 flex gap-1">
        <button 
          onClick={() => {
            const newRange = Math.max(20, viewRange.end - viewRange.start - 20);
            setViewRange({ start: viewRange.end - newRange, end: viewRange.end });
          }}
          className="w-6 h-6 bg-gray-100 hover:bg-gray-200 rounded text-sm"
        >+</button>
        <button 
          onClick={() => {
            const newRange = Math.min(data.length, viewRange.end - viewRange.start + 20);
            const newStart = Math.max(0, viewRange.end - newRange);
            setViewRange({ start: newStart, end: viewRange.end });
          }}
          className="w-6 h-6 bg-gray-100 hover:bg-gray-200 rounded text-sm"
        >−</button>
        <button 
          onClick={() => setViewRange({ start: 0, end: data.length })}
          className="px-2 h-6 bg-gray-100 hover:bg-gray-200 rounded text-xs"
        >All</button>
      </div>

      {/* Range info */}
      <div className="absolute bottom-2 left-2 text-xs text-gray-500">
        {data[viewRange.start]?.date} → {data[viewRange.end - 1]?.date} ({viewRange.end - viewRange.start} ngày)
      </div>
    </div>
  );
};

// ============== VOLUME CHART COMPONENT ==============
const VolumeChart = ({ data }) => {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!data || data.length === 0 || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const rect = containerRef.current.getBoundingClientRect();
    
    canvas.width = rect.width * 2;
    canvas.height = 120 * 2;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = '120px';
    ctx.scale(2, 2);

    const width = rect.width;
    const height = 120;
    const padding = { top: 10, right: 60, bottom: 20, left: 10 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Last 60 days
    const visibleData = data.slice(-60);
    const maxVol = Math.max(...visibleData.map(d => d.v));
    const barWidth = Math.max(2, chartWidth / visibleData.length - 2);
    const gap = (chartWidth - barWidth * visibleData.length) / (visibleData.length + 1);

    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, width, height);

    // Draw volume bars
    visibleData.forEach((d, i) => {
      const x = padding.left + gap + i * (barWidth + gap);
      const barHeight = (d.v / maxVol) * chartHeight;
      const y = padding.top + chartHeight - barHeight;
      
      const isUp = d.c >= d.o;
      ctx.fillStyle = isUp ? 'rgba(34, 197, 94, 0.6)' : 'rgba(239, 68, 68, 0.6)';
      ctx.fillRect(x, y, barWidth, barHeight);
    });

    // Draw VA lines
    const drawVALine = (key, color) => {
      ctx.beginPath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      let started = false;
      visibleData.forEach((d, i) => {
        if (d[key] === null) return;
        const x = padding.left + gap + i * (barWidth + gap) + barWidth / 2;
        const y = padding.top + chartHeight - (d[key] / maxVol) * chartHeight;
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();
    };

    drawVALine('va5', '#f59e0b');
    drawVALine('va20', '#3b82f6');
    drawVALine('va60', '#8b5cf6');

    // Legend
    ctx.font = '10px sans-serif';
    ctx.fillStyle = '#666';
    ctx.fillText('VA5', padding.left + 10, height - 5);
    ctx.fillStyle = '#f59e0b';
    ctx.fillRect(padding.left + 30, height - 10, 12, 2);
    ctx.fillStyle = '#666';
    ctx.fillText('VA20', padding.left + 50, height - 5);
    ctx.fillStyle = '#3b82f6';
    ctx.fillRect(padding.left + 80, height - 10, 12, 2);

  }, [data]);

  return (
    <div ref={containerRef} className="bg-white rounded-lg border">
      <canvas ref={canvasRef} />
    </div>
  );
};

// ============== MAIN APP ==============
export default function StockScanner() {
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedStock, setSelectedStock] = useState(null);
  const [dailyData, setDailyData] = useState(null);
  const [loadingDaily, setLoadingDaily] = useState(false);

  // Filters
  const [thresholds, setThresholds] = useState({
    maConverge: 10,
    vaConverge: 50,
    ma5_20: 5,
    ma20_60: 8,
  });
  const [exchange, setExchange] = useState('ALL');
  const [sortBy, setSortBy] = useState('maConverge');
  const [sortOrder, setSortOrder] = useState('asc');

  // Load snapshot
  useEffect(() => {
    const loadSnapshot = async () => {
      try {
        const res = await fetch(`${DATA_BASE_URL}/snapshot.json`);
        if (!res.ok) throw new Error('Không thể tải dữ liệu');
        const data = await res.json();
        setSnapshot(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadSnapshot();
  }, []);

  // Load daily data when stock selected
  useEffect(() => {
    if (!selectedStock) {
      setDailyData(null);
      return;
    }

    const loadDaily = async () => {
      setLoadingDaily(true);
      try {
        const res = await fetch(`${DATA_BASE_URL}/daily/${selectedStock}.json`);
        if (!res.ok) throw new Error('Không thể tải dữ liệu');
        const data = await res.json();
        
        // Convert array format to object format
        const columns = data.columns;
        const parsed = data.data.map(row => {
          const obj = {};
          columns.forEach((col, i) => obj[col] = row[i]);
          return obj;
        });
        
        setDailyData(parsed);
      } catch (err) {
        console.error(err);
        setDailyData(null);
      } finally {
        setLoadingDaily(false);
      }
    };
    loadDaily();
  }, [selectedStock]);

  // Filtered & sorted data
  const filteredStocks = useMemo(() => {
    if (!snapshot?.stocks) return [];
    
    let result = snapshot.stocks.filter(stock => {
      if (exchange !== 'ALL' && stock.exchange !== exchange) return false;
      if (stock.maConverge > thresholds.maConverge) return false;
      if (stock.vaConverge > thresholds.vaConverge) return false;
      if (stock.ma5_20 > thresholds.ma5_20) return false;
      if (stock.ma20_60 > thresholds.ma20_60) return false;
      return true;
    });

    result.sort((a, b) => {
      const aVal = a[sortBy] ?? 0;
      const bVal = b[sortBy] ?? 0;
      return sortOrder === 'asc' ? aVal - bVal : bVal - aVal;
    });

    return result;
  }, [snapshot, thresholds, exchange, sortBy, sortOrder]);

  const getColorClass = (value, max) => {
    const ratio = value / max;
    if (ratio <= 0.3) return 'bg-green-100 text-green-800';
    if (ratio <= 0.6) return 'bg-yellow-100 text-yellow-800';
    if (ratio <= 0.8) return 'bg-orange-100 text-orange-800';
    return 'bg-red-100 text-red-800';
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full mx-auto mb-4"></div>
          <div className="text-gray-600">Đang tải dữ liệu...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center text-red-600">
          <div className="text-4xl mb-4">❌</div>
          <div>{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 via-purple-600 to-indigo-600 text-white">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <h1 className="text-2xl font-bold">📊 VN Stock MA/VA Scanner</h1>
          <p className="opacity-80 mt-1">
            Lọc cổ phiếu hội tụ MA/VA - Cập nhật: {snapshot?.updated}
          </p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Filters */}
          <div className="lg:col-span-1 space-y-4">
            <div className="bg-white rounded-xl shadow-sm p-4">
              <h2 className="font-semibold mb-4">⚙️ Bộ lọc</h2>
              
              {/* Exchange filter */}
              <div className="mb-4">
                <label className="text-sm text-gray-600 block mb-2">Sàn:</label>
                <div className="flex flex-wrap gap-2">
                  {['ALL', 'HOSE', 'HNX', 'UPCOM'].map(ex => (
                    <button
                      key={ex}
                      onClick={() => setExchange(ex)}
                      className={`px-3 py-1 rounded-full text-sm font-medium transition ${
                        exchange === ex 
                          ? 'bg-blue-600 text-white' 
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>

              {/* Threshold sliders */}
              {[
                { key: 'maConverge', label: 'MA Hội tụ', max: 20 },
                { key: 'vaConverge', label: 'VA Hội tụ', max: 100 },
                { key: 'ma5_20', label: 'MA5-MA20', max: 15 },
                { key: 'ma20_60', label: 'MA20-MA60', max: 20 },
              ].map(item => (
                <div key={item.key} className="mb-3">
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-600">{item.label}</span>
                    <span className="font-medium">≤ {thresholds[item.key]}%</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max={item.max}
                    step="0.5"
                    value={thresholds[item.key]}
                    onChange={(e) => setThresholds(prev => ({ 
                      ...prev, 
                      [item.key]: parseFloat(e.target.value) 
                    }))}
                    className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                  />
                </div>
              ))}

              {/* Sort */}
              <div className="border-t pt-4 mt-4">
                <label className="text-sm text-gray-600 block mb-2">Sắp xếp:</label>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="w-full p-2 border rounded-lg text-sm mb-2"
                >
                  <option value="maConverge">MA Hội tụ</option>
                  <option value="vaConverge">VA Hội tụ</option>
                  <option value="ma5_20">MA5-MA20</option>
                  <option value="price">Giá</option>
                  <option value="volume">Khối lượng</option>
                </select>
                <div className="flex gap-2">
                  <button
                    onClick={() => setSortOrder('asc')}
                    className={`flex-1 py-2 rounded-lg text-sm ${
                      sortOrder === 'asc' ? 'bg-blue-600 text-white' : 'bg-gray-100'
                    }`}
                  >↑ Tăng</button>
                  <button
                    onClick={() => setSortOrder('desc')}
                    className={`flex-1 py-2 rounded-lg text-sm ${
                      sortOrder === 'desc' ? 'bg-blue-600 text-white' : 'bg-gray-100'
                    }`}
                  >↓ Giảm</button>
                </div>
              </div>

              {/* Stats */}
              <div className="border-t pt-4 mt-4">
                <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg p-3 text-center">
                  <div className="text-3xl font-bold text-blue-600">{filteredStocks.length}</div>
                  <div className="text-sm text-gray-600">/ {snapshot?.totalStocks} mã</div>
                </div>
              </div>
            </div>
          </div>

          {/* Main content */}
          <div className="lg:col-span-3 space-y-4">
            {/* Chart area */}
            {selectedStock && (
              <div className="bg-white rounded-xl shadow-sm p-4">
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-lg font-semibold">
                    📈 {selectedStock}
                    {loadingDaily && <span className="ml-2 text-sm text-gray-400">Đang tải...</span>}
                  </h2>
                  <button
                    onClick={() => setSelectedStock(null)}
                    className="text-gray-400 hover:text-gray-600"
                  >✕</button>
                </div>
                
                <CandlestickChart data={dailyData} symbol={selectedStock} />
                
                {dailyData && (
                  <div className="mt-4">
                    <VolumeChart data={dailyData} />
                  </div>
                )}
              </div>
            )}

            {/* Stock list */}
            <div className="bg-white rounded-xl shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-3 text-left text-xs font-semibold text-gray-600">#</th>
                      <th className="px-3 py-3 text-left text-xs font-semibold text-gray-600">Mã</th>
                      <th className="px-3 py-3 text-left text-xs font-semibold text-gray-600">Sàn</th>
                      <th className="px-3 py-3 text-right text-xs font-semibold text-gray-600">Giá</th>
                      <th className="px-3 py-3 text-right text-xs font-semibold text-gray-600">KL</th>
                      <th className="px-3 py-3 text-center text-xs font-semibold text-blue-600">MA5-20</th>
                      <th className="px-3 py-3 text-center text-xs font-semibold text-blue-600">MA20-60</th>
                      <th className="px-3 py-3 text-center text-xs font-semibold text-green-600">MA Conv</th>
                      <th className="px-3 py-3 text-center text-xs font-semibold text-purple-600">VA Conv</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {filteredStocks.length === 0 ? (
                      <tr>
                        <td colSpan="9" className="px-4 py-12 text-center text-gray-500">
                          <div className="text-4xl mb-2">🔍</div>
                          <div>Không tìm thấy mã nào</div>
                        </td>
                      </tr>
                    ) : (
                      filteredStocks.slice(0, 100).map((stock, idx) => (
                        <tr 
                          key={stock.symbol}
                          onClick={() => setSelectedStock(stock.symbol)}
                          className={`hover:bg-blue-50 cursor-pointer transition ${
                            selectedStock === stock.symbol ? 'bg-blue-50' : ''
                          }`}
                        >
                          <td className="px-3 py-3 text-sm text-gray-500">{idx + 1}</td>
                          <td className="px-3 py-3 font-semibold text-gray-900">{stock.symbol}</td>
                          <td className="px-3 py-3 text-sm text-gray-500">{stock.exchange}</td>
                          <td className="px-3 py-3 text-right font-mono text-sm">{formatPrice(stock.price)}</td>
                          <td className="px-3 py-3 text-right text-sm text-gray-600">{formatNumber(stock.volume)}</td>
                          <td className="px-3 py-3 text-center">
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${getColorClass(stock.ma5_20, thresholds.ma5_20)}`}>
                              {stock.ma5_20?.toFixed(1)}%
                            </span>
                          </td>
                          <td className="px-3 py-3 text-center">
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${getColorClass(stock.ma20_60, thresholds.ma20_60)}`}>
                              {stock.ma20_60?.toFixed(1)}%
                            </span>
                          </td>
                          <td className="px-3 py-3 text-center">
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${getColorClass(stock.maConverge, thresholds.maConverge)}`}>
                              {stock.maConverge?.toFixed(1)}%
                            </span>
                          </td>
                          <td className="px-3 py-3 text-center">
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${getColorClass(stock.vaConverge, thresholds.vaConverge)}`}>
                              {stock.vaConverge?.toFixed(1)}%
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
              {filteredStocks.length > 100 && (
                <div className="px-4 py-3 bg-gray-50 text-center text-sm text-gray-500">
                  Hiển thị 100/{filteredStocks.length} mã. Thu hẹp bộ lọc để xem thêm.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
