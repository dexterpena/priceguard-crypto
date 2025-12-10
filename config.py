import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration"""

    # Flask
    SECRET_KEY = os.getenv(
        'FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')

    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
    SUPABASE_JWT_SECRET = os.getenv('SUPABASE_JWT_SECRET')

    # Resend
    RESEND_API_KEY = os.getenv('RESEND_API_KEY')
    RESEND_FROM_EMAIL = os.getenv(
        'RESEND_FROM_EMAIL', 'noreply@priceguard.com')

    # CoinDesk API
    COINDESK_API_URL = os.getenv(
        'COINDESK_API_URL', 'https://data-api.coindesk.com')
    COINDESK_API_KEY = os.getenv('COINDESK_API_KEY')

    # Application
    APP_URL = os.getenv('APP_URL', 'http://localhost:8000')

    # App Settings
    PREDICTION_DAYS = 7
    HISTORY_DAYS = 30

    @staticmethod
    def validate():
        """Validate required configuration"""
        required = [
            'SUPABASE_URL',
            'SUPABASE_KEY',
            'RESEND_API_KEY'
        ]
        missing = [key for key in required if not os.getenv(key)]
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}")
