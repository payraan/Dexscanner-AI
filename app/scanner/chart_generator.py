import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import pandas as pd
import io
from typing import Dict, Optional, List

# سطوح فیبوناچی اصلاحی که میخواهیم نمایش دهیم
FIB_RETRACEMENT_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786]

class ChartGenerator:
    def __init__(self):
        plt.style.use('dark_background')

    def _calculate_fib_retracement_levels(self, high: float, low: float) -> Dict:
        """سطوح فیبوناچی اصلاحی را بر اساس سقف و کف محاسبه می‌کند."""
        price_range = high - low
        if price_range <= 0:
            return {}
        # سطوح کلیدی 0.0 و 1.0 را هم برای کامل بودن اضافه می‌کنیم
        levels_to_calc = [0.0] + FIB_RETRACEMENT_LEVELS + [1.0]
        return {level: high - (price_range * level) for level in levels_to_calc}

    def _draw_fibonacci_levels(self, ax, fib_state: Dict):
        """فیبوناچی اصلاحی و تارگت‌ها را بر روی نمودار رسم می‌کند."""
        if not fib_state:
            return

        high, low = fib_state['high'], fib_state['low']
        retracement_levels = self._calculate_fib_retracement_levels(high, low)
        
        # رسم سطوح اصلاحی (Retracement)
        fib_colors = ['#e74c3c', '#ff9ff3', '#54a0ff', '#5f27cd', '#00d2d3', '#ff9f43', '#2ecc71'] # 7 رنگ برای 7 سطح
        for i, (level, price) in enumerate(retracement_levels.items()):
            ax.axhline(y=price, color=fib_colors[i % len(fib_colors)], linestyle='--', linewidth=1, alpha=0.7)
            ax.text(ax.get_xlim()[1] + 0.01 * (ax.get_xlim()[1] - ax.get_xlim()[0]), price, f'Fib {level:.3f}', 
                    color='white', va='center', ha='left', fontsize=9,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7, edgecolor=fib_colors[i % len(fib_colors)], linewidth=1))

        # رسم تارگت‌ها (Extension)
        target_colors = ['#4caf50', '#8bc34a', '#cddc39']
        targets = {
            '1.272': fib_state.get('target1'),
            '1.618': fib_state.get('target2'),
            '2.000': fib_state.get('target3')
        }
        for i, (level, price) in enumerate(targets.items()):
            if price:
                ax.axhline(y=price, color=target_colors[i % len(target_colors)], linestyle=':', linewidth=1.5, alpha=0.9)
                ax.text(ax.get_xlim()[1] + 0.01 * (ax.get_xlim()[1] - ax.get_xlim()[0]), price, f'Target {level}', 
                        color='white', va='center', ha='left', fontsize=10, fontweight='bold',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7, edgecolor=target_colors[i % len(target_colors)], linewidth=1.5))

    def _draw_zones(self, ax, zones: List[Dict]):
        """نواحی حمایت و مقاومت را رسم می‌کند."""
        if not zones:
            return
        for zone in zones:
            color = '#ff6b6b' if zone['type'] == 'resistance' else '#51cf66'
            alpha = min(0.15 + (zone.get('score', 0) / 10) * 0.25, 0.4)
            zone_height = zone['price'] * 0.015 # کمی ضخیم‌تر
            ax.axhspan(zone['price'] - zone_height / 2, zone['price'] + zone_height / 2, color=color, alpha=alpha)

    def create_signal_chart(self, df: pd.DataFrame, signal_data: Dict) -> Optional[bytes]:
        """نمودار کندل استیک را با تمام اندیکاتورها و مقیاس‌بندی صحیح ایجاد می‌کند."""
        if df.empty or len(df) < 10:
            return None

        # نام توکن از signal_data گرفته می‌شود که همیشه وجود دارد
        token_symbol = signal_data.get('token', 'Unknown')

        try:
            fig, ax = plt.subplots(figsize=(16, 9))
            fig.patch.set_facecolor('#1a1a1a')
            ax.set_facecolor('#1a1a1a')

            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
            
            self._draw_candlesticks(ax, df)
            self._add_moving_averages(ax, df)
            self._draw_zones(ax, signal_data.get('zones'))

            fib_state = signal_data.get('fibonacci_state')
            self._draw_fibonacci_levels(ax, fib_state)

            self._add_watermark(ax)
            self._add_price_box(ax, df)
            self._format_chart(ax, token_symbol, signal_data, df, fib_state)

            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', facecolor='#1a1a1a', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            plt.close(fig)
            return buffer.getvalue()
            
        except Exception as e:
            print(f"Chart generation error for {token_symbol}: {e}")
            return None

    def _draw_candlesticks(self, ax, df):
        """رسم کندل‌ها با عرض مناسب."""
        # این منطق از کد قدیمی شما گرفته شده و بهینه شده است
        for i, row in df.iterrows():
            color = '#00ff88' if row['close'] >= row['open'] else '#ff4444'
            ax.plot([row['datetime'], row['datetime']], [row['low'], row['high']], color=color, linewidth=1.5, alpha=0.9)
            
            time_diff = (df['datetime'].iloc[1] - df['datetime'].iloc[0]) if len(df) > 1 else timedelta(minutes=5)
            width = time_diff * 0.7
            
            body_height = abs(row['close'] - row['open'])
            body_bottom = min(row['open'], row['close'])
            if body_height > 0:
                rect = plt.Rectangle((row['datetime'] - width/2, body_bottom), width, body_height, facecolor=color, alpha=0.9)
                ax.add_patch(rect)

    def _add_moving_averages(self, ax, df):
        """اضافه کردن EMA."""
        if len(df) >= 20:
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            ax.plot(df['datetime'], df['ema20'], color='#ffa726', linewidth=2, alpha=0.8, label='EMA 20')
        if len(df) >= 50:
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            ax.plot(df['datetime'], df['ema50'], color='#42a5f5', linewidth=2, alpha=0.8, label='EMA 50')

    def _add_watermark(self, ax):
        """اضافه کردن واترمارک."""
        ax.text(0.5, 0.5, 'NarmoonAI', transform=ax.transAxes, fontsize=40,
                color='gray', alpha=0.15, ha='center', va='center', style='italic')

    def _format_chart(self, ax, token_symbol, signal_data, df, fib_state):
        """فرمت نهایی چارت با مقیاس‌بندی هوشمند."""
        timeframe_str = signal_data.get('timeframe', '')
        current_price = df['close'].iloc[-1]
        ax.set_title(f"{token_symbol} - {timeframe_str} Chart - Price: ${current_price:.8f}", color='white', fontsize=14, fontweight='bold', loc='left')
        ax.grid(True, alpha=0.15, color='#444444')
        
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position('right')
        ax.set_ylabel('Price (USDT)', color='white', fontsize=10)

        # --- بخش کلیدی: تنظیم دستی محدوده محور Y برای نمایش کامل تارگت‌ها ---
        all_prices = [df['low'].min(), df['high'].max()]
        if fib_state and fib_state.get('target3'):
            all_prices.append(fib_state['target3']) # اضافه کردن بالاترین تارگت به لیست قیمت‌ها
        
        min_price = min(p for p in all_prices if p is not None and p > 0)
        max_price = max(p for p in all_prices if p is not None)
        
        padding = (max_price - min_price) * 0.1 # 10% حاشیه در بالا و پایین
        ax.set_ylim(min_price - padding, max_price + padding)
        # --- پایان بخش کلیدی ---

        # تنظیم محور زمان
        total_duration = df['datetime'].iloc[-1] - df['datetime'].iloc[0]
        if total_duration < timedelta(days=2):
            formatter = mdates.DateFormatter('%H:%M\n%d-%b')
        else:
            formatter = mdates.DateFormatter('%d-%b')
        ax.xaxis.set_major_formatter(formatter)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha='center')
        
        ax.tick_params(axis='both', colors='#888888', labelsize=9)
        for spine in ax.spines.values():
            spine.set_edgecolor('#333333')
        
        # افزایش حاشیه سمت راست برای نمایش لیبل‌های فیبوناچی
        right_margin = (df['datetime'].iloc[-1] - df['datetime'].iloc[0]) * 0.15
        ax.set_xlim(df['datetime'].iloc[0], df['datetime'].iloc[-1] + right_margin)
        
        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc='upper left', framealpha=0.5, fontsize=9)

chart_generator = ChartGenerator()
