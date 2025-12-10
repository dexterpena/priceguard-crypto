import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from config import Config

logger = logging.getLogger(__name__)


class CryptoAPIService:
    """Service for fetching cryptocurrency data from CoinDesk API"""

    def __init__(self):
        self.base_url = Config.COINDESK_API_URL
        self.toplist_url = f"{self.base_url}/asset/v1/top/list"
        self.asset_url = f"{self.base_url}/asset/v2/metadata"
        self.session = requests.Session()
        self.api_key = Config.COINDESK_API_KEY

        # Cache for API responses with TTL
        self._cache = {}
        self._cache_ttl = {
            'price': 30,  # 30 seconds for price data
            'history': 300,  # 5 minutes for historical data
            'toplist': 300,  # 5 minutes for toplist data
            'metadata': 60,  # 1 minute for asset metadata
        }

    def _get_cache_key(self, cache_type: str, identifier: str) -> str:
        """Generate cache key"""
        return f"{cache_type}:{identifier}"

    def _get_from_cache(self, cache_key: str) -> dict | list | None:
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

    def _set_cache(self, cache_key: str, data: dict | list):
        """Store data in cache"""
        self._cache[cache_key] = (data, time.time())

    def get_crypto_price(self, symbol: str) -> dict | None:
        """
        Get current price and details for a cryptocurrency using asset metadata

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

            # CoinDesk asset metadata endpoint includes live pricing
            url = self.asset_url
            params = {
                'assets': symbol,
                'asset_lookup_priority': 'SYMBOL',
                'quote_asset': 'USD',
                'asset_language': 'en-US',
                'groups': 'BASIC,PRICE,MKT_CAP,VOLUME,CHANGE',
                'api_key': self.api_key
            }

            response = self.session.get(url, params=params, headers={
                                        'Content-type': 'application/json; charset=UTF-8'}, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Parse the response
            if data and 'Data' in data:
                asset_data = data['Data'].get(symbol)
                if not asset_data:
                    # Fallback: try uppercased key
                    asset_data = data['Data'].get(symbol.upper())
                if asset_data:

                    result = {
                        'symbol': symbol,
                        'name': asset_data.get('NAME', symbol),
                        'price': round(float(asset_data.get('PRICE_USD', 0)), 2),
                        'market_cap': round(float(asset_data.get('CIRCULATING_MKT_CAP_USD', 0)), 2),
                        'volume_24h': round(float(asset_data.get('SPOT_MOVING_24_HOUR_QUOTE_VOLUME_USD', 0)), 2),
                        'change_24h': round(float(asset_data.get('SPOT_MOVING_24_HOUR_CHANGE_PERCENTAGE_USD', 0)), 2),
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'logo_url': asset_data.get('LOGO_URL', '')
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

    def get_multiple_crypto_prices(self, symbols: list[str]) -> dict[str, dict]:
        """
        Get current prices for multiple cryptocurrencies using asset metadata

        Returns:
            {
                'BTC': {...},
                'ETH': {...}
            }
        """
        try:
            results = {}

            # Convert symbols to uppercase and join for asset lookup
            symbols_upper = [s.upper() for s in symbols]
            assets_param = ','.join(symbols_upper)

            # CoinDesk asset metadata endpoint
            url = self.asset_url
            params = {
                'assets': assets_param,
                'asset_lookup_priority': 'SYMBOL',
                'quote_asset': 'USD',
                'asset_language': 'en-US',
                'groups': 'BASIC,PRICE,MKT_CAP,VOLUME,CHANGE',
                'api_key': self.api_key
            }

            response = self.session.get(url, params=params, headers={
                                        'Content-type': 'application/json; charset=UTF-8'}, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Parse the response
            if data and 'Data' in data:
                for symbol, asset_data in data['Data'].items():
                    sym = symbol.upper()

                    results[sym] = {
                        'symbol': sym,
                        'name': asset_data.get('NAME', sym),
                        'price': round(float(asset_data.get('PRICE_USD', 0)), 2),
                        'market_cap': round(float(asset_data.get('CIRCULATING_MKT_CAP_USD', 0)), 2),
                        'volume_24h': round(float(asset_data.get('SPOT_MOVING_24_HOUR_QUOTE_VOLUME_USD', 0)), 2),
                        'change_24h': round(float(asset_data.get('SPOT_MOVING_24_HOUR_CHANGE_PERCENTAGE_USD', 0)), 2),
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'logo_url': asset_data.get('LOGO_URL', '')
                    }

            return results

        except Exception as e:
            logger.error(f"Error fetching multiple crypto prices: {e}")
            return {}

    def get_historical_data(self, symbol: str, days: int = 30, unit: str = 'days') -> list[dict]:
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
            # Use days or hours based on unit parameter
            url = f"{self.base_url}/index/cc/v1/historical/{unit}"
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

    def search_crypto(self, query: str) -> list[dict]:
        """
        Search for cryptocurrencies by name or symbol

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

            # Reuse toplist data (cached) to search by symbol or name
            top_cryptos = self.get_top_cryptos(limit=200)
            for asset in top_cryptos:
                symbol = asset.get('symbol', '').upper()
                name = asset.get('name', '').upper()
                if query in symbol or query in name:
                    results.append({
                        'id': asset.get('id'),
                        'symbol': asset.get('symbol', ''),
                        'name': asset.get('name', ''),
                        'logo_url': asset.get('logo_url', '')
                    })

            return results

        except Exception as e:
            logger.error(f"Error searching crypto: {e}")
            return []

    def get_top_cryptos(self, limit: int = 100, page: int = 1) -> list[dict]:
        """
        Get top cryptocurrencies by market cap using CoinDesk toplist endpoint

        Args:
            limit: Number of cryptocurrencies to fetch (default: 100, max: 100)
            page: Page number for pagination (default: 1)

        Returns:
            [
                {
                    'symbol': str,
                    'name': str,
                    'price': float,
                    'market_cap': float,
                    'volume_24h': float,
                    'change_24h': float,
                    'logo_url': str
                },
                ...
            ]
        """
        try:
            # Check cache first
            cache_key = self._get_cache_key('toplist', f"{limit}:{page}")
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data

            # CoinDesk toplist endpoint
            params = {
                'page': page,
                'page_size': min(limit, 100),  # Max 100 per page
                'sort_by': 'CIRCULATING_MKT_CAP_USD',
                'sort_direction': 'DESC',
                'groups': 'ID,BASIC,SUPPLY,PRICE,MKT_CAP,VOLUME,CHANGE,TOPLIST_RANK',
                'toplist_quote_asset': 'USD',
                'api_key': self.api_key
            }

            response = self.session.get(
                self.toplist_url,
                params=params,
                headers={'Content-type': 'application/json; charset=UTF-8'},
                timeout=10
            )
            response.raise_for_status()

            data = response.json()

            if not data or 'Data' not in data or 'LIST' not in data['Data']:
                logger.warning("No toplist data found in response")
                return []

            toplist = []
            for asset in data['Data']['LIST']:
                try:
                    toplist.append({
                        'id': asset.get('ID'),  # CoinDesk API ID
                        'symbol': asset.get('SYMBOL', ''),
                        'name': asset.get('NAME', ''),
                        'price': round(float(asset.get('PRICE_USD', 0)), 2),
                        'market_cap': float(asset.get('CIRCULATING_MKT_CAP_USD', 0)),
                        'volume_24h': float(asset.get('SPOT_MOVING_24_HOUR_QUOTE_VOLUME_USD', 0)),
                        'change_24h': round(float(asset.get('SPOT_MOVING_24_HOUR_CHANGE_PERCENTAGE_USD', 0)), 2),
                        'logo_url': asset.get('LOGO_URL', '')
                    })
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Error parsing asset {asset.get('SYMBOL', 'unknown')}: {e}")
                    continue

            # Cache the result
            self._set_cache(cache_key, toplist)
            return toplist

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching top cryptos: {e}")
            return []
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing toplist data: {e}")
            return []

    def get_crypto_with_logo(self, symbol: str) -> dict | None:
        """
        Get cryptocurrency details including logo from CoinDesk asset management API

        Args:
            symbol: Cryptocurrency symbol (e.g., 'BTC', 'ETH')

        Returns:
            {
                'symbol': str,
                'name': str,
                'logo_url': str,
                'id': int
            } or None if not found
        """
        try:
            symbol = symbol.upper()

            # Check cache first
            cache_key = self._get_cache_key('asset', symbol)
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data

            # Get from toplist to find the crypto
            top_cryptos = self.get_top_cryptos(limit=100)

            for crypto in top_cryptos:
                if crypto.get('symbol', '').upper() == symbol:
                    result = {
                        'symbol': crypto['symbol'],
                        'name': crypto['name'],
                        'logo_url': crypto['logo_url'],
                        'id': crypto['id']
                    }
                    # Cache the result
                    self._set_cache(cache_key, result)
                    return result

            # If not found in top 100, try fetching more
            for page in range(2, 5):  # Check up to 400 cryptos
                top_cryptos = self.get_top_cryptos(limit=100, page=page)
                for crypto in top_cryptos:
                    if crypto.get('symbol', '').upper() == symbol:
                        result = {
                            'symbol': crypto['symbol'],
                            'name': crypto['name'],
                            'logo_url': crypto['logo_url'],
                            'id': crypto['id']
                        }
                        # Cache the result
                        self._set_cache(cache_key, result)
                        return result

        except Exception as e:
            logger.error(f"Error fetching crypto details for {symbol}: {e}")
            return None

    def get_watchlist_data(self, symbols: list[str]) -> dict[str, dict]:
        """
        Get detailed metadata for multiple cryptocurrencies for watchlist display

        Args:
            symbols: List of cryptocurrency symbols (e.g., ['BTC', 'ETH'])

        Returns:
            {
                'BTC': {
                    'symbol': str,
                    'name': str,
                    'logo_url': str,
                    'price': float,
                    'change_24h': float,
                    'market_cap': float,
                    'volume_24h': float
                },
                ...
            }
        """
        try:
            if not symbols:
                return {}

            # Convert to uppercase and join
            symbols_upper = [s.upper() for s in symbols]
            assets_param = ','.join(symbols_upper)

            # Check cache first
            cache_key = self._get_cache_key('metadata', assets_param)
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data

            # CoinDesk asset metadata endpoint
            url = self.asset_url
            params = {
                'assets': assets_param,
                'asset_lookup_priority': 'SYMBOL',
                'quote_asset': 'USD',
                'asset_language': 'en-US',
                'groups': 'BASIC,PRICE,MKT_CAP,VOLUME,CHANGE',
                'api_key': self.api_key
            }

            response = self.session.get(url, params=params, headers={
                'Content-type': 'application/json; charset=UTF-8'}, timeout=15)
            response.raise_for_status()

            data = response.json()

            results = {}
            if data and 'Data' in data:
                for symbol, asset_data in data['Data'].items():
                    results[symbol] = {
                        'symbol': symbol,
                        'name': asset_data.get('NAME', ''),
                        'logo_url': asset_data.get('LOGO_URL', ''),
                        'price': round(float(asset_data.get('PRICE_USD', 0)), 2),
                        'change_24h': round(float(asset_data.get('SPOT_MOVING_24_HOUR_CHANGE_PERCENTAGE_USD', 0)), 2),
                        'market_cap': round(float(asset_data.get('CIRCULATING_MKT_CAP_USD', 0)), 2),
                        'volume_24h': round(float(asset_data.get('SPOT_MOVING_24_HOUR_QUOTE_VOLUME_USD', 0)), 2)
                    }

            # Cache the result
            self._set_cache(cache_key, results)
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching watchlist data: {e}")
            return {}
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing watchlist data: {e}")
            return {}


# Singleton instance
crypto_api = CryptoAPIService()
