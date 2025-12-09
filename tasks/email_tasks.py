"""
Background task to send daily email summaries to users
"""
import logging

from database import db
from services import email_service
from tasks.alert_tasks import check_alerts_for_user

logger = logging.getLogger(__name__)


def send_all_daily_summaries():
    """
    Send daily email summaries to all users

    Returns:
        Dictionary with results
    """
    logger.info("Starting daily email summary task...")

    results = {
        'users_processed': 0,
        'emails_sent': 0,
        'errors': []
    }

    try:
        # Get all unique users with watchlist items
        watchlist_items = db.get_all_watchlist_items()

        if not watchlist_items:
            logger.info("No watchlist items found")
            return results

        # Group by user
        users = {}
        for item in watchlist_items:
            user_id = item['user_id']
            if user_id not in users:
                users[user_id] = []
            users[user_id].append(item)

        logger.info(f"Sending daily summaries to {len(users)} users...")

        for user_id, user_watchlist in users.items():
            try:
                results['users_processed'] += 1

                # Check user preferences
                preferences = db.get_user_preferences(user_id)
                if preferences and not preferences.get('daily_summary_enabled', True):
                    logger.info(
                        f"User {user_id[:8]}... has daily summary disabled")
                    continue

                # Prepare watchlist summary
                watchlist_summary = []
                for item in user_watchlist:
                    # Get latest price
                    latest_price = db.get_latest_price(item['crypto_id'])
                    if latest_price:
                        watchlist_summary.append({
                            'name': item['cryptos']['name'],
                            'symbol': item['cryptos']['symbol'],
                            'current_price': float(latest_price['price']),
                            'change_24h': float(latest_price.get('change_24h', 0)),
                            'market_cap': float(latest_price.get('market_cap', 0))
                        })

                if not watchlist_summary:
                    logger.warning(
                        f"No price data available for user {user_id[:8]}...")
                    continue

                # Check for triggered alerts today
                triggered_alerts = check_alerts_for_user(user_id)

                # Get user email from Supabase Auth
                user_email = db.get_user_email(user_id)
                if not user_email:
                    logger.warning(f"Could not get email for user {user_id}")
                    continue

                from config import Config

                # Send daily summary email
                email_sent = email_service.send_daily_summary(
                    to_email=user_email,
                    user_name=user_email.split('@')[0],
                    watchlist_summary=watchlist_summary,
                    alerts_triggered=triggered_alerts,
                    dashboard_url=Config.APP_URL
                )

                if email_sent:
                    results['emails_sent'] += 1
                    logger.info(f"Daily summary sent to {user_email}")

            except Exception as e:
                error_msg = f"Error sending summary to user {user_id[:8]}...: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)

        logger.info(
            f"Daily summary task completed. Processed: {results['users_processed']}, Sent: {results['emails_sent']}")

    except Exception as e:
        logger.error(f"Fatal error in daily summary task: {e}")
        results['errors'].append(f"Fatal error: {str(e)}")

    return results


def send_daily_summary_to_user(user_id: str):
    """
    Send daily summary to a specific user
    """
    try:
        # Get user's watchlist
        watchlist = db.get_user_watchlist(user_id)

        if not watchlist:
            logger.info(f"User {user_id[:8]}... has no watchlist items")
            return False

        # Prepare summary
        watchlist_summary = []
        for item in watchlist:
            watchlist_summary.append({
                'name': item['cryptos']['name'],
                'symbol': item['cryptos']['symbol'],
                'current_price': item.get('current_price', 0),
                'change_24h': item.get('change_24h', 0),
                'market_cap': item.get('market_cap', 0)
            })

        # Check for triggered alerts
        triggered_alerts = check_alerts_for_user(user_id)

        # Get user email from Supabase Auth
        user_email = db.get_user_email(user_id)
        if not user_email:
            logger.error(f"Could not get email for user {user_id}")
            return False

        from config import Config

        # Send email
        return email_service.send_daily_summary(
            to_email=user_email,
            user_name=user_email.split('@')[0],
            watchlist_summary=watchlist_summary,
            alerts_triggered=triggered_alerts,
            dashboard_url=Config.APP_URL
        )

    except Exception as e:
        logger.error(f"Error sending daily summary to user {user_id}: {e}")
        return False


if __name__ == '__main__':
    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run daily summary task
    send_all_daily_summaries()
