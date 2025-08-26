from app.database.session import get_db
from app.database.models import Token
from app.scanner.data_provider import data_provider
from app.scanner.token_health import token_health_checker
from sqlalchemy import select
from datetime import datetime
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

class TokenService:
    async def store_tokens(self, tokens: List[Dict]):
        """Store/update tokens in database"""
        async for session in get_db():
            for token_data in tokens:
                result = await session.execute(
                    select(Token).where(Token.address == token_data['address'])
                )
                existing_token = result.scalar_one_or_none()
                
                if not existing_token:
                    new_token = Token(
                        address=token_data['address'],
                        pool_id=token_data['pool_id'],
                        symbol=token_data['symbol'],
                        launch_date=datetime.utcnow(),
                        health_status='active'
                    )
                    session.add(new_token)
            
            await session.commit()

    async def store_tokens_with_health(self, tokens: List[Dict]):
        """Store/update tokens in database with health check"""
        async for session in get_db():
            for token_data in tokens:
                # Check if token exists
                result = await session.execute(
                    select(Token).where(Token.address == token_data['address'])
                )
                existing_token = result.scalar_one_or_none()
                
                # Get health data for token
                df = await data_provider.fetch_ohlcv(
                    token_data['pool_id'],
                    timeframe="hour",
                    aggregate="1",
                    limit=50
                )
                health_status = await token_health_checker.check_token_health(df, token_data)
                
                if existing_token:
                    # Update existing token health
                    existing_token.health_status = health_status
                    existing_token.last_health_check = datetime.utcnow()
                else:
                    # Create new token
                    new_token = Token(
                        address=token_data['address'],
                        pool_id=token_data['pool_id'],
                        symbol=token_data['symbol'],
                        launch_date=datetime.utcnow(),
                        health_status=health_status,
                        last_health_check=datetime.utcnow()
                    )
                    session.add(new_token)
            
            await session.commit()

token_service = TokenService()
