import redis.asyncio as redis
import json
import logging
from typing import Optional, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisClient:
   def __init__(self):
       self.redis_client = None
       self.connected = False

   async def connect(self):
       """Connect to Redis"""
       try:
           redis_url = getattr(settings, 'REDIS_URL', None)
           if redis_url:
               self.redis_client = redis.from_url(redis_url)
               await self.redis_client.ping()
               self.connected = True
               logger.info("✅ Redis connected successfully")
           else:
               logger.warning("⚠️ Redis URL not configured")
       except Exception as e:
           logger.error(f"❌ Redis connection failed: {e}")
           self.connected = False

   async def get(self, key: str) -> Optional[Any]:
       """Get cached data"""
       if not self.connected:
           return None
       try:
           data = await self.redis_client.get(key)
           return json.loads(data) if data else None
       except Exception as e:
           logger.error(f"Redis get error: {e}")
           return None

   async def set(self, key: str, value: Any, ttl: int = 120):
       """Cache data with TTL"""
       if not self.connected:
           return False
       try:
           await self.redis_client.set(key, json.dumps(value), ex=ttl)
           return True
       except Exception as e:
           logger.error(f"Redis set error: {e}")
           return False

redis_client = RedisClient()
