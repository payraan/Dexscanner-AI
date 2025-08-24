import httpx
import pandas as pd
from typing import Optional, List, Dict
import asyncio

class DataProvider:
    def __init__(self):
        self.base_url = "https://api.geckoterminal.com/api/v2"
        
    async def fetch_trending_tokens(self, limit: int = 50) -> List[Dict]:
        """Fetch trending tokens from GeckoTerminal"""
        url = f"{self.base_url}/networks/solana/trending_pools"
        params = {
            'include': 'base_token,quote_token',
            'limit': str(limit)
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    return self._process_trending_data(data)
        except Exception as e:
            print(f"Error fetching trending tokens: {e}")
        return []
    
    async def fetch_ohlcv(self, pool_id: str, timeframe: str = "hour", 
                         aggregate: str = "1", limit: int = 200) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data for a pool"""
        network, pool_address = pool_id.split('_')
        url = f"{self.base_url}/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}"
        
        params = {
            'aggregate': aggregate,
            'limit': str(limit)
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    return self._process_ohlcv_data(data)
        except Exception as e:
            print(f"Error fetching OHLCV data: {e}")
        return None
    
    def _process_trending_data(self, data: Dict) -> List[Dict]:
        """Process trending data response"""
        tokens = []
        pools = data.get('data', [])
        included = data.get('included', [])
        
        # Create token map
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
            except (ValueError, TypeError, KeyError) as e:
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

data_provider = DataProvider()
