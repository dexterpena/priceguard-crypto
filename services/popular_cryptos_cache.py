"""
Popular Cryptos Cache Service

This service is responsible for:
1. Fetching top cryptocurrencies from CoinDesk API
2. Caching them in the popular_cryptos table
3. Running on a schedule (every 5 minutes)
"""

import logging
from datetime import datetime, timezone

from database.db import SupabaseDB
from services.crypto_api import crypto_api

logger = logging.getLogger(__name__)


class PopularCryptosCacheService:
    """Service for caching popular cryptocurrencies data"""

    def __init__(self):
        self.db = SupabaseDB()

    def refresh_popular_cryptos(self, limit: int = 100) -> dict:
        """
        Fetch top cryptocurrencies from API and cache in database

        Args:
            limit: Number of top cryptos to cache (default: 100)

        Returns:
            {
                'success': bool,
                'cached_count': int,
                'updated_count': int,
                'error': str (optional)
            }
        """
        try:
            logger.info(
                f"Starting refresh of popular cryptos (limit: {limit})")

            # Fetch top cryptos from CoinDesk API
            top_cryptos = crypto_api.get_top_cryptos(limit=limit)

            if not top_cryptos:
                logger.warning("No data received from CoinDesk API")
                return {
                    'success': False,
                    'cached_count': 0,
                    'updated_count': 0,
                    'error': 'No data from API'
                }

            cached_count = 0
            updated_count = 0

            # Upsert each crypto into the database
            for crypto in top_cryptos:
                try:
                    # Get API ID from toplist response
                    # Note: The toplist API should include ID field
                    api_id = crypto.get('id') or self._get_api_id_from_symbol(
                        crypto['symbol'])

                    if not api_id:
                        logger.warning(
                            f"Could not determine API ID for {crypto['symbol']}, skipping")
                        continue

                    # Prepare data for upsert
                    data = {
                        'api_id': api_id,
                        'symbol': crypto['symbol'],
                        'name': crypto['name'],
                        'logo_url': crypto.get('logo_url', ''),
                        'price': float(crypto['price']),
                        'market_cap': float(crypto.get('market_cap', 0)),
                        'volume_24h': float(crypto.get('volume_24h', 0)),
                        'change_24h': float(crypto.get('change_24h', 0)),
                        'price_updated_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }

                    # Upsert into database
                    result = self.db.service_client.table('popular_cryptos').upsert(
                        data,
                        on_conflict='api_id'
                    ).execute()

                    if result.data:
                        # Check if it was an insert or update by checking if cached_at is recent
                        is_new = self._is_newly_cached(api_id)
                        if is_new:
                            cached_count += 1
                        else:
                            updated_count += 1

                except Exception as e:
                    logger.error(
                        f"Error caching crypto {crypto.get('symbol', 'unknown')}: {e}")
                    continue

            logger.info(
                f"Popular cryptos refresh complete: {cached_count} new, {updated_count} updated")

            return {
                'success': True,
                'cached_count': cached_count,
                'updated_count': updated_count,
                'total_processed': len(top_cryptos)
            }

        except Exception as e:
            logger.error(f"Error refreshing popular cryptos: {e}")
            return {
                'success': False,
                'cached_count': 0,
                'updated_count': 0,
                'error': str(e)
            }

    def _get_api_id_from_symbol(self, symbol: str) -> int | None:
        """
        Fetch API ID for a crypto by symbol using the metadata endpoint

        Args:
            symbol: Crypto symbol (e.g., 'BTC')

        Returns:
            API ID or None if not found
        """
        try:
            # Use the watchlist data endpoint which returns ID
            data = crypto_api.get_watchlist_data([symbol])

            if data and symbol in data:
                # The ID should be in the response
                # We might need to add this to the get_watchlist_data response
                return data[symbol].get('id')

            return None

        except Exception as e:
            logger.error(
                f"Error fetching API ID for symbol {symbol}: {e}")
            return None

    def _is_newly_cached(self, api_id: int) -> bool:
        """
        Check if a crypto was just cached (cached_at is recent)

        Args:
            api_id: CoinDesk API ID

        Returns:
            True if newly cached (within last minute), False otherwise
        """
        try:
            result = self.db.service_client.table('popular_cryptos').select(
                'cached_at').eq('api_id', api_id).execute()

            if result.data and len(result.data) > 0:
                cached_at_str = result.data[0]['cached_at']
                # Parse datetime string - handle both formats
                if isinstance(cached_at_str, str):
                    cached_at_str = cached_at_str.replace('Z', '+00:00')
                    cached_at = datetime.fromisoformat(cached_at_str)
                    if cached_at.tzinfo is None:
                        cached_at = cached_at.replace(tzinfo=timezone.utc)
                else:
                    cached_at = cached_at_str

                now = datetime.now(timezone.utc)
                diff = (now - cached_at).total_seconds()
                return diff < 60  # Newly cached if within last minute

            return True  # If no record found, treat as new

        except Exception as e:
            logger.error(f"Error checking cached status: {e}")
            return False

    def get_cached_crypto(self, api_id: int) -> dict | None:
        """
        Get cached crypto data by API ID

        Args:
            api_id: CoinDesk API ID

        Returns:
            Crypto data dict or None if not found
        """
        try:
            result = self.db.client.table('popular_cryptos').select(
                '*').eq('api_id', api_id).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]

            return None

        except Exception as e:
            logger.error(f"Error fetching cached crypto {api_id}: {e}")
            return None

    def get_all_cached_cryptos(self) -> list[dict]:
        """
        Get all cached popular cryptocurrencies

        Returns:
            List of crypto data dicts
        """
        try:
            result = self.db.client.table('popular_cryptos').select(
                '*').order('market_cap', desc=True).execute()

            return result.data if result.data else []

        except Exception as e:
            logger.error(f"Error fetching all cached cryptos: {e}")
            return []


# Singleton instance
popular_cryptos_cache = PopularCryptosCacheService()
