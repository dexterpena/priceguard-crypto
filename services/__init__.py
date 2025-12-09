# Services module
from .crypto_api import CryptoAPIService, crypto_api
from .email_service import EmailService, email_service
from .ml_model import PricePredictionModel, create_price_prediction

__all__ = [
    'crypto_api', 'CryptoAPIService',
    'email_service', 'EmailService',
    'PricePredictionModel', 'create_price_prediction'
]
