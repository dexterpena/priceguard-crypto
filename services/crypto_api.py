import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests

from config import Config

logger = logging.getLogger(__name__)


class CryptoAPIService:
    """Service for fetching cryptocurrency data from CoinDesk API"""

    def __init__(self):
        self.base_url = "https://data-api.coindesk.com/index/cc/v1"
        self.session = requests.Session()
        self.api_key = Config.COINDESK_API_KEY

        # Supported crypto symbols for CoinDesk
        self.supported_symbols = [
            'BTC', 'ETH', 'USDT', 'BNB', 'SOL', 'XRP', 'USDC', 'ADA', 'AVAX', 'DOGE']

        # Cache for API responses with TTL
        self._cache = {}
        self._cache_ttl = {
            'price': 30,  # 30 seconds for price data
            'history': 300,  # 5 minutes for historical data
        }

    def _get_cache_key(self, cache_type: str, identifier: str) -> str:
        """Generate cache key"""
        return f"{cache_type}:{identifier}"

    def _get_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Get data from cache if not expired"""
        if cache_key in self._cache:
            data, timestamp = self._cache[cache_key]
            cache_type = cache_key.split(':')[0]
            ttl = self._cache_ttl.get(cache_type, 60)
            if time.time() - timestamp < ttl:
                logger.info(f"Cache hit for {cache_key}")
                return data
            else:
                del self._cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, data: Dict):
        """Store data in cache"""
        self._cache[cache_key] = (data, time.time())

    def get_crypto_price(self, symbol: str) -> Optional[Dict]:
        """
        Get current price and details for a cryptocurrency

        Returns:
            {
                'symbol': str,
                'name': str,
                'price': float,
                'market_cap': float,
                'volume_24h': float,
                'change_24h': float,
                'timestamp': str
            }
        """
        try:
            symbol = symbol.upper()

            # Check cache first
            cache_key = self._get_cache_key('price', symbol)
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data

            # CoinDesk endpoint for historical data (get last 2 days to calculate 24h change)
            url = f"{self.base_url}/historical/days"
            params = {
                'market': 'cadli',
                'instrument': f'{symbol}-USD',
                'limit': 2,
                'aggregate': 1,
                'fill': 'true',
                'apply_mapping': 'true',
                'response_format': 'JSON',
                'api_key': self.api_key
            }

            response = self.session.get(url, params=params, headers={
                                        'Content-type': 'application/json; charset=UTF-8'}, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Parse the response
            if data and 'Data' in data and len(data['Data']) > 0:
                latest = data['Data'][-1]  # Most recent day

                # Calculate 24h change
                change_24h = 0
                if len(data['Data']) >= 2:
                    previous = data['Data'][-2]
                    if previous.get('CLOSE') and previous['CLOSE'] > 0:
                        change_24h = (
                            (latest.get('CLOSE', 0) - previous.get('CLOSE', 0)) / previous['CLOSE']) * 100

                result = {
                    'symbol': symbol,
                    'name': symbol,
                    'price': round(float(latest.get('CLOSE', 0)), 2),
                    'market_cap': 0,  # CoinDesk doesn't provide market cap in OHLCV data
                    'volume_24h': round(float(latest.get('VOLUME', 0)), 2),
                    'change_24h': round(float(change_24h), 2),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }

                # Cache the result
                self._set_cache(cache_key, result)
                return result

            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching crypto price for {symbol}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing crypto data for {symbol}: {e}")
            return None

    def get_multiple_crypto_prices(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Get current prices for multiple cryptocurrencies

        Returns:
            {
                'BTC': {...},
                'ETH': {...}
            }
        """
        try:
            results = {}

            # CoinDesk doesn't support batch requests, so we fetch individually
            # but we use caching to minimize API calls
            for symbol in symbols:
                price_data = self.get_crypto_price(symbol)
                if price_data:
                    results[symbol.upper()] = price_data

            return results

        except Exception as e:
            logger.error(f"Error fetching multiple crypto prices: {e}")
            return {}

    def get_historical_data(self, symbol: str, days: int = 30, unit: str = 'days') -> List[Dict]:
        """
        Get historical price data for a cryptocurrency

        Args:
            symbol: Cryptocurrency symbol
            days: Number of time periods to fetch
            unit: 'hours' for 24h view, 'days' for others

        Returns:
            [
                {
                    'price': float,
                    'market_cap': float,
                    'volume_24h': float,
                    'timestamp': str,
                    'open': float,
                    'high': float,
                    'low': float,
                    'close': float
                },
                ...
            ]
        """
        try:
            symbol = symbol.upper()

            # Check cache first
            cache_key = self._get_cache_key(
                'history', f"{symbol}:{days}:{unit}")
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data

            # CoinDesk endpoint for historical OHLCV data
            url = f"{self.base_url}/historical/{unit}"
            params = {
                'market': 'cadli',
                'instrument': f'{symbol}-USD',
                'limit': days,
                'aggregate': 1,
                'fill': 'true',
                'apply_mapping': 'true',
                'response_format': 'JSON',
                'api_key': self.api_key
            }

            response = self.session.get(url, params=params, headers={
                                        'Content-type': 'application/json; charset=UTF-8'}, timeout=15)
            response.raise_for_status()

            data = response.json()

            if data and 'Data' in data:
                historical_data = []

                for item in data['Data']:
                    historical_data.append({
                        'price': round(float(item.get('CLOSE', 0)), 2),
                        'market_cap': 0,  # CoinDesk doesn't provide market cap
                        'volume_24h': round(float(item.get('VOLUME', 0)), 2),
                        'timestamp': datetime.fromtimestamp(item.get('TIMESTAMP', 0), tz=timezone.utc).isoformat(),
                        'open': round(float(item.get('OPEN', 0)), 2),
                        'high': round(float(item.get('HIGH', 0)), 2),
                        'low': round(float(item.get('LOW', 0)), 2),
                        'close': round(float(item.get('CLOSE', 0)), 2)
                    })

                # Cache the result
                self._set_cache(cache_key, historical_data)
                return historical_data

            return []

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return []
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing historical data for {symbol}: {e}")
            return []

    def search_crypto(self, query: str) -> List[Dict]:
        """
        Search for cryptocurrencies by name or symbol

        Note: CoinDesk doesn't have a search endpoint, so we filter from supported symbols

        Returns:
            [
                {
                    'id': str,
                    'symbol': str,
                    'name': str
                },
                ...
            ]
        """
        try:
            query = query.upper()
            results = []

            # Simple filtering from supported symbols
            for symbol in self.supported_symbols:
                if query in symbol:
                    results.append({
                        'id': symbol.lower(),
                        'symbol': symbol,
                        'name': symbol,
                        'thumb': ''
                    })

            return results

        except Exception as e:
            logger.error(f"Error searching crypto: {e}")
            return []


# Singleton instance
crypto_api = CryptoAPIService()
