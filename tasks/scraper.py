"""
Background task to scrape/fetch cryptocurrency prices from API
and store them in the database
"""
import logging
from datetime import datetime

from database import db
from services import crypto_api

logger = logging.getLogger(__name__)


def scrape_all_crypto_prices():
    """
    Fetch latest prices for all tracked cryptocurrencies
    and store in price_history table
    """
    logger.info("Starting daily crypto price scrape...")

    results = {
        'success': 0,
        'failed': 0,
        'errors': []
    }

    try:
        # Get all cryptos from database
        cryptos = db.get_all_cryptos()

        if not cryptos:
            logger.warning("No cryptocurrencies found in database")
            return results

        logger.info(f"Fetching prices for {len(cryptos)} cryptocurrencies...")

        # Fetch prices for each crypto
        for crypto in cryptos:
            try:
                symbol = crypto['symbol']
                crypto_id = crypto['crypto_id']

                # Fetch current price from API
                price_data = crypto_api.get_crypto_price(symbol)

                if price_data:
                    # Store in database
                    db.add_price_history(
                        crypto_id=crypto_id,
                        price=price_data['price'],
                        market_cap=price_data.get('market_cap'),
                        volume_24h=price_data.get('volume_24h'),
                        change_24h=price_data.get('change_24h')
                    )

                    results['success'] += 1
                    logger.info(f"✓ {symbol}: ${price_data['price']:,.2f}")
                else:
                    results['failed'] += 1
                    logger.warning(f"✗ {symbol}: Failed to fetch price")

            except Exception as e:
                results['failed'] += 1
                error_msg = f"{crypto['symbol']}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(
                    f"Error fetching price for {crypto['symbol']}: {e}")

        logger.info(
            f"Price scrape completed. Success: {results['success']}, Failed: {results['failed']}")

    except Exception as e:
        logger.error(f"Fatal error in price scrape: {e}")
        results['errors'].append(f"Fatal error: {str(e)}")

    return results


def scrape_historical_data(symbol: str, crypto_id: int, days: int = 30):
    """
    Fetch and store historical data for a specific cryptocurrency
    Useful for initializing data or backfilling
    """
    logger.info(f"Fetching {days} days of historical data for {symbol}...")

    try:
        # Fetch historical data from API
        historical_data = crypto_api.get_historical_data(symbol, days)

        if not historical_data:
            logger.warning(f"No historical data returned for {symbol}")
            return 0

        # Prepare records for bulk insert
        records = []
        for entry in historical_data:
            records.append({
                'crypto_id': crypto_id,
                'price': entry['price'],
                'market_cap': entry.get('market_cap'),
                'volume_24h': entry.get('volume_24h'),
                'timestamp': entry['timestamp']
            })

        # Bulk insert
        if records:
            success = db.bulk_insert_price_history(records)
            if success:
                logger.info(
                    f"Inserted {len(records)} historical records for {symbol}")
                return len(records)

        return 0

    except Exception as e:
        logger.error(f"Error fetching historical data for {symbol}: {e}")
        return 0


def initialize_historical_data_for_all():
    """
    Initialize historical data for all cryptocurrencies in database
    Run this once when setting up the system
    """
    logger.info("Initializing historical data for all cryptocurrencies...")

    cryptos = db.get_all_cryptos()
    total_records = 0

    for crypto in cryptos:
        count = scrape_historical_data(
            crypto['symbol'], crypto['crypto_id'], days=30)
        total_records += count

    logger.info(
        f"Historical data initialization complete. Total records: {total_records}")
    return total_records


if __name__ == '__main__':
    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run the scraper
    scrape_all_crypto_prices()
