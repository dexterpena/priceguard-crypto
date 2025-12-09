"""Utility functions for data export and formatting"""
import csv
import io
from datetime import datetime, timezone
from typing import Dict, List


def export_price_history_to_csv(history: List[Dict], crypto_symbol: str) -> str:
    """
    Export price history to CSV format
    """
    output = io.StringIO()

    if not history:
        return ""

    # Define CSV columns
    fieldnames = ['timestamp', 'price',
                  'market_cap', 'volume_24h', 'change_24h']

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for record in history:
        writer.writerow({
            'timestamp': record.get('timestamp', ''),
            'price': record.get('price', 0),
            'market_cap': record.get('market_cap', 0),
            'volume_24h': record.get('volume_24h', 0),
            'change_24h': record.get('change_24h', 0)
        })

    return output.getvalue()


def export_predictions_to_csv(predictions: List[Dict], crypto_symbol: str) -> str:
    """
    Export ML predictions to CSV format
    """
    output = io.StringIO()

    if not predictions:
        return ""

    fieldnames = ['date', 'predicted_price', 'day_offset']

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for record in predictions:
        writer.writerow({
            'date': record.get('date', ''),
            'predicted_price': record.get('predicted_price', 0),
            'day_offset': record.get('day_offset', 0)
        })

    return output.getvalue()


def export_watchlist_to_csv(watchlist: List[Dict]) -> str:
    """
    Export user's watchlist to CSV format
    """
    output = io.StringIO()

    if not watchlist:
        return ""

    fieldnames = [
        'symbol', 'name', 'current_price', 'change_24h',
        'market_cap', 'alert_percent', 'date_added'
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for item in watchlist:
        crypto = item.get('cryptos', {})
        writer.writerow({
            'symbol': crypto.get('symbol', ''),
            'name': crypto.get('name', ''),
            'current_price': item.get('current_price', 0),
            'change_24h': item.get('change_24h', 0),
            'market_cap': item.get('market_cap', 0),
            'alert_percent': item.get('alert_percent', 0),
            'date_added': item.get('date_added', '')
        })

    return output.getvalue()


def format_price(price: float, decimals: int = 2) -> str:
    """
    Format price as USD currency
    """
    return f"${price:,.{decimals}f}"


def format_percent(value: float, decimals: int = 2, show_sign: bool = True) -> str:
    """
    Format percentage value
    """
    sign = '+' if value > 0 and show_sign else ''
    return f"{sign}{value:.{decimals}f}%"


def format_large_number(num: float) -> str:
    """
    Format large numbers with K, M, B, T suffixes
    """
    if num >= 1e12:
        return f"${num / 1e12:.2f}T"
    elif num >= 1e9:
        return f"${num / 1e9:.2f}B"
    elif num >= 1e6:
        return f"${num / 1e6:.2f}M"
    elif num >= 1e3:
        return f"${num / 1e3:.2f}K"
    else:
        return f"${num:.2f}"


def calculate_percent_change(old_price: float, new_price: float) -> float:
    """
    Calculate percentage change between two prices
    """
    if old_price == 0:
        return 0.0

    return ((new_price - old_price) / old_price) * 100


def get_price_trend(change: float) -> str:
    """
    Get trend indicator based on price change
    """
    if change > 0.1:
        return 'up'
    elif change < -0.1:
        return 'down'
    else:
        return 'stable'


def get_timestamp_str(dt: datetime = None) -> str:
    """
    Get formatted timestamp string
    """
    if dt is None:
        dt = datetime.now(timezone.utc)

    return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
