"""
Background task scheduler using APScheduler
Runs daily tasks for price scraping, alert checking, and email summaries
"""
import atexit
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from tasks import (check_all_alerts, scrape_all_crypto_prices,
                   send_all_daily_summaries)

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Scheduler for background tasks"""

    def __init__(self):
        self.scheduler = BackgroundScheduler(daemon=True)
        self.scheduler.start()

        # Shutdown scheduler when the app exits
        atexit.register(lambda: self.scheduler.shutdown())

        logger.info("Task scheduler initialized")

    def schedule_daily_price_scrape(self, hour: int = 0, minute: int = 0):
        """
        Schedule daily price scraping
        Default: midnight UTC
        """
        self.scheduler.add_job(
            func=scrape_all_crypto_prices,
            trigger=CronTrigger(hour=hour, minute=minute),
            id='daily_price_scrape',
            name='Daily Price Scrape',
            replace_existing=True
        )
        logger.info(
            f"Scheduled daily price scrape at {hour:02d}:{minute:02d} UTC")

    def schedule_alert_check(self, hour: int = 8, minute: int = 0):
        """
        Schedule daily alert checking
        Default: 8:00 AM UTC
        """
        self.scheduler.add_job(
            func=check_all_alerts,
            trigger=CronTrigger(hour=hour, minute=minute),
            id='daily_alert_check',
            name='Daily Alert Check',
            replace_existing=True
        )
        logger.info(
            f"Scheduled daily alert check at {hour:02d}:{minute:02d} UTC")

    def schedule_daily_email_summary(self, hour: int = 9, minute: int = 0):
        """
        Schedule daily email summaries
        Default: 9:00 AM UTC
        """
        self.scheduler.add_job(
            func=send_all_daily_summaries,
            trigger=CronTrigger(hour=hour, minute=minute),
            id='daily_email_summary',
            name='Daily Email Summary',
            replace_existing=True
        )
        logger.info(
            f"Scheduled daily email summary at {hour:02d}:{minute:02d} UTC")

    def schedule_hourly_price_update(self):
        """
        Schedule hourly price updates (more frequent scraping)
        Runs every hour on the hour
        """
        self.scheduler.add_job(
            func=scrape_all_crypto_prices,
            trigger=CronTrigger(minute=0),
            id='hourly_price_update',
            name='Hourly Price Update',
            replace_existing=True
        )
        logger.info("Scheduled hourly price updates")

    def schedule_all_default_tasks(self):
        """
        Schedule all tasks with default times:
        - Hourly price updates
        - Daily alert check at 8:00 AM UTC
        - Daily email summary at 9:00 AM UTC
        """
        self.schedule_hourly_price_update()
        self.schedule_alert_check(hour=8, minute=0)
        self.schedule_daily_email_summary(hour=9, minute=0)

        logger.info("All default tasks scheduled")

    def list_jobs(self):
        """List all scheduled jobs"""
        jobs = self.scheduler.get_jobs()
        job_list = []

        for job in jobs:
            job_list.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None
            })

        return job_list

    def remove_job(self, job_id: str):
        """Remove a scheduled job"""
        self.scheduler.remove_job(job_id)
        logger.info(f"Removed job: {job_id}")

    def pause(self):
        """Pause the scheduler"""
        self.scheduler.pause()
        logger.info("Scheduler paused")

    def resume(self):
        """Resume the scheduler"""
        self.scheduler.resume()
        logger.info("Scheduler resumed")

    def shutdown(self):
        """Shutdown the scheduler"""
        self.scheduler.shutdown()
        logger.info("Scheduler shutdown")


task_scheduler = TaskScheduler()


if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Schedule all tasks
    task_scheduler.schedule_all_default_tasks()

    # Log scheduled jobs
    logger.info("\nScheduled Jobs:")
    logger.info("-" * 60)
    for job in task_scheduler.list_jobs():
        logger.info(f"{job['name']:<30} Next run: {job['next_run']}")
    logger.info("-" * 60)

    # Keep the script running
    try:
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("\nShutting down scheduler...")
        task_scheduler.shutdown()
