from app.database.session import get_db
from app.database.models import Token # Changed from SignalHistory to Token
from sqlalchemy import select, update
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# --- NEW: Define token states and cooldown duration ---
STATE_WATCHING = "WATCHING"
STATE_SIGNALED = "SIGNALED"
STATE_COOLDOWN = "COOLDOWN"
COOLDOWN_HOURS = 12 # Cooldown duration increased to 12 hours

class TokenStateService:
    async def can_send_signal(self, token_address: str) -> bool:
        """
        Checks if a signal can be sent for a token based on its current state.
        A signal can only be sent if the token is in the 'WATCHING' state.
        """
        async for session in get_db():
            # First, check and reset any tokens that have passed their cooldown period
            await self._reset_cooled_down_tokens(session)

            result = await session.execute(
                select(Token).where(Token.address == token_address)
            )
            token = result.scalar_one_or_none()

            if not token:
                # If token is not in DB yet, it's considered new and watchable.
                return True
            
            # A signal can only be sent if the token is in the WATCHING state.
            return token.state == STATE_WATCHING

    async def record_signal_sent(self, token_address: str, signal_price: float):
        """
        Updates the token's state to SIGNALED and sets the cooldown period.
        """
        async for session in get_db():
            stmt = (
                update(Token)
                .where(Token.address == token_address)
                .values(
                    state=STATE_SIGNALED, # Change state to SIGNALED
                    last_signal_price=signal_price,
                    last_state_change=datetime.utcnow()
                )
            )
            await session.execute(stmt)
            await session.commit()
            logger.info(f"🧠 Token state updated to SIGNALED for {token_address}")

    async def _reset_cooled_down_tokens(self, session):
        """
        Finds tokens in SIGNALED or COOLDOWN state whose cooldown period has passed
        and resets their state to WATCHING.
        """
        cooldown_period = datetime.utcnow() - timedelta(hours=COOLDOWN_HOURS)
        stmt = (
            update(Token)
            .where(
                Token.state.in_([STATE_SIGNALED, STATE_COOLDOWN]),
                Token.last_state_change < cooldown_period
            )
            .values(
                state=STATE_WATCHING,
                last_state_change=datetime.utcnow()
            )
        )
        await session.execute(stmt)
        await session.commit()


# Rename the instance to reflect the new service
token_state_service = TokenStateService()
