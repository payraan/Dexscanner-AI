from app.database.session import get_db
from app.database.models import Token
from sqlalchemy import select
from datetime import datetime
from typing import List, Dict

class TokenService:
    async def store_tokens(self, tokens: List[Dict]):
        """Store/update tokens in database"""
        async for session in get_db():
            for token_data in tokens:
                # Check if token exists
                result = await session.execute(
                    select(Token).where(Token.address == token_data['address'])
                )
                existing_token = result.scalar_one_or_none()
                
                if not existing_token:
                    # Create new token with estimated launch date
                    new_token = Token(
                        address=token_data['address'],
                        pool_id=token_data['pool_id'],
                        symbol=token_data['symbol'],
                        launch_date=datetime.utcnow(),  # Estimate for now
                        health_status='active'
                    )
                    session.add(new_token)
            
            await session.commit()

token_service = TokenService()
