import httpx
import pandas as pd
from typing import Optional, List, Dict
import asyncio
import hashlib
from app.services.redis_client import redis_client
import logging

logger = logging.getLogger(__name__)

class DataProvider:
    def __init__(self):
        self.base_url = "https://api.geckoterminal.com/api/v2"
        self.max_retries = 5
        self.initial_backoff = 1.0

    async def _api_request_handler(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Handles API requests with caching, rate limiting, and exponential backoff.
        """
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url, params=params)

                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 429:
                        backoff_time = self.initial_backoff * (2 ** attempt)
                        logger.warning(f"Rate limit hit for {url}. Retrying in {backoff_time:.2f} seconds...")
                        await asyncio.sleep(backoff_time)
                    else:
                        logger.error(f"API Error: {response.status_code} for URL {url}. Response: {response.text[:200]}")
                        return None
            except httpx.RequestError as e:
                logger.error(f"HTTP request failed for {url}: {e}")
                if attempt >= self.max_retries - 1:
                    return None
                await asyncio.sleep(self.initial_backoff * (2 ** attempt))

        logger.error(f"Failed to fetch data from {url} after {self.max_retries} retries.")
        return None

    def _generate_cache_key(self, endpoint: str, params: dict) -> str:
        """Generate unique cache key for API request"""
        cache_string = f"{endpoint}_{str(sorted(params.items()))}"
        return hashlib.md5(cache_string.encode()).hexdigest()

    async def fetch_trending_tokens(self, limit: int = 50) -> List[Dict]:
        """Fetch trending tokens with Redis caching"""
        url = f"{self.base_url}/networks/solana/trending_pools"
        params = {
            'include': 'base_token,quote_token',
            'limit': str(limit)
        }

        cache_key = self._generate_cache_key("trending_pools", params)
        cached_data = await redis_client.get(cache_key)
        if cached_data:
            return cached_data

        data = await self._api_request_handler(url, params=params)
        if data:
            processed_data = self._process_trending_data(data)
            await redis_client.set(cache_key, processed_data, ttl=60)
            return processed_data
        return []

    async def fetch_ohlcv(self, pool_id: str, timeframe: str = "hour",
                         aggregate: str = "1", limit: int = 200) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data with Redis caching"""
        network, pool_address = pool_id.split('_')
        url = f"{self.base_url}/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}"
        params = {
            'aggregate': aggregate,
            'limit': str(limit)
        }

        cache_key = self._generate_cache_key(f"ohlcv_{pool_id}_{timeframe}", params)
        cached_data = await redis_client.get(cache_key)
        if cached_data:
            return pd.DataFrame(cached_data)

        data = await self._api_request_handler(url, params=params)
        if data:
            df = self._process_ohlcv_data(data)
            if not df.empty:
                await redis_client.set(cache_key, df.to_dict('records'), ttl=120)
            return df
        return None

    def _process_trending_data(self, data: Dict) -> List[Dict]:
        """Process trending data response"""
        tokens = []
        pools = data.get('data', [])
        included = data.get('included', [])

        token_map = {item.get('id'): item.get('attributes', {})
                     for item in included if item.get('type') == 'token'}

        for pool in pools:
            try:
                attributes = pool.get('attributes', {})
                relationships = pool.get('relationships', {})

                base_token_rel = relationships.get('base_token', {}).get('data', {})
                base_token_id = base_token_rel.get('id', '')
                token_attrs = token_map.get(base_token_id, {})

                token_address = token_attrs.get('address')
                base_token_price = attributes.get('base_token_price_usd')

                if not token_address or not base_token_price:
                    continue

                volume_24h = float(attributes.get('volume_usd', {}).get('h24', 0))

                token_data = {
                    'address': token_address,
                    'symbol': token_attrs.get('symbol', 'Unknown'),
                    'pool_id': pool.get('id', ''),
                    'volume_24h': volume_24h,
                    'price_usd': float(base_token_price)
                }
                tokens.append(token_data)
            except (ValueError, TypeError, KeyError):
                continue

        return tokens

    def _process_ohlcv_data(self, data: Dict) -> pd.DataFrame:
        """Process OHLCV data response"""
        ohlcv_list = data.get('data', {}).get('attributes', {}).get('ohlcv_list', [])

        df_data = []
        for candle in ohlcv_list:
            timestamp, open_price, high, low, close, volume = candle
            df_data.append({
                'timestamp': timestamp,
                'open': float(open_price),
                'high': float(high),
                'low': float(low),
                'close': float(close),
                'volume': float(volume)
            })

        df = pd.DataFrame(df_data)
        if not df.empty:
            df = df.sort_values('timestamp').reset_index(drop=True)

        return df

    async def fetch_pool_details(self, pool_id: str) -> Optional[Dict]:
        """
        Fetches full pool details including creation date.
        This function intelligently caches results in Redis to avoid repeated requests.
        """
        network, pool_address = pool_id.split('_')
        url = f"{self.base_url}/networks/{network}/pools/{pool_address}"

        cache_key = f"pool_details_{pool_id}"
        cached_data = await redis_client.get(cache_key)
        if cached_data:
            logger.info(f"Using cached pool details for {pool_id}")
            return cached_data

        logger.info(f"Fetching new pool details from API for {pool_id}")
        data = await self._api_request_handler(url)
        if data:
            attributes = data.get('data', {}).get('attributes', {})
            if attributes:
                await redis_client.set(cache_key, attributes, ttl=86400)
            return attributes
        return None

data_provider = DataProvider()
