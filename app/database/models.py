from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, BigInteger, ForeignKey, Text
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

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
