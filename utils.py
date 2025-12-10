"""Utility functions for data export and formatting"""
import csv
import io
from datetime import datetime, timezone


def export_price_history_to_csv(history: list[dict], crypto_symbol: str) -> str:
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


def export_watchlist_to_csv(watchlist: list[dict]) -> str:
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
