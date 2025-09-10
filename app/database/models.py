from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, BigInteger, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class User(Base):
   __tablename__ = 'users'
   
   id = Column(BigInteger, primary_key=True)
   is_subscribed = Column(Boolean, default=False)
   subscription_end_date = Column(DateTime)
   created_at = Column(DateTime, default=datetime.utcnow)

class Token(Base):
   __tablename__ = 'tokens'
   
   id = Column(Integer, primary_key=True)
   address = Column(String, unique=True, index=True, nullable=False)
   pool_id = Column(String, unique=True, nullable=False)
   symbol = Column(String, nullable=False)
   launch_date = Column(DateTime, nullable=False) 
     
   # --- فیلدهای جدید برای چرخه حیات و مدیریت وضعیت ---
   state = Column(String, default='WATCHING', index=True) # مقادیر: WATCHING, SIGNALED, COOLDOWN, INVALIDATED
   last_signal_price = Column(Float, nullable=True)
   last_state_change = Column(DateTime, default=datetime.utcnow)
   last_scan_price = Column(Float, nullable=True)
   message_id = Column(BigInteger, nullable=True)
   reply_count = Column(Integer, default=0)

   # --- پایان فیلدهای جدید ---

   health_status = Column(String, default='active')
   last_health_check = Column(DateTime)
   
   alerts = relationship("Alert", back_populates="token")

class Alert(Base):
   __tablename__ = 'alerts'
   
   id = Column(Integer, primary_key=True)
   token_id = Column(Integer, ForeignKey('tokens.id'), nullable=False)
   strategy = Column(String, nullable=False)
   price_at_alert = Column(Float)
   message_id = Column(BigInteger)
   chat_id = Column(BigInteger)
   timestamp = Column(DateTime, default=datetime.utcnow)
   
   token = relationship("Token", back_populates="alerts")

class SignalHistory(Base):
   __tablename__ = 'signal_history'
   
   id = Column(Integer, primary_key=True)
   token_address = Column(String, nullable=False)
   signal_type = Column(String, nullable=False)
   sent_at = Column(DateTime, default=datetime.utcnow)
   volume_24h = Column(Float)
   price = Column(Float)

class ZoneState(Base):
   __tablename__ = 'zone_states'
   
   id = Column(Integer, primary_key=True)
   token_address = Column(String, nullable=False)
   zone_price = Column(Float, nullable=False)
   current_state = Column(String, default='IDLE')
   last_signal_type = Column(String)
   last_signal_time = Column(DateTime)
   last_price = Column(Float)
   created_at = Column(DateTime, default=datetime.utcnow)
   updated_at = Column(DateTime, default=datetime.utcnow)

class FibonacciState(Base):
    __tablename__ = 'fibonacci_state'

    id = Column(Integer, primary_key=True)
    token_address = Column(String, nullable=False, index=True)
    timeframe = Column(String, nullable=False)
    high_point = Column(Float, nullable=False)
    low_point = Column(Float, nullable=False)
    high_point_timestamp = Column(DateTime, nullable=True)
    low_point_timestamp = Column(DateTime, nullable=True)
    target1_price = Column(Float)
    target2_price = Column(Float)
    target3_price = Column(Float)
    status = Column(String, default='ACTIVE')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint('token_address', 'timeframe', name='_token_timeframe_uc'),)

class SignalResult(Base):
    __tablename__ = 'signal_results'

    id = Column(Integer, primary_key=True)
    alert_id = Column(Integer, ForeignKey('alerts.id'), nullable=True, unique=True)
    token_address = Column(String, nullable=False, index=True)
    token_symbol = Column(String, nullable=True)
    
    signal_price = Column(Float, nullable=False)
    
    # --- فیلدهای بهبود یافته برای ردیابی عملکرد ---
    peak_price = Column(Float, nullable=True) # بالاترین قیمت پس از سیگنال
    peak_profit_percentage = Column(Float, default=0.0) # درصد سود در قله
    tracking_status = Column(String, default='TRACKING', index=True) # مقادیر: TRACKING, SUCCESS, FAILED, EXPIRED
    closed_at = Column(DateTime, nullable=True) # زمان بسته شدن ردیابی
    # --- پایان فیلدهای بهبود یافته ---

    # فیلد جدید برای ذخیره تایم‌فریم اولیه
    initial_timeframe = Column(String, nullable=True)

    before_chart_file_id = Column(String, nullable=False)
    composite_file_ids = Column(JSONB, nullable=True)

    is_rugged = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    captured_at = Column(DateTime, nullable=True) # این فیلد ممکن است در آینده با closed_at ترکیب شود

    alert = relationship("Alert")

class SmartMoneyWallet(Base):
    __tablename__ = 'smart_money_wallets'
    
    id = Column(Integer, primary_key=True)
    address = Column(String, unique=True, nullable=False, index=True)
    chain = Column(String, default='solana')
    success_rate = Column(Float, default=0.0)
    total_profits = Column(Float, default=0.0)
    notes = Column(Text)
    last_seen = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

# --- مدل جدید برای لیست سیاه ---
class Blacklist(Base):
    __tablename__ = 'blacklist'

    id = Column(Integer, primary_key=True)
    token_address = Column(String, unique=True, nullable=False, index=True)
    reason = Column(String, nullable=True) # e.g., "RUG_PULL", "HONEYPOT"
    added_at = Column(DateTime, default=datetime.utcnow)
# --- پایان مدل جدید ---
