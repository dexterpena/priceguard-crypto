#!/usr/bin/env python3
"""
Cache Refresher Service - Separate process for updating popular_cryptos cache.
Run this separately from the Flask app.

Usage:
    python cache_refresher.py           # Run continuously with 5-minute intervals
    python cache_refresher.py --once    # Run once and exit (for cron jobs)
"""

import logging
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from services.popular_cryptos_cache import PopularCryptosCacheService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def refresh_cache_job():
    """Job to refresh the popular cryptos cache"""
    logger.info("=" * 60)
    logger.info(f"Starting cache refresh at {datetime.now()}")
    logger.info("=" * 60)

    try:
        cache_service = PopularCryptosCacheService()
        result = cache_service.refresh_popular_cryptos(limit=100)

        if result['success']:
            logger.info(f"✅ Cache refresh successful!")
            logger.info(f"   New cryptos cached: {result['cached_count']}")
            logger.info(
                f"   Existing cryptos updated: {result['updated_count']}")
            logger.info(
                f"   Total processed: {result.get('total_processed', 0)}")
        else:
            logger.error(
                f"❌ Cache refresh failed: {result.get('error', 'Unknown error')}")

    except Exception as e:
        logger.exception(f"❌ Error during cache refresh: {e}")

    logger.info("=" * 60)


def run_continuous():
    """Run the scheduler continuously"""
    logger.info("🚀 Starting PriceGuard Crypto Cache Refresher")
    logger.info("   Mode: Continuous (every 5 minutes)")
    logger.info("   Press Ctrl+C to stop")
    logger.info("")

    # Run immediately on startup
    logger.info("Running initial cache refresh...")
    refresh_cache_job()

    # Set up scheduler for recurring runs
    scheduler = BlockingScheduler()
    scheduler.add_job(
        refresh_cache_job,
        trigger=IntervalTrigger(minutes=5),
        id='refresh_popular_cryptos',
        name='Refresh popular cryptos cache',
        replace_existing=True
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("\n👋 Cache refresher stopped by user")
        sys.exit(0)


def run_once():
    """Run the refresh job once and exit (for cron jobs)"""
    logger.info("🚀 Running cache refresh (one-time mode)")
    refresh_cache_job()
    logger.info("✅ One-time refresh complete. Exiting.")
    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_once()
    else:
        run_continuous()
