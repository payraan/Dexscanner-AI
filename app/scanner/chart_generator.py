import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import io
from typing import Dict, Optional
import asyncio

class ChartGenerator:
    def __init__(self):
        plt.style.use('dark_background')

    def _calculate_fibonacci_retracement(self, df: pd.DataFrame):
        """محاسبه سطوح فیبوناچی برگشتی"""
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
        """محاسبه سطوح فیبوناچی برای تارگت‌ها"""
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
        """رسم خطوط فیبوناچی برگشتی با لیبل"""
        if not fib_data:
            return
            
        colors = ['#2ecc71', '#ff9f43', '#00d2d3', '#5f27cd', '#54a0ff', '#ff9ff3', '#e74c3c']
        
        for i, (level, price) in enumerate(fib_data['levels'].items()):
            ax.axhline(y=price, color=colors[i % len(colors)], linestyle='--', 
                      linewidth=1, alpha=0.6)
            
            # اضافه کردن لیبل در سمت چپ با قیمت
            ax.text(0.01, price, f'Fib {level:.3f}: ${price:.6f}', 
                   transform=ax.get_yaxis_transform(),
                   color=colors[i % len(colors)], va='center', fontsize=8,
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.7))

    def _draw_fibonacci_extension(self, ax, fib_ext_data, df):
        """رسم خطوط فیبوناچی extension با لیبل"""
        if not fib_ext_data:
            return
            
        current_price = df['close'].iloc[-1]
        max_visible_price = max(df['high'].max() * 1.5, current_price * 2.0)
            
        colors = ['#4caf50', '#8bc34a']
        
        for i, (level, price) in enumerate(fib_ext_data['levels'].items()):
            if price < max_visible_price:
                ax.axhline(y=price, color=colors[i % len(colors)], linestyle=':', 
                          linewidth=1.2, alpha=0.7)
                
                # اضافه کردن لیبل در سمت چپ
                ax.text(0.01, price, f'Target {level:.3f}: ${price:.6f}', 
                       transform=ax.get_yaxis_transform(),
                       color=colors[i % len(colors)], va='center', fontsize=8,
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.7))

    def _draw_zones(self, ax, zones):
        """رسم support/resistance zones"""
        for zone in zones:
            color = '#ff6b6b' if zone['type'] == 'resistance' else '#51cf66'
            alpha = min(0.2 + (zone['score'] / 10) * 0.3, 0.5)
            
            zone_height = zone['price'] * 0.01
            ax.axhspan(zone['price'] - zone_height/2, 
                      zone['price'] + zone_height/2,
                      color=color, alpha=alpha)

    def create_signal_chart(self, df: pd.DataFrame, token_data: Dict, signal_data: Dict) -> Optional[bytes]:
        """ساخت چارت حرفه‌ای با استایل ربات قدیمی"""
        if df.empty or len(df) < 10:
            return None

        try:
            fig, ax = plt.subplots(figsize=(16, 9))
            fig.patch.set_facecolor('#1a1a1a')
            ax.set_facecolor('#1a1a1a')

            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
            
            self._draw_candlesticks(ax, df)
            self._add_moving_averages(ax, df)

            if signal_data.get('zones'):
                self._draw_zones(ax, signal_data['zones'])

            # رسم فیبوناچی‌ها
            fib_retracement_data = self._calculate_fibonacci_retracement(df)            
            fib_extension_data = self._calculate_fibonacci_extension(df)
            self._draw_fibonacci_retracement(ax, fib_retracement_data)
            self._draw_fibonacci_extension(ax, fib_extension_data, df)

            # اضافه کردن watermark
            self._add_watermark(ax)
            
            # اضافه کردن price box
            self._add_price_box(ax, df)
            
            self._format_chart(ax, token_data, signal_data, df)

            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', facecolor='#1a1a1a', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            plt.close(fig)

            return buffer.getvalue()
            
        except Exception as e:
            print(f"Chart generation error: {e}")
            return None

    def _draw_candlesticks(self, ax, df):
        """رسم کندل‌ها با عرض مناسب"""
        for i, row in df.iterrows():
            color = '#00ff88' if row['close'] >= row['open'] else '#ff4444'
            
            ax.plot([row['datetime'], row['datetime']], [row['low'], row['high']], 
                   color=color, linewidth=1.5, alpha=0.9)
            
            # محاسبه عرض کندل
            if i < len(df) - 1:
                next_row = df.iloc[i + 1]
                time_diff = next_row['datetime'] - row['datetime']
            elif i > 0:
                prev_row = df.iloc[i - 1]
                time_diff = row['datetime'] - prev_row['datetime']
            else:
                time_diff = timedelta(hours=1)
                
            width_days = time_diff.total_seconds() / 86400.0 * 0.7
            
            body_height = abs(row['close'] - row['open'])
            body_bottom = min(row['open'], row['close'])

            if body_height > 0:
                rect_start_num = mdates.date2num(row['datetime']) - width_days/2
                ax.add_patch(plt.Rectangle((rect_start_num, body_bottom), 
                                         width_days, body_height,
                                         facecolor=color, alpha=0.9))

    def _add_moving_averages(self, ax, df):
        """اضافه کردن EMA"""
        if len(df) >= 20:
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            ax.plot(df['datetime'], df['ema20'],
                   color='#ffa726', linewidth=2, alpha=0.8)

        if len(df) >= 50:
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            ax.plot(df['datetime'], df['ema50'],
                   color='#42a5f5', linewidth=2, alpha=0.8)

    def _add_watermark(self, ax):
        """اضافه کردن watermark در گوشه پایین راست"""
        ax.text(0.98, 0.02, 'NarmoonAI',
               transform=ax.transAxes,
               fontsize=18,
               color='gray',
               alpha=0.3,
               ha='right',
               va='bottom',
               style='italic')

    def _add_price_box(self, ax, df):
        """اضافه کردن کادر قیمت فعلی"""
        current_price = df['close'].iloc[-1]
        ax.text(0.98, 0.08, f'Price: ${current_price:.8f}',
               transform=ax.transAxes,
               fontsize=12,
               color='white',
               ha='right',
               va='bottom',
               bbox=dict(boxstyle='round,pad=0.5', facecolor='black', alpha=0.8))

    def _format_chart(self, ax, token_data, signal_data, df):
        """فرمت نهایی چارت با محور زمان درست"""
        # عنوان
        timeframe_str = signal_data.get('timeframe', '')
        ax.set_title(f"{token_data['token']} - {timeframe_str} Chart",
                    color='white', fontsize=14, fontweight='bold', loc='left')

        ax.grid(True, alpha=0.15, color='#444444')
        
        # محور Y در سمت راست
        ax.yaxis.tick_right()
        ax.yaxis.set_label_position('right')
        ax.set_ylabel('Price (USDT)', color='white', fontsize=10)

        # تنظیم محدوده Y
        visible_high = df['high'].max()
        visible_low = df['low'].min()
        price_range = visible_high - visible_low
        
        padding = price_range * 0.1
        ax.set_ylim(visible_low - padding, visible_high + padding)

        # تنظیم محور X (زمان)
        total_duration = df['datetime'].iloc[-1] - df['datetime'].iloc[0]
        
        # انتخاب فرمت مناسب برای محور زمان
        if total_duration < timedelta(hours=12):
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            ax.xaxis.set_minor_locator(mdates.HourLocator())
        elif total_duration < timedelta(days=1):
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        elif total_duration < timedelta(days=3):
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        elif total_duration < timedelta(days=7):
            ax.xaxis.set_major_locator(mdates.DayLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        elif total_duration < timedelta(days=30):
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        else:
            ax.xaxis.set_major_locator(mdates.WeekLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        
        # چرخش لیبل‌های محور X
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, ha='center')
        
        ax.tick_params(axis='both', colors='#888888', labelsize=9)
        
        # حاشیه‌ها
        for spine in ax.spines.values():
            spine.set_edgecolor('#333333')
            spine.set_linewidth(1)
        
        # محدوده X
        ax.set_xlim(df['datetime'].iloc[0], df['datetime'].iloc[-1])

chart_generator = ChartGenerator()
