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

    # Resend
    RESEND_API_KEY = os.getenv('RESEND_API_KEY')
    RESEND_FROM_EMAIL = os.getenv(
        'RESEND_FROM_EMAIL', 'noreply@priceguard.com')

    # Crypto API
    CRYPTO_API_BASE_URL = os.getenv(
        'CRYPTO_API_BASE_URL', 'https://api.freecryptoapi.com/v1')
    COINDESK_API_KEY = os.getenv('COINDESK_API')

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
