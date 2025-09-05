from app.database.session import get_db
from app.database.models import Token
from sqlalchemy import select, update
from datetime import datetime, timedelta, timezone
import logging
from app.scanner.timeframe_selector import get_dynamic_timeframe # Import the helper function

logger = logging.getLogger(__name__)

# Define token states
STATE_WATCHING = "WATCHING"
STATE_SIGNALED = "SIGNALED"
STATE_COOLDOWN = "COOLDOWN"

class TokenStateService:
    def _get_dynamic_cooldown(self, launch_date: datetime) -> timedelta:
        """
        Calculates the cooldown duration based on the token's age.
        This logic is synchronized with the timeframe selector.
        """
        age = datetime.now(timezone.utc) - launch_date
        
        if age < timedelta(hours=12):       # Corresponds to 1m, 5m charts
            return timedelta(minutes=15)
        elif age < timedelta(days=1):       # Corresponds to 15m chart
            return timedelta(minutes=30)
        elif age < timedelta(days=3):       # Corresponds to 1h chart
            return timedelta(hours=2)
        elif age < timedelta(days=7):       # Corresponds to 4h chart
            return timedelta(hours=6)
        else:                               # Corresponds to 12h, 1d charts
            return timedelta(hours=12)

    async def can_send_signal(self, token_address: str) -> bool:
        """
        Checks if a signal can be sent for a token based on its current state.
        A signal can only be sent if the token is in the 'WATCHING' state.
        """
        async for session in get_db():
            await self.reset_cooled_down_tokens(session)

            result = await session.execute(
                select(Token).where(Token.address == token_address)
            )
            token = result.scalar_one_or_none()

            if not token:
                return True
            
            return token.state == STATE_WATCHING

    async def record_signal_sent(self, token_address: str, signal_price: float, session):
        """
        Updates the token's state to SIGNALED and sets the cooldown period.
        """
        stmt = (
            update(Token)
            .where(Token.address == token_address)
            .values(
                state=STATE_SIGNALED,
                last_signal_price=signal_price,
                last_state_change=datetime.utcnow()
            )
        )
        await session.execute(stmt)
        logger.info(f"🧠 Token state updated to SIGNALED for {token_address}")

    async def reset_cooled_down_tokens(self, session):
        """
        Finds tokens in SIGNALED/COOLDOWN state whose dynamic cooldown period has passed
        and resets their state to WATCHING.
        """
        tokens_in_cooldown_result = await session.execute(
            select(Token).where(Token.state.in_([STATE_SIGNALED, STATE_COOLDOWN]))
        )
        tokens_in_cooldown = tokens_in_cooldown_result.scalars().all()
        
        tokens_to_reset_ids = []
        now = datetime.utcnow()

        for token in tokens_in_cooldown:
            # We need timezone-aware datetime for launch_date if it's naive
            launch_date_aware = token.launch_date.replace(tzinfo=timezone.utc)
            cooldown_duration = self._get_dynamic_cooldown(launch_date_aware)
            
            if token.last_state_change and now > token.last_state_change + cooldown_duration:
                tokens_to_reset_ids.append(token.id)
        
        if tokens_to_reset_ids:
            stmt = (
                update(Token)
                .where(Token.id.in_(tokens_to_reset_ids))
                .values(
                    state=STATE_WATCHING,
                    last_state_change=now
                )
            )
            await session.execute(stmt)
            await session.commit()
            logger.info(f"🔄 Reset state to WATCHING for {len(tokens_to_reset_ids)} tokens.")


token_state_service = TokenStateService()
