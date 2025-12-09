"""
Background task to check price alerts and send notifications
"""
import logging
from datetime import datetime, timedelta

from database import db
from services import email_service

logger = logging.getLogger(__name__)


def check_all_alerts():
    """
    Check all watchlist items for alert conditions
    Send email notifications when thresholds are met
    """
    logger.info("Starting alert check...")

    results = {
        'checked': 0,
        'triggered': 0,
        'emails_sent': 0,
        'errors': []
    }

    try:
        # Get all watchlist items
        watchlist_items = db.get_all_watchlist_items()

        if not watchlist_items:
            logger.info("No watchlist items to check")
            return results

        logger.info(
            f"Checking alerts for {len(watchlist_items)} watchlist items...")

        for item in watchlist_items:
            try:
                results['checked'] += 1

                crypto_id = item['crypto_id']
                user_id = item['user_id']
                alert_percent = float(item['alert_percent'])

                # Get latest price
                latest_price = db.get_latest_price(crypto_id)
                if not latest_price:
                    continue

                current_price = float(latest_price['price'])

                # Get price from 24 hours ago
                history = db.get_price_history(crypto_id, days=2)
                if len(history) < 2:
                    continue

                # Calculate price from ~24h ago
                previous_price = float(history[0]['price'])

                # Calculate percent change
                percent_change = (
                    (current_price - previous_price) / previous_price) * 100

                # Check if alert threshold is met
                if abs(percent_change) >= alert_percent:
                    results['triggered'] += 1

                    alert_type = 'increase' if percent_change > 0 else 'decrease'

                    # Log the alert
                    db.log_alert(
                        user_id=user_id,
                        crypto_id=crypto_id,
                        trigger_price=current_price,
                        percent_change=percent_change,
                        alert_type=alert_type
                    )

                    # Check user preferences
                    preferences = db.get_user_preferences(user_id)
                    if preferences and preferences.get('email_alerts_enabled', True):
                        # Get user email from Supabase Auth
                        user_email = db.get_user_email(user_id)
                        if not user_email:
                            logger.warning(
                                f"Could not get email for user {user_id}")
                            continue

                        crypto_info = item['cryptos']
                        crypto_name = crypto_info['name']
                        crypto_symbol = crypto_info['symbol']

                        # Send alert email
                        from config import Config
                        email_sent = email_service.send_price_alert(
                            to_email=user_email,
                            crypto_name=crypto_name,
                            crypto_symbol=crypto_symbol,
                            current_price=current_price,
                            percent_change=percent_change,
                            alert_type=alert_type,
                            dashboard_url=Config.APP_URL
                        )

                        if email_sent:
                            results['emails_sent'] += 1
                            logger.info(
                                f"Alert sent for {crypto_symbol}: {percent_change:+.2f}%")

            except Exception as e:
                error_msg = f"Error checking alert: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)

        logger.info(
            f"Alert check completed. Checked: {results['checked']}, Triggered: {results['triggered']}, Emails sent: {results['emails_sent']}")

    except Exception as e:
        logger.error(f"Fatal error in alert check: {e}")
        results['errors'].append(f"Fatal error: {str(e)}")

    return results


def check_alerts_for_user(user_id: str):
    """
    Check alerts for a specific user
    """
    logger.info(f"Checking alerts for user {user_id}...")

    triggered_alerts = []

    try:
        watchlist = db.get_user_watchlist(user_id)

        for item in watchlist:
            crypto_id = item['crypto_id']
            alert_percent = float(item['alert_percent'])

            # Get price change
            current_price = item.get('current_price', 0)
            change_24h = item.get('change_24h', 0)

            if abs(change_24h) >= alert_percent:
                triggered_alerts.append({
                    'crypto_name': item['cryptos']['name'],
                    'crypto_symbol': item['cryptos']['symbol'],
                    'current_price': current_price,
                    'percent_change': change_24h,
                    'alert_type': 'increase' if change_24h > 0 else 'decrease'
                })

        return triggered_alerts

    except Exception as e:
        logger.error(f"Error checking alerts for user {user_id}: {e}")
        return []


if __name__ == '__main__':
    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run alert check
    check_all_alerts()
