import logging
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from config import Config

logger = logging.getLogger(__name__)


class SupabaseDB:
    """Supabase database client wrapper"""

    def __init__(self):
        self.client: Client = create_client(
            Config.SUPABASE_URL,
            Config.SUPABASE_KEY
        )
        self.service_client: Client = create_client(
            Config.SUPABASE_URL,
            Config.SUPABASE_SERVICE_KEY
        ) if Config.SUPABASE_SERVICE_KEY else None

    def get_user_email(self, user_id: str) -> Optional[str]:
        """Get user email from Supabase Auth"""
        try:
            if not self.service_client:
                logger.error("Service client not available")
                return None

            # Use service client to get user details
            response = self.service_client.auth.admin.get_user_by_id(user_id)
            if response and response.user:
                return response.user.email
            return None
        except Exception as e:
            logger.error(f"Error getting user email: {e}")
            return None

    # ==================== Crypto Operations ====================

    def get_crypto_by_symbol(self, symbol: str) -> Optional[Dict]:
        """Get crypto by symbol"""
        try:
            response = self.client.table('cryptos').select(
                '*').eq('symbol', symbol.upper()).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting crypto by symbol: {e}")
            return None

    def get_crypto_by_id(self, crypto_id: int) -> Optional[Dict]:
        """Get crypto by ID"""
        try:
            response = self.client.table('cryptos').select(
                '*').eq('crypto_id', crypto_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting crypto by ID: {e}")
            return None

    def get_all_cryptos(self) -> List[Dict]:
        """Get all cryptos"""
        try:
            response = self.client.table('cryptos').select('*').execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting all cryptos: {e}")
            return []

    def add_crypto(self, symbol: str, name: str) -> Optional[Dict]:
        """Add a new crypto"""
        try:
            response = self.client.table('cryptos').insert({
                'symbol': symbol.upper(),
                'name': name
            }).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error adding crypto: {e}")
            return None

    # ==================== Watchlist Operations ====================

    def get_user_watchlist(self, user_id: str) -> List[Dict]:
        """Get user's watchlist with crypto details and latest prices"""
        try:
            response = self.client.table('watchlist').select(
                '*, cryptos(*)'
            ).eq('user_id', user_id).execute()

            # Enrich with latest prices
            watchlist = response.data
            logger.info(
                f"Found {len(watchlist)} watchlist items for user {user_id}")

            for item in watchlist:
                crypto_id = item['crypto_id']
                crypto_symbol = item['cryptos']['symbol'] if item.get(
                    'cryptos') else 'Unknown'

                latest_price = self.get_latest_price(crypto_id)
                if latest_price:
                    item['current_price'] = latest_price['price']
                    item['change_24h'] = latest_price.get('change_24h', 0)
                    item['market_cap'] = latest_price.get('market_cap', 0)
                    item['volume_24h'] = latest_price.get('volume_24h', 0)
                    logger.info(
                        f"{crypto_symbol}: price=${latest_price['price']}, change={latest_price.get('change_24h', 0)}%")
                else:
                    logger.warning(
                        f"No price data found for {crypto_symbol} (crypto_id={crypto_id})")

            return watchlist
        except Exception as e:
            logger.error(f"Error getting user watchlist: {e}")
            return []

    def is_in_watchlist(self, user_id: str, crypto_id: int) -> bool:
        """Check if crypto is already in user's watchlist"""
        try:
            response = self.client.table('watchlist').select('watch_id').eq(
                'user_id', user_id
            ).eq('crypto_id', crypto_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking watchlist: {e}")
            return False

    def add_to_watchlist(self, user_id: str, crypto_id: int, alert_percent: float = 5.0) -> Optional[Dict]:
        """Add crypto to user's watchlist"""
        try:
            # Use service client to bypass RLS since we've already authenticated the user
            client = self.service_client if self.service_client else self.client
            response = client.table('watchlist').insert({
                'user_id': user_id,
                'crypto_id': crypto_id,
                'alert_percent': alert_percent
            }).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error adding to watchlist: {e}")
            return None

    def remove_from_watchlist(self, watch_id: int, user_id: str) -> bool:
        """Remove crypto from user's watchlist"""
        try:
            # Use service client to bypass RLS since we've already authenticated the user
            client = self.service_client if self.service_client else self.client
            client.table('watchlist').delete().eq(
                'watch_id', watch_id).eq('user_id', user_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error removing from watchlist: {e}")
            return False

    def update_alert_threshold(self, watch_id: int, user_id: str, alert_percent: float) -> bool:
        """Update alert threshold for a watchlist item"""
        try:
            # Use service client to bypass RLS since we've already authenticated the user
            client = self.service_client if self.service_client else self.client
            client.table('watchlist').update({
                'alert_percent': alert_percent
            }).eq('watch_id', watch_id).eq('user_id', user_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating alert threshold: {e}")
            return False

    # ==================== Price History Operations ====================

    def get_latest_price(self, crypto_id: int) -> Optional[Dict]:
        """Get latest price for a crypto"""
        try:
            response = self.client.table('price_history').select('*').eq(
                'crypto_id', crypto_id
            ).order('timestamp', desc=True).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting latest price: {e}")
            return None

    def get_price_history(self, crypto_id: int, days: int = 30) -> List[Dict]:
        """Get price history for last N days"""
        try:
            from datetime import datetime, timedelta, timezone

            # Calculate the date N days ago
            cutoff_date = (datetime.now(timezone.utc) -
                           timedelta(days=days)).isoformat()

            response = self.client.table('price_history').select('*').eq(
                'crypto_id', crypto_id
            ).gte('timestamp', cutoff_date).order('timestamp', desc=False).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting price history: {e}")
            return []

    def add_price_history(self, crypto_id: int, price: float, market_cap: float = None,
                          volume_24h: float = None, change_24h: float = None) -> Optional[Dict]:
        """Add price history record"""
        try:
            data = {
                'crypto_id': crypto_id,
                'price': price
            }
            if market_cap is not None:
                data['market_cap'] = market_cap
            if volume_24h is not None:
                data['volume_24h'] = volume_24h
            if change_24h is not None:
                data['change_24h'] = change_24h

            logger.info(
                f"Adding price history for crypto_id={crypto_id}: ${price}, change={change_24h}%")

            # Use service client to bypass RLS for system operations
            client = self.service_client if self.service_client else self.client
            response = client.table(
                'price_history').insert(data).execute()

            result = response.data[0] if response.data else None
            if result:
                logger.info(
                    f"Successfully added price history record: {result}")
            else:
                logger.warning(f"Price history insert returned no data")

            return result
        except Exception as e:
            logger.error(f"Error adding price history: {e}")
            return None

    def bulk_insert_price_history(self, records: List[Dict]) -> bool:
        """Bulk insert price history records"""
        try:
            if not records:
                return True
            response = self.service_client.table(
                'price_history').insert(records).execute()
            return True
        except Exception as e:
            logger.error(f"Error bulk inserting price history: {e}")
            return False

    # ==================== Alerts Operations ====================

    def log_alert(self, user_id: str, crypto_id: int, trigger_price: float,
                  percent_change: float, alert_type: str) -> Optional[Dict]:
        """Log a price alert"""
        try:
            response = self.client.table('alerts_log').insert({
                'user_id': user_id,
                'crypto_id': crypto_id,
                'trigger_price': trigger_price,
                'percent_change': percent_change,
                'alert_type': alert_type
            }).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error logging alert: {e}")
            return None

    def get_user_alerts(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get user's alert history"""
        try:
            response = self.client.table('alerts_log').select(
                '*, cryptos(*)'
            ).eq('user_id', user_id).order('timestamp', desc=True).limit(limit).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting user alerts: {e}")
            return []

    def get_all_watchlist_items(self) -> List[Dict]:
        """Get all watchlist items (for background tasks, using service key)"""
        try:
            if not self.service_client:
                logger.error("Service client not available")
                return []

            response = self.service_client.table('watchlist').select(
                '*, cryptos(*)'
            ).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting all watchlist items: {e}")
            return []

    # ==================== User Preferences ====================

    def get_user_preferences(self, user_id: str) -> Optional[Dict]:
        """Get user preferences"""
        try:
            response = self.client.table('user_preferences').select(
                '*').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0]
            else:
                # Create default preferences
                return self.create_user_preferences(user_id)
        except Exception as e:
            logger.error(f"Error getting user preferences: {e}")
            return None

    def create_user_preferences(self, user_id: str) -> Optional[Dict]:
        """Create default user preferences"""
        try:
            response = self.client.table('user_preferences').insert({
                'user_id': user_id,
                'email_alerts_enabled': True,
                'daily_summary_enabled': True
            }).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating user preferences: {e}")
            return None

    def update_user_preferences(self, user_id: str, email_alerts_enabled: bool = None,
                                daily_summary_enabled: bool = None) -> bool:
        """Update user preferences"""
        try:
            data = {}
            if email_alerts_enabled is not None:
                data['email_alerts_enabled'] = email_alerts_enabled
            if daily_summary_enabled is not None:
                data['daily_summary_enabled'] = daily_summary_enabled

            if data:
                self.client.table('user_preferences').update(
                    data).eq('user_id', user_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating user preferences: {e}")
            return False


# Singleton instance
db = SupabaseDB()
