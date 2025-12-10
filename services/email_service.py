import logging

import requests

from config import Config

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails via Resend API"""

    def __init__(self):
        self.api_key = Config.RESEND_API_KEY
        self.from_email = Config.RESEND_FROM_EMAIL
        self.api_url = "https://api.resend.com/emails"

    def send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        """Send an email using Resend API"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "from": self.from_email,
                "to": [to_email],
                "subject": subject,
                "html": html_content
            }

            response = requests.post(
                self.api_url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending email to {to_email}: {e}")
            return False

    def send_price_alert(self, to_email: str, crypto_name: str, crypto_symbol: str,
                         current_price: float, percent_change: float,
                         alert_type: str, dashboard_url: str) -> bool:
        """Send a price alert email"""

        change_direction = "increased" if alert_type == "increase" else "decreased"
        emoji = "📈" if alert_type == "increase" else "📉"
        color = "#10b981" if alert_type == "increase" else "#ef4444"

        subject = f"{emoji} Price Alert: {crypto_name} ({crypto_symbol}) {change_direction} by {abs(percent_change):.2f}%"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {color}; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9fafb; padding: 30px; border-radius: 0 0 5px 5px; }}
                .alert-box {{ background-color: white; padding: 20px; margin: 20px 0; border-left: 4px solid {color}; border-radius: 4px; }}
                .price {{ font-size: 32px; font-weight: bold; color: {color}; margin: 10px 0; }}
                .change {{ font-size: 24px; color: {color}; }}
                .button {{ display: inline-block; padding: 12px 24px; background-color: {color}; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                .footer {{ text-align: center; margin-top: 20px; color: #6b7280; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{emoji} Price Alert Triggered!</h1>
                </div>
                <div class="content">
                    <div class="alert-box">
                        <h2>{crypto_name} ({crypto_symbol})</h2>
                        <div class="price">${current_price:,.2f}</div>
                        <div class="change">{percent_change:+.2f}% {change_direction}</div>
                    </div>
                    <p>Your price alert threshold has been triggered for <strong>{crypto_name}</strong>.</p>
                    <p>The price has {change_direction} by <strong>{abs(percent_change):.2f}%</strong> in the last 24 hours.</p>
                    <a href="{dashboard_url}" class="button">View Dashboard</a>
                    <div class="footer">
                        <p>You're receiving this email because you set up price alerts on PriceGuard Crypto Tracker.</p>
                        <p>Manage your alerts in your dashboard settings.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, html_content)

    def send_watchlist_added(self, to_email: str, crypto_name: str, crypto_symbol: str,
                             alert_percent: float, dashboard_url: str) -> bool:
        """Send an email when a crypto is added to watchlist"""
        subject = f"✅ Added to Watchlist: {crypto_name} ({crypto_symbol})"
        html_content = f"""
        <p>{crypto_name} ({crypto_symbol}) was added to your PriceGuard watchlist.</p>
        <p>Alert threshold: {alert_percent:.2f}%</p>
        <p><a href="{dashboard_url}">View Dashboard</a></p>
        """
        return self.send_email(to_email, subject, html_content)

    def send_watchlist_removed(self, to_email: str, crypto_name: str, crypto_symbol: str,
                               dashboard_url: str) -> bool:
        """Send an email when a crypto is removed from watchlist"""
        subject = f"Removed from Watchlist: {crypto_name} ({crypto_symbol})"
        html_content = f"""
        <p>{crypto_name} ({crypto_symbol}) was removed from your PriceGuard watchlist.</p>
        <p><a href="{dashboard_url}">Open Dashboard</a></p>
        """
        return self.send_email(to_email, subject, html_content)

    def send_daily_summary(self, to_email: str, user_name: str, watchlist_summary: list[dict],
                           alerts_triggered: list[dict], dashboard_url: str) -> bool:
        """Send daily portfolio summary email"""

        subject = f"📊 Daily Crypto Summary - {len(watchlist_summary)} Assets"

        # Build watchlist table
        watchlist_rows = ""
        for item in watchlist_summary:
            change_color = "#10b981" if item['change_24h'] >= 0 else "#ef4444"
            change_symbol = "+" if item['change_24h'] >= 0 else ""

            watchlist_rows += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">
                    <strong>{item['name']}</strong><br>
                    <span style="color: #6b7280; font-size: 12px;">{item['symbol']}</span>
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; text-align: right;">
                    ${item['current_price']:,.2f}
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; text-align: right; color: {change_color}; font-weight: bold;">
                    {change_symbol}{item['change_24h']:.2f}%
                </td>
            </tr>
            """

        # Build alerts section
        alerts_section = ""
        if alerts_triggered:
            alerts_section = "<h3 style='color: #ef4444;'>🚨 Alerts Triggered Today</h3><ul>"
            for alert in alerts_triggered:
                alerts_section += f"<li><strong>{alert['crypto_name']}</strong> {alert['alert_type']} by {abs(alert['percent_change']):.2f}%</li>"
            alerts_section += "</ul>"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #3b82f6; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: #f9fafb; padding: 30px; border-radius: 0 0 5px 5px; }}
                table {{ width: 100%; background-color: white; border-collapse: collapse; margin: 20px 0; border-radius: 5px; overflow: hidden; }}
                th {{ background-color: #1f2937; color: white; padding: 12px; text-align: left; }}
                .button {{ display: inline-block; padding: 12px 24px; background-color: #3b82f6; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                .footer {{ text-align: center; margin-top: 20px; color: #6b7280; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 Your Daily Crypto Summary</h1>
                    <p>Hello {user_name}!</p>
                </div>
                <div class="content">
                    {alerts_section}
                    
                    <h3>Your Watchlist ({len(watchlist_summary)} assets)</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Asset</th>
                                <th style="text-align: right;">Price</th>
                                <th style="text-align: right;">24h Change</th>
                            </tr>
                        </thead>
                        <tbody>
                            {watchlist_rows}
                        </tbody>
                    </table>
                    
                    <a href="{dashboard_url}" class="button">View Full Dashboard</a>
                    
                    <div class="footer">
                        <p>Daily summary from PriceGuard Crypto Tracker</p>
                        <p>Manage your preferences in your dashboard settings.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, html_content)


# Singleton instance
email_service = EmailService()
