import httpx
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

from app.core.config import settings
from app.services.redis_client import redis_client

logger = logging.getLogger(__name__)

class BitqueryService:
   def __init__(self):
       self.api_url = "https://streaming.bitquery.io/eap"
       self.api_key = settings.BITQUERY_API_KEY
       
   async def execute_query(self, query: str, variables: Dict = None) -> Optional[Dict]:
       """Execute GraphQL query to Bitquery V2"""
       headers = {
           "Authorization": f"Bearer {self.api_key}",
           "Content-Type": "application/json"
       }
       
       payload = {
           "query": query,
           "variables": variables or {}
       }
       
       try:
           async with httpx.AsyncClient(timeout=30.0) as client:
               response = await client.post(self.api_url, json=payload, headers=headers)
               if response.status_code == 200:
                   data = response.json()
                   if 'errors' in data:
                       logger.error(f"GraphQL errors: {data['errors']}")
                       return None
                   return data
               logger.error(f"Bitquery error: {response.status_code} - {response.text}")
               return None
       except Exception as e:
           logger.error(f"Request error: {e}")
           return None

   async def get_holder_stats(self, token_address: str) -> Optional[Dict]:
       """Get holder statistics for a token"""
       cache_key = f"holder_stats_{token_address}"
       cached = await redis_client.get(cache_key)
       if cached:
           return cached
       
       query = """
       query GetSupplyAndTopHolders($token: String!) {
         tokenSupply: Solana(network: solana) {
           TokenSupplyUpdates(
             where: {TokenSupplyUpdate: {Currency: {MintAddress: {is: $token}}}}
             limit: {count: 1}
             orderBy: {descending: Block_Time}
           ) {
             TokenSupplyUpdate {
               PostBalance
             }
           }
         }
         holderStats: Solana(network: solana, aggregates: yes) {
           BalanceUpdates(
             limit: {count: 10}
             orderBy: {descendingByField: "BalanceUpdate_Holding_maximum"}
             where: {
               BalanceUpdate: {Currency: {MintAddress: {is: $token}}}
               Transaction: {Result: {Success: true}}
             }
           ) {
             BalanceUpdate {
               Account {
                 Address
               }
               Holding: PostBalance(maximum: Block_Slot, selectWhere: {gt: "0"})
             }
           }
         }
       }
       """
       
       variables = {"token": token_address}
       result = await self.execute_query(query, variables)
       
       if result and 'data' in result:
           stats = self._process_holder_stats(result['data'])
           if stats:
               await redis_client.set(cache_key, stats, ttl=300)
           return stats
       return None

   async def get_total_holders(self, token_address: str) -> Optional[int]:
       """Get total number of ACTIVE holders (with balance > 0)"""
       cache_key = f"total_holders_{token_address}"
       cached = await redis_client.get(cache_key)
       if cached:
           return cached
       
       query = """
       query GetActiveHolders($token: String!) {
         Solana(aggregates: yes) {
           BalanceUpdates(
             where: {
               BalanceUpdate: {
                 Currency: {MintAddress: {is: $token}}
                 PostBalance: {gt: "0"}
               }
               Transaction: {Result: {Success: true}}
             }
           ) {
             activeHolders: uniq(of: BalanceUpdate_Account_Address)
           }
         }
       }
       """
       
       variables = {"token": token_address}
       result = await self.execute_query(query, variables)
       
       if result and 'data' in result:
           try:
               balance_updates = result['data']['Solana']['BalanceUpdates']
               if balance_updates and len(balance_updates) > 0:
                   total = balance_updates[0]['activeHolders']
                   await redis_client.set(cache_key, total, ttl=300)
                   return total
           except Exception as e:
               logger.error(f"Error getting total holders: {e}")
       return None
   
   def _process_holder_stats(self, data: Dict) -> Optional[Dict]:
       """Process holder statistics from query result"""
       try:
           # Get top holders
           holders_data = data.get('holderStats', {}).get('BalanceUpdates', [])
           if not holders_data:
               logger.error("No holder data found")
               return None
           
           top_10_balance = 0
           for holder in holders_data:
               holding = holder.get('BalanceUpdate', {}).get('Holding')
               if holding:
                   top_10_balance += float(holding)
           
           # Get total supply
           total_supply = 0
           supply_data = data.get('tokenSupply', {}).get('TokenSupplyUpdates', [])
           if supply_data:
               supply_update = supply_data[0].get('TokenSupplyUpdate', {})
               if supply_update and 'PostBalance' in supply_update:
                   total_supply = float(supply_update['PostBalance'])
           
           # If no supply, estimate
           if total_supply == 0:
               total_supply = top_10_balance * 4
           
           concentration = (top_10_balance / total_supply * 100) if total_supply > 0 else 0
           
           return {
               'total_supply': total_supply,
               'top_10_balance': top_10_balance,
               'top_10_concentration': round(concentration, 2),
               'distribution_score': max(0, 100 - concentration)
           }
       except Exception as e:
           logger.error(f"Error processing holder stats: {e}", exc_info=True)
           return None

   async def get_liquidity_stats(self, token_address: str) -> Optional[Dict]:
       """Get liquidity statistics for a token"""
       cache_key = f"liquidity_stats_{token_address}"
       cached = await redis_client.get(cache_key)
       if cached:
           return cached
       
       yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
       
       query = """
       query LiquidityAnalyzer($tokenAddress: String!, $yesterday: DateTime!) {
         Solana(network: solana) {
           netFlow24h: DEXTradeByTokens(
             where: {
               Trade: {Currency: {MintAddress: {is: $tokenAddress}}},
               Block: {Time: {since: $yesterday}},
               Transaction: {Result: {Success: true}}
             }
           ) {
             buy_total_usd: sum(of: Trade_Side_AmountInUSD, if: {Trade: {Side: {Type: {is: buy}}}})
             sell_total_usd: sum(of: Trade_Side_AmountInUSD, if: {Trade: {Side: {Type: {is: sell}}}})
           }
           liquidityAsBase: DEXPools(
             where: {
               Pool: {Market: {BaseCurrency: {MintAddress: {is: $tokenAddress}}}},
               Transaction: {Result: {Success: true}}
             }
             orderBy: {descending: Block_Time}
             limit: {count: 1}
           ) {
             Pool {
               Base { base_usd: PostAmountInUSD(maximum: Block_Slot) }
               Quote { quote_usd: PostAmountInUSD(maximum: Block_Slot) }
             }
           }
           liquidityAsQuote: DEXPools(
             where: {
               Pool: {Market: {QuoteCurrency: {MintAddress: {is: $tokenAddress}}}},
               Transaction: {Result: {Success: true}}
             }
             orderBy: {descending: Block_Time}
             limit: {count: 1}
           ) {
             Pool {
               Base { base_usd: PostAmountInUSD(maximum: Block_Slot) }
               Quote { quote_usd: PostAmountInUSD(maximum: Block_Slot) }
             }
           }
           liquidityInstructions24h: Instructions(
             where: {
               Instruction: {Program: {Address: {in: [
                 "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
                 "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
               ]}}}
               Block: {Time: {since: $yesterday}}
               Transaction: {Result: {Success: true}}
             }
           ) {
             addLiquidityCount24h: count(
               if: {Instruction: {Program: {Method: {in: ["addLiquidity", "increaseLiquidity"]}}}}
             )
             removeLiquidityCount24h: count(
               if: {Instruction: {Program: {Method: {in: ["removeLiquidity", "decreaseLiquidity"]}}}}
             )
           }
         }
       }
       """

       variables = {"tokenAddress": token_address, "yesterday": yesterday}
       result = await self.execute_query(query, variables)
       
       if result and 'data' in result:
           stats = self._process_liquidity_stats(result['data'])
           if stats:
               await redis_client.set(cache_key, stats, ttl=600)
           return stats
       return None

   def _process_liquidity_stats(self, data: Dict) -> Optional[Dict]:
       """Process liquidity statistics from query result"""
       try:
           solana_data = data.get('Solana', {})

           # Process Net Flow
           net_flow_data = solana_data.get('netFlow24h', [])
           total_buy_usd = sum(float(item.get('buy_total_usd', 0) or 0) for item in net_flow_data)
           total_sell_usd = sum(float(item.get('sell_total_usd', 0) or 0) for item in net_flow_data)
           net_flow = total_buy_usd - total_sell_usd

           # Process Total Liquidity
           liquidity_pool = solana_data.get('liquidityAsBase', []) or solana_data.get('liquidityAsQuote', [])
           total_liquidity_usd = 0
           if liquidity_pool:
               pool_data = liquidity_pool[0].get('Pool', {})
               base_usd = float(pool_data.get('Base', {}).get('base_usd', 0) or 0)
               quote_usd = float(pool_data.get('Quote', {}).get('quote_usd', 0) or 0)
               total_liquidity_usd = base_usd + quote_usd

           # Process Liquidity Transaction Counts
           instructions_data = solana_data.get('liquidityInstructions24h', [{}])[0] if solana_data.get('liquidityInstructions24h') else {}
           add_count = int(instructions_data.get('addLiquidityCount24h', 0) or 0)
           remove_count = int(instructions_data.get('removeLiquidityCount24h', 0) or 0)
           
           stability_ratio = add_count / (remove_count + 1)

           return {
               'net_flow_24h_usd': round(net_flow, 2),
               'total_liquidity_usd': round(total_liquidity_usd, 2),
               'add_liquidity_count_24h': add_count,
               'remove_liquidity_count_24h': remove_count,
               'liquidity_stability_ratio': round(stability_ratio, 2)
           }
       except Exception as e:
           logger.error(f"Error processing liquidity stats: {e}")
           return None

bitquery_service = BitqueryService()
