import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta # <-- مشکل اینجا بود و حالا حل شد
import pandas as pd
import numpy as np
import io
from typing import Dict, Optional

class ChartGenerator:
    def __init__(self):
        plt.style.use('dark_background')

    def _calculate_fibonacci_retracement(self, df: pd.DataFrame):
        """Calculate Fibonacci retracement levels"""
        if len(df) < 20:
            return None
        
        high_point = df['high'].max()
        low_point = df['low'].min()
        price_range = high_point - low_point

        if price_range <= 0:
            return None

        levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        levels_dict = {level: high_point - (price_range * level) for level in levels}
        
        return {'levels': levels_dict, 'high_point': high_point, 'low_point': low_point}

    def _calculate_fibonacci_extension(self, df: pd.DataFrame):
        """Calculate Fibonacci extension levels"""
        if len(df) < 20:
            return None
            
        high_point = df['high'].max()
        low_point = df['low'].min()
        price_range = high_point - low_point

        if price_range <= 0:
            return None

        ext_levels = [1.272, 1.618]
        levels_dict = {level: high_point + (price_range * (level - 1.0)) for level in ext_levels}

        return {'levels': levels_dict}

    def _draw_fibonacci_retracement(self, ax, fib_data):
        """Draw Fibonacci retracement levels"""
        if not fib_data:
            return
            
        colors = ['#e74c3c', '#ff9ff3', '#54a0ff', '#5f27cd', '#00d2d3', '#ff9f43', '#2ecc71']
        for i, (level, price) in enumerate(fib_data['levels'].items()):
            ax.axhline(y=price, color=colors[i % len(colors)], linestyle='--', 
                       linewidth=1, alpha=0.7)
            ax.text(ax.get_xlim()[1], price, f'  Fib {level:.3f}', 
                   color=colors[i % len(colors)], va='center', ha='left', fontsize=9)

    def _draw_fibonacci_extension(self, ax, fib_ext_data):
        """Draw Fibonacci extension levels"""
        if not fib_ext_data:
            return
            
        colors = ['#4caf50', '#8bc34a']
        for i, (level, price) in enumerate(fib_ext_data['levels'].items()):
            ax.axhline(y=price, color=colors[i % len(colors)], linestyle=':', 
                       linewidth=1.2, alpha=0.9)
            ax.text(ax.get_xlim()[1], price, f'  Target {level:.3f}', 
                   color=colors[i % len(colors)], va='center', ha='left', fontsize=9)

    def _draw_zones(self, ax, zones, df):
        """Draw support and resistance zones"""
        for zone in zones:
            color = '#ff6b6b' if zone['type'] == 'resistance' else '#51cf66'
            alpha = min(0.2 + (zone['score'] / 10) * 0.3, 0.5)
            
            # Draw zone as horizontal rectangle
            zone_height = zone['price'] * 0.01  # 1% height
            ax.axhspan(zone['price'] - zone_height/2, 
                       zone['price'] + zone_height/2,
                       color=color, alpha=alpha, 
                       label=f"{zone['type'].title()} (Score: {zone['score']:.1f})")

    def create_signal_chart(self, df: pd.DataFrame, token_data: Dict, signal_data: Dict) -> Optional[bytes]:
        """Create candlestick chart with all indicators"""
        if df.empty or len(df) < 10:
            return None

        try:
            fig, ax = plt.subplots(figsize=(16, 9))
            fig.patch.set_facecolor('#1e1e1e')
            ax.set_facecolor('#1e1e1e')

            # Convert timestamps to datetime
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
            
            # Draw candlesticks
            self._draw_candlesticks(ax, df)
            
            # Add moving averages
            if len(df) >= 20:
                self._add_moving_averages(ax, df)

            # Draw support/resistance zones
            if signal_data.get('zones'):
                self._draw_zones(ax, signal_data['zones'], df)

            # Calculate and draw Fibonacci levels
            fib_retracement_data = self._calculate_fibonacci_retracement(df)
            fib_extension_data = self._calculate_fibonacci_extension(df)
            self._draw_fibonacci_retracement(ax, fib_retracement_data)
            self._draw_fibonacci_extension(ax, fib_extension_data)

            # Add watermark and format
            self._add_watermark(fig)
            self._format_chart(ax, token_data, signal_data, df)

            # Save to bytes
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', facecolor='#1e1e1e', 
                       bbox_inches='tight', dpi=120)
            buffer.seek(0)
            plt.close(fig)

            return buffer.getvalue()
            
        except Exception as e:
            print(f"Chart generation error: {e}")
            return None

    def _draw_candlesticks(self, ax, df):
        """Draw candlestick chart using correct datetime on X-axis"""
        for _, row in df.iterrows():
            color = '#00ff88' if row['close'] >= row['open'] else '#ff4444'
        
            # High-low line
            ax.plot([row['datetime'], row['datetime']], [row['low'], row['high']], 
                   color=color, linewidth=1.5, alpha=0.8)
        
            # Calculate candle width more safely
            try:
                if len(df) > 1:
                    time_diff_seconds = (df['datetime'].iloc[1] - df['datetime'].iloc[0]).total_seconds()
                    width_days = time_diff_seconds / 86400.0 * 0.8  # Convert to days
                else:
                    width_days = 1/24 * 0.8  # 1 hour default
            
                # Body rectangle
                body_height = abs(row['close'] - row['open'])
                body_bottom = min(row['open'], row['close'])

                if body_height > 0:
                    rect_start_num = mdates.date2num(row['datetime']) - width_days/2
                
                    ax.add_patch(plt.Rectangle((rect_start_num, body_bottom), 
                                             width_days, body_height,
                                             facecolor=color, alpha=0.8))
            except Exception as e:
                # Skip this candle if there's an error
                continue

    def _add_moving_averages(self, ax, df):
        """Add EMA lines using datetime on X-axis"""
        if len(df) >= 20:
            df['ema20'] = df['close'].ewm(span=20).mean()
            ax.plot(df['datetime'], df['ema20'],
                   color='#ffa726', linewidth=1.5, alpha=0.7, label='EMA 20')

        if len(df) >= 50:
            df['ema50'] = df['close'].ewm(span=50).mean()
            ax.plot(df['datetime'], df['ema50'],
                   color='#42a5f5', linewidth=1.5, alpha=0.7, label='EMA 50')

    def _add_watermark(self, fig):
        """Add a centered, semi-transparent watermark"""
        fig.text(0.5, 0.5, 'NarmoonAI',
                 fontsize=80,
                 color='gray',
                 ha='center',
                 va='center',
                 alpha=0.1,
                 fontweight='bold')

    def _format_chart(self, ax, token_data, signal_data, df):
        """
        نسخه اصلاح‌شده برای فرمت‌بندی چارت با محورهای هوشمند.
        این تابع مشکل فضای خالی بالای چارت و محور زمان را حل می‌کند.
        """
        ax.set_title(f"{token_data['token']} - Signal: {signal_data['signal_type'].replace('_', ' ').title()}",
                    color='white', fontsize=16, fontweight='bold')

        ax.grid(True, alpha=0.2, color='#555555')
        ax.set_ylabel('Price ($)', color='white')

        # --- بخش کلیدی ۱: اصلاح محدوده محور Y (رفع فضای خالی) ---
        # به جای استفاده از محدوده خودکار، محدوده را بر اساس کندل‌ها تنظیم می‌کنیم
        visible_df = df.iloc[-100:] # تمرکز روی ۱۰۰ کندل آخر برای تعیین محدوده
        min_price = visible_df['low'].min()
        max_price = visible_df['high'].max()
        padding = (max_price - min_price) * 0.05  # اضافه کردن ۵٪ حاشیه در بالا و پایین

        ax.set_ylim(min_price - padding, max_price + padding)

        # --- بخش کلیدی ۲: اصلاح و هوشمندسازی محور X (زمان) ---
        total_duration = df['datetime'].iloc[-1] - df['datetime'].iloc[0]

        if total_duration < timedelta(days=2):
            # برای تایم‌فریم‌های کوتاه (کمتر از ۲ روز)
            locator = mdates.AutoDateLocator(minticks=5, maxticks=8)
            formatter = mdates.DateFormatter('%H:%M\n%d-%b')
        elif total_duration < timedelta(days=15):
            # برای تایم‌فریم‌های متوسط (بین ۲ تا ۱۵ روز)
            locator = mdates.DayLocator(interval=max(1, int(total_duration.days / 7)))
            formatter = mdates.DateFormatter('%d-%b')
        else:
            # برای تایم‌فریم‌های بلند (بیش از ۱۵ روز)
            locator = mdates.AutoDateLocator(minticks=4, maxticks=7)
            formatter = mdates.DateFormatter('%b-%Y')
            
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
        
        # --- بقیه تنظیمات ---
        ax.tick_params(axis='both', colors='white', labelsize=10)
        for spine in ax.spines.values():
            spine.set_edgecolor('#555555')
            
        time_range = df['datetime'].iloc[-1] - df['datetime'].iloc[0]
        right_margin = time_range * 0.1 # افزایش حاشیه سمت راست برای نمایش بهتر لیبل‌ها
        
        ax.set_xlim(df['datetime'].iloc[0], df['datetime'].iloc[-1] + right_margin)
        
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position('right')

        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc='upper left', framealpha=0.3, fontsize=9)

chart_generator = ChartGenerator()
