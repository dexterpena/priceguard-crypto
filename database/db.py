import logging
from datetime import datetime, timedelta, timezone

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
        # Create service client for server-side admin operations
        self.service_client: Client = create_client(
            Config.SUPABASE_URL,
            Config.SUPABASE_SERVICE_KEY
        ) if Config.SUPABASE_SERVICE_KEY else None

    def get_user_email(self, user_id: str) -> str | None:
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

    # Watchlist Operations

    def get_user_watchlist(self, user_id: str, user_token: str | None = None) -> list[dict]:
        """Get user's watchlist with cached crypto info and live prices"""
        try:
            watchlist = []
            # Choose client for watchlist and enrichment queries
            data_client = self.service_client if self.service_client else self.client

            # Try anon client with user token first (RLS)
            if user_token:
                try:
                    data_client = self.client  # anon client with token
                    data_client.postgrest.auth(user_token)
                    response = data_client.table('watchlist').select(
                        '*'
                    ).eq('user_id', user_id).order('date_added', desc=True).execute()
                    watchlist = response.data or []
                    logger.info(f"Watchlist fetched via user token: {len(watchlist)} items")
                except Exception as e:
                    logger.warning(f"Anon watchlist fetch failed, will try service client: {e}")

            # Fallback to service client if available or if no items returned
            if self.service_client and (not watchlist):
                data_client = self.service_client
                response = data_client.table('watchlist').select(
                    '*'
                ).eq('user_id', user_id).order('date_added', desc=True).execute()
                watchlist = response.data or []
                logger.info(f"Watchlist fetched via service role: {len(watchlist)} items")

            logger.info(f"Found {len(watchlist)} watchlist items for user {user_id}")

            # Enrich with latest prices from cache
            for item in watchlist:
                api_crypto_id = item['api_crypto_id']

                # Get latest price from popular_cryptos cache
                crypto_cache = data_client.table('popular_cryptos').select(
                    'price', 'change_24h', 'market_cap', 'volume_24h'
                ).eq('api_id', api_crypto_id).execute()

                if crypto_cache.data and len(crypto_cache.data) > 0:
                    cached_data = crypto_cache.data[0]
                    item['current_price'] = float(cached_data['price'])
                    item['change_24h'] = float(
                        cached_data.get('change_24h', 0))
                    item['market_cap'] = float(
                        cached_data.get('market_cap', 0))
                    item['volume_24h'] = float(
                        cached_data.get('volume_24h', 0))
                    logger.info(
                        f"{item['symbol']}: price=${cached_data['price']}, change={cached_data.get('change_24h', 0)}%")
                else:
                    # Fallback: fetch from API
                    logger.warning(
                        f"No cached price for {item['symbol']} (api_id={api_crypto_id}), will use API")
                    item['current_price'] = 0
                    item['change_24h'] = 0
                    item['market_cap'] = 0
                    item['volume_24h'] = 0

            # Sort by market cap descending to match popular cryptos
            watchlist.sort(
                key=lambda x: float(x.get('market_cap') or 0),
                reverse=True
            )

            return watchlist
        except Exception as e:
            logger.error(f"Error getting user watchlist: {e}")
            return []

    def get_user_watched_crypto_ids(self, user_id: str) -> list[int]:
        """Get list of api_crypto_ids that user is watching"""
        try:
            client = self.service_client if self.service_client else self.client
            # No user_token here; used for UI state only, RLS covered by service role or anon token not needed
            response = client.table('watchlist').select(
                'api_crypto_id'
            ).eq('user_id', user_id).execute()
            return [item['api_crypto_id'] for item in response.data]
        except Exception as e:
            logger.error(f"Error getting watched crypto IDs: {e}")
            return []

    def add_to_watchlist(self, user_id: str, api_crypto_id: int, symbol: str, name: str, logo_url: str = '', alert_percent: float = 5.0) -> dict | None:
        """Add crypto to user's watchlist with cached info"""
        try:
            # Use service client to bypass RLS since we've already authenticated the user
            client = self.service_client if self.service_client else self.client
            response = client.table('watchlist').insert({
                'user_id': user_id,
                'api_crypto_id': api_crypto_id,
                'symbol': symbol,
                'name': name,
                'logo_url': logo_url,
                'alert_percent': alert_percent
            }).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error adding to watchlist: {e}")
            return None

    def is_in_watchlist_by_api_id(self, user_id: str, api_crypto_id: int) -> bool:
        """Check if crypto is already in user's watchlist by API ID"""
        try:
            client = self.service_client if self.service_client else self.client
            response = client.table('watchlist').select('watch_id').eq(
                'user_id', user_id).eq('api_crypto_id', api_crypto_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking watchlist: {e}")
            return False

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

    # Alerts

    def log_alert(self, user_id: str, api_crypto_id: int, symbol: str, name: str,
                  trigger_price: float, percent_change: float, alert_type: str) -> bool:
        """Record a triggered alert"""
        try:
            client = self.service_client if self.service_client else self.client
            client.table('alerts_log').insert({
                'user_id': user_id,
                'api_crypto_id': api_crypto_id,
                'symbol': symbol,
                'name': name,
                'trigger_price': trigger_price,
                'percent_change': percent_change,
                'alert_type': alert_type
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Error logging alert: {e}")
            return False

    def has_recent_alert(self, user_id: str, api_crypto_id: int, lookback_hours: int = 24) -> bool:
        """Check if an alert was logged recently to avoid duplicate emails"""
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
            client = self.service_client if self.service_client else self.client
            result = client.table('alerts_log').select('alert_id').eq(
                'user_id', user_id
            ).eq('api_crypto_id', api_crypto_id).gte('timestamp', since.isoformat()).limit(1).execute()
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error checking recent alerts: {e}")
            return False

    def get_user_alerts(self, user_id: str) -> list[dict]:
        """Fetch user's alert history"""
        try:
            result = self.client.table('alerts_log').select('*').eq(
                'user_id', user_id).order('timestamp', desc=True).execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error fetching alert history: {e}")
            return []

    # User Preferences

    def get_user_preferences(self, user_id: str) -> dict | None:
        """Fetch or create default user preferences"""
        try:
            response = self.client.table('user_preferences').select(
                '*').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0]
            return self.create_user_preferences(user_id)
        except Exception as e:
            logger.error(f"Error getting user preferences: {e}")
            return None

    def create_user_preferences(self, user_id: str) -> dict | None:
        """Create default preferences for a user"""
        try:
            response = self.client.table('user_preferences').insert({
                'user_id': user_id,
                'email_alerts_enabled': True,
                'daily_summary_enabled': True,
                'watchlist_alerts_enabled': True,
                'price_alerts_enabled': True
            }).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating user preferences: {e}")
            return None

    def update_user_preferences(self, user_id: str, **prefs) -> bool:
        """Update user preferences fields"""
        allowed = {
            'email_alerts_enabled',
            'daily_summary_enabled',
            'watchlist_alerts_enabled',
            'price_alerts_enabled'
        }
        updates = {k: v for k, v in prefs.items() if k in allowed}

        if not updates:
            return True

        try:
            updates['updated_at'] = datetime.now(timezone.utc).isoformat()
            self.client.table('user_preferences').upsert({
                'user_id': user_id,
                **updates
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating user preferences: {e}")
            return False


db = SupabaseDB()
