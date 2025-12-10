import logging
import os
from datetime import datetime
from functools import wraps

import requests
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS

from config import Config
from database import db
from services import create_price_prediction, crypto_api, email_service
from services.popular_cryptos_cache import popular_cryptos_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Ensure static directories exist
os.makedirs('static/charts', exist_ok=True)
os.makedirs('static/predictions', exist_ok=True)


def get_user_from_header():
    """Extract user ID from Authorization header (Supabase JWT)"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None

    token = auth_header.split(' ')[1]

    try:
        import jwt

        # For development: decode without verification to test
        # In production, you should verify the signature properly
        payload = jwt.decode(
            token,
            options={"verify_signature": False}
        )
        logger.info(f"JWT decoded successfully for user: {payload.get('sub')}")
        return payload.get('sub')
    except Exception as e:
        logger.error(f"JWT validation error: {e}")
        return None


def get_user_from_token():
    """Extract user ID from token - checks both header and query params"""
    # First try header
    user_id = get_user_from_header()
    if user_id:
        return user_id

    token = request.args.get('token')
    if not token:
        return None

    try:
        import jwt
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload.get('sub')
    except:
        return None


def get_email_from_token():
    """Extract user email from JWT if present (no verification)"""
    auth_header = request.headers.get('Authorization')
    token = None
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
    else:
        token = request.args.get('token')

    if not token:
        return None

    try:
        import jwt
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload.get('email') or payload.get('sub')
    except Exception as e:
        logger.warning(f"Failed to read email from token: {e}")
        return None


def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = get_user_from_token()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(user_id, *args, **kwargs)
    return decorated_function


# Frontend Routes

@app.route('/')
def index():
    """Serve the main dashboard"""
    return render_template('index.html')


@app.route('/login')
def login_page():
    """Serve the login page"""
    return render_template('login.html')


@app.route('/register')
def register_page():
    """Serve the registration page"""
    return render_template('register.html')


@app.route('/preferences')
def preferences_page():
    """Serve the preferences page"""
    return render_template('preferences.html')


# Authentication Routes

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    """Register a new user"""
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400

        # Sign up with Supabase Auth
        response = db.client.auth.sign_up({
            "email": email,
            "password": password
        })

        return jsonify({
            'message': 'User registered successfully',
            'user': {'email': email}
        }), 201

    except Exception as e:
        logger.error(f"Signup error: {e}")
        error_msg = str(e)
        if 'already registered' in error_msg.lower():
            return jsonify({'error': 'Email already registered'}), 400
        return jsonify({'error': error_msg}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400

        # Sign in with Supabase Auth
        response = db.client.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if not response.user:
            return jsonify({'error': 'Invalid credentials'}), 401

        return jsonify({
            'message': 'Login successful',
            'token': response.session.access_token,
            'user': {
                'id': response.user.id,
                'email': response.user.email
            }
        }), 200

    except Exception as e:
        logger.error(f"Login error: {e}")
        error_msg = str(e)
        if 'invalid' in error_msg.lower() or 'credentials' in error_msg.lower():
            return jsonify({'error': 'Invalid email or password'}), 401
        return jsonify({'error': 'Login failed. Please try again.'}), 401


# Crypto Routes

@app.route('/api/cryptos', methods=['GET'])
def get_cryptos():
    """Get all available cryptocurrencies"""
    try:
        cryptos = db.get_all_cryptos()
        return jsonify(cryptos), 200
    except Exception as e:
        logger.error(f"Error getting cryptos: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cryptos/top', methods=['GET'])
def get_top_cryptos():
    """Get top cryptocurrencies from cache"""
    try:
        limit = request.args.get('limit', 10, type=int)

        logger.info(f"Fetching top {limit} cryptocurrencies from cache")

        # Get all cached cryptos (already sorted by market cap)
        all_cryptos = popular_cryptos_cache.get_all_cached_cryptos()

        # Return only the requested limit
        top_cryptos = all_cryptos[:limit]

        # Format response to match expected structure
        formatted_cryptos = []
        for crypto in top_cryptos:
            formatted_cryptos.append({
                'id': crypto['api_id'],
                'symbol': crypto['symbol'],
                'name': crypto['name'],
                'logo_url': crypto.get('logo_url', ''),
                'price': float(crypto['price']),
                'market_cap': float(crypto.get('market_cap', 0)),
                'volume_24h': float(crypto.get('volume_24h', 0)),
                'change_24h': float(crypto.get('change_24h', 0))
            })

        return jsonify({
            'success': True,
            'data': formatted_cryptos,
            'count': len(formatted_cryptos),
            'from_cache': True
        }), 200

    except Exception as e:
        logger.error(f"Error getting top cryptos: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cryptos/search', methods=['GET'])
def search_cryptos():
    """Search for cryptocurrencies in cache first, then API"""
    try:
        query = request.args.get('q', '').upper()
        if not query:
            return jsonify([]), 200

        # Search in cached cryptos first
        all_cached = popular_cryptos_cache.get_all_cached_cryptos()
        results = []

        for crypto in all_cached:
            if (query in crypto['symbol'].upper() or
                    query in crypto['name'].upper()):
                results.append({
                    'id': crypto['api_id'],
                    'symbol': crypto['symbol'],
                    'name': crypto['name'],
                    'logo_url': crypto.get('logo_url', ''),
                    'price': float(crypto['price'])
                })

        # If no results in cache, fall back to API search
        if not results:
            api_results = crypto_api.search_crypto(query)
            results = api_results

        return jsonify(results), 200

    except Exception as e:
        logger.error(f"Error searching cryptos: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cryptos/<symbol>/price', methods=['GET'])
def get_crypto_price(symbol):
    """Get current price for a cryptocurrency"""
    try:
        price_data = crypto_api.get_crypto_price(symbol)
        if not price_data:
            return jsonify({'error': 'Crypto not found'}), 404

        return jsonify(price_data), 200

    except Exception as e:
        logger.error(f"Error getting crypto price: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cryptos/prices', methods=['POST'])
def get_multiple_crypto_prices():
    """Get current prices for multiple cryptocurrencies"""
    try:
        data = request.json
        logger.info(f"Received data: {data}, type: {type(data)}")

        # Handle both list and object with symbols key
        if isinstance(data, list):
            symbols = data
        elif isinstance(data, dict):
            symbols = data.get('symbols', [])
        else:
            symbols = []

        # Ensure symbols is a list
        if isinstance(symbols, str):
            symbols = [s.strip() for s in symbols.split(',')]

        logger.info(f"Processing symbols: {symbols}")

        if not symbols:
            return jsonify({'error': 'Symbols required'}), 400

        prices = crypto_api.get_multiple_crypto_prices(symbols)
        return jsonify(prices), 200

    except Exception as e:
        logger.error(f"Error getting multiple crypto prices: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cryptos/<symbol>/history', methods=['GET'])
def get_crypto_history(symbol):
    """Get historical price data from CoinDesk API"""
    try:
        days_param = request.args.get('days', '1', type=str)

        # Determine unit and limit based on days parameter
        if days_param == 'max':
            days = 365  # CoinDesk max limit for days
            unit = 'days'
        elif days_param == '1':
            # For 24h view, use hours endpoint
            days = 24
            unit = 'hours'
        else:
            days = int(days_param)
            unit = 'days'

        logger.info(
            f"Fetching history for {symbol} for {days} {unit} from CoinDesk")

        # Fetch from CoinDesk API
        historical_data = crypto_api.get_historical_data(symbol, days, unit)

        if not historical_data:
            return jsonify({'error': 'No data available'}), 404

        prices = []
        market_caps = []
        total_volumes = []
        ohlc_data = []

        for item in historical_data:
            timestamp = datetime.fromisoformat(
                item['timestamp'].replace('Z', '+00:00'))
            timestamp_ms = int(timestamp.timestamp() * 1000)

            prices.append([timestamp_ms, item['price']])
            market_caps.append([timestamp_ms, item['market_cap']])
            total_volumes.append([timestamp_ms, item['volume_24h']])

            # Include OHLC data for additional info
            ohlc_data.append({
                'timestamp': timestamp_ms,
                'open': item.get('open', item['price']),
                'high': item.get('high', item['price']),
                'low': item.get('low', item['price']),
                'close': item.get('close', item['price']),
                'volume': item['volume_24h']
            })

        response_data = {
            'prices': prices,
            'market_caps': market_caps,
            'total_volumes': total_volumes,
            'ohlc': ohlc_data  # Extra data for displaying stats
        }

        logger.info(f"Received {len(prices)} price points for {symbol}")
        return jsonify(response_data), 200

    except requests.exceptions.RequestException as e:
        logger.exception(
            f"Request error getting crypto history for {symbol}: {e}")
        return jsonify({'error': f'Failed to fetch data from CoinDesk: {str(e)}'}), 500
    except Exception as e:
        logger.exception(f"Error getting crypto history for {symbol}: {e}")
        return jsonify({'error': str(e)}), 500


# Watchlist Routes

@app.route('/api/watchlist', methods=['GET'])
@require_auth
def get_watchlist(user_id):
    """Get user's watchlist with crypto data"""
    try:
        watchlist = db.get_user_watchlist(user_id)

        # Evaluate alert thresholds and notify when triggered (respect preferences)
        try:
            prefs = db.get_user_preferences(user_id) or {}
            email_enabled = prefs.get('email_alerts_enabled', True)
            price_alerts_enabled = prefs.get('price_alerts_enabled', True)
            user_email = (
                db.get_user_email(user_id) or get_email_from_token()
            ) if email_enabled else None

            if email_enabled and price_alerts_enabled and user_email:
                for item in watchlist:
                    change = item.get('change_24h', 0) or 0
                    threshold = item.get('alert_percent', 0) or 0
                    api_crypto_id = item.get('api_crypto_id')
                    symbol = item.get('symbol', '')
                    name = item.get('name', symbol)

                    if threshold and abs(change) >= threshold and api_crypto_id:
                        if not db.has_recent_alert(user_id, api_crypto_id):
                            alert_type = 'increase' if change >= threshold else 'decrease'
                            email_service.send_price_alert(
                                to_email=user_email,
                                crypto_name=name,
                                crypto_symbol=symbol,
                                current_price=item.get('current_price', 0),
                                percent_change=change,
                                alert_type=alert_type,
                                dashboard_url=Config.APP_URL
                            )
                            db.log_alert(
                                user_id=user_id,
                                api_crypto_id=api_crypto_id,
                                symbol=symbol,
                                name=name,
                                trigger_price=item.get('current_price', 0),
                                percent_change=change,
                                alert_type=alert_type
                            )
        except Exception as alert_err:
            logger.warning(f"Alert notification check failed: {alert_err}")

        return jsonify(watchlist), 200
    except Exception as e:
        logger.error(f"Error getting watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/watchlist/ids', methods=['GET'])
@require_auth
def get_watchlist_ids(user_id):
    """Get list of api_crypto_ids user is watching (for UI state)"""
    try:
        watched_ids = db.get_user_watched_crypto_ids(user_id)
        return jsonify({'watched_ids': watched_ids}), 200
    except Exception as e:
        logger.error(f"Error getting watchlist IDs: {e}")
        return jsonify({'error': str(e)}), 500


# Preferences Routes

@app.route('/api/preferences', methods=['GET'])
@require_auth
def get_preferences(user_id):
    """Get user preferences"""
    try:
        prefs = db.get_user_preferences(user_id)
        return jsonify(prefs or {}), 200
    except Exception as e:
        logger.error(f"Error getting preferences: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/preferences', methods=['POST'])
@require_auth
def update_preferences(user_id):
    """Update user preferences"""
    try:
        data = request.json or {}
        email_alerts_enabled = data.get('email_alerts_enabled')
        watchlist_alerts_enabled = data.get('watchlist_alerts_enabled')
        price_alerts_enabled = data.get('price_alerts_enabled')
        daily_summary_enabled = data.get('daily_summary_enabled')

        success = db.update_user_preferences(
            user_id,
            email_alerts_enabled=email_alerts_enabled,
            watchlist_alerts_enabled=watchlist_alerts_enabled,
            price_alerts_enabled=price_alerts_enabled,
            daily_summary_enabled=daily_summary_enabled
        )

        if not success:
            return jsonify({'error': 'Failed to update preferences'}), 400

        prefs = db.get_user_preferences(user_id)
        return jsonify(prefs or {}), 200
    except Exception as e:
        logger.error(f"Error updating preferences: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/watchlist/add', methods=['POST'])
@require_auth
def add_to_watchlist_route(user_id):
    """Add crypto to watchlist using new schema"""
    try:
        data = request.json
        symbol = data.get('symbol', '').upper()
        alert_percent = data.get('alert_percent', 5.0)
        # New: get API ID from request
        api_crypto_id = data.get('api_crypto_id')

        # Support both new (api_crypto_id) and old (symbol only) requests
        if not api_crypto_id and not symbol:
            return jsonify({'error': 'Symbol or API ID required'}), 400

        # Get crypto info from cache or API
        crypto_info = None

        if api_crypto_id:
            # Get from cache by API ID
            crypto_info = popular_cryptos_cache.get_cached_crypto(
                api_crypto_id)
            if crypto_info:
                symbol = crypto_info['symbol']

        if not crypto_info and symbol:
            # Try to find in cache by symbol
            all_cached = popular_cryptos_cache.get_all_cached_cryptos()
            for crypto in all_cached:
                if crypto['symbol'].upper() == symbol:
                    crypto_info = crypto
                    api_crypto_id = crypto['api_id']
                    break

        if not crypto_info:
            # Not in cache, need to fetch from API
            crypto_data = crypto_api.get_crypto_price(symbol)
            if not crypto_data:
                return jsonify({'error': f'Cryptocurrency {symbol} not found'}), 404

            # Try to get API ID from metadata
            watchlist_data = crypto_api.get_watchlist_data([symbol])
            if watchlist_data and symbol in watchlist_data:
                api_crypto_id = watchlist_data[symbol].get('id')

            if not api_crypto_id:
                return jsonify({'error': f'Could not determine API ID for {symbol}'}), 400

            crypto_info = {
                'api_id': api_crypto_id,
                'symbol': symbol,
                'name': crypto_data.get('name', symbol),
                'logo_url': crypto_data.get('logo_url', '')
            }

        # Check if already in watchlist
        if db.is_in_watchlist_by_api_id(user_id, api_crypto_id):
            return jsonify({'error': f'{symbol} is already in your watchlist'}), 400

        # Add to watchlist with cached info
        watchlist_item = db.add_to_watchlist(
            user_id=user_id,
            api_crypto_id=api_crypto_id,
            symbol=crypto_info['symbol'],
            name=crypto_info['name'],
            logo_url=crypto_info.get('logo_url', ''),
            alert_percent=alert_percent
        )

        if not watchlist_item:
            return jsonify({'error': 'Failed to add to watchlist'}), 500

        # Notify user of new watchlist item
        try:
            prefs = db.get_user_preferences(user_id) or {}
            if prefs.get('email_alerts_enabled', True) and prefs.get('watchlist_alerts_enabled', True):
                user_email = db.get_user_email(user_id) or get_email_from_token()
                if user_email:
                    email_service.send_watchlist_added(
                        to_email=user_email,
                        crypto_name=crypto_info['name'],
                        crypto_symbol=symbol,
                        alert_percent=alert_percent,
                    dashboard_url=Config.APP_URL
                )
        except Exception as notify_err:
            logger.warning(f"Watchlist add email failed: {notify_err}")

        logger.info(
            f"Added {symbol} (ID: {api_crypto_id}) to watchlist for user {user_id}")
        return jsonify(watchlist_item), 201

    except Exception as e:
        logger.exception(f"Error adding to watchlist: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/watchlist/<int:watch_id>', methods=['DELETE'])
@require_auth
def remove_from_watchlist(user_id, watch_id):
    """Remove crypto from watchlist"""
    try:
        # Fetch item before removal for email context
        item_details = db.client.table('watchlist').select(
            'symbol', 'name'
        ).eq('watch_id', watch_id).eq('user_id', user_id).limit(1).execute()
        removed_item = item_details.data[0] if item_details.data else None

        success = db.remove_from_watchlist(watch_id, user_id)
        if not success:
            return jsonify({'error': 'Failed to remove from watchlist'}), 400

        try:
            prefs = db.get_user_preferences(user_id) or {}
            if prefs.get('email_alerts_enabled', True) and prefs.get('watchlist_alerts_enabled', True):
                user_email = db.get_user_email(user_id) or get_email_from_token()
                if user_email and removed_item:
                    email_service.send_watchlist_removed(
                        to_email=user_email,
                        crypto_name=removed_item.get('name') or removed_item.get('symbol', ''),
                        crypto_symbol=removed_item.get('symbol', ''),
                        dashboard_url=Config.APP_URL
                    )
        except Exception as notify_err:
            logger.warning(f"Watchlist remove email failed: {notify_err}")

        return jsonify({'message': 'Removed from watchlist'}), 200

    except Exception as e:
        logger.error(f"Error removing from watchlist: {e}")
        return jsonify({'error': str(e)}), 500


# Price History Routes

@app.route('/api/history/<symbol>', methods=['GET'])
@require_auth
def get_price_history(user_id, symbol):
    """Get price history and predictions for a cryptocurrency"""
    try:
        prediction_days = request.args.get('days', 7, type=int)
        predict = request.args.get('predict', 'true').lower() == 'true'
        model_type = request.args.get('model_type', 'linear')

        # use 2x the prediction period (minimum 7 days)
        training_days = max(prediction_days * 2, 7)

        # Determine unit based on prediction period
        if prediction_days == 1:
            # use hourly data for 24h prediction
            unit = 'hours'
            training_periods = 48  # Use 48 hours to predict next 24 hours
        else:
            unit = 'days'
            training_periods = training_days

        logger.info(
            f"Fetching {training_periods} {unit} of data to predict next {prediction_days} days")

        # Get historical data from CoinDesk API
        historical_data = crypto_api.get_historical_data(
            symbol.upper(), training_periods, unit)

        if not historical_data:
            return jsonify({
                'symbol': symbol.upper(),
                'history': [],
                'predictions': None,
                'message': 'No historical data available'
            }), 200

        result = {
            'symbol': symbol.upper(),
            'name': symbol.upper(),
            'history': historical_data
        }

        # Generate predictions if requested
        if predict and len(historical_data) >= 7:
            try:
                prediction_result = create_price_prediction(
                    historical_data,
                    symbol.upper(),
                    prediction_days=prediction_days,
                    model_type=model_type
                )
                result['predictions'] = prediction_result['predictions']
                result['metrics'] = prediction_result['metrics']
                result['plot_url'] = f"/api/charts/{os.path.basename(prediction_result['plot_path'])}"
            except Exception as pred_error:
                logger.error(f"Prediction error: {pred_error}")
                result['predictions'] = None
                result['prediction_error'] = str(pred_error)
        else:
            result['predictions'] = None

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error getting price history: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/charts/<filename>')
def serve_chart(filename):
    """Serve generated chart images"""
    return send_from_directory('static/predictions', filename)


@app.route('/api/export/history/<symbol>', methods=['GET'])
@require_auth
def export_history_csv(user_id, symbol):
    """Export price history as CSV"""
    try:
        from utils import export_price_history_to_csv

        days = request.args.get('days', 30, type=int)

        # Get crypto
        crypto = db.get_crypto_by_symbol(symbol.upper())
        if not crypto:
            return jsonify({'error': 'Crypto not found'}), 404

        # Get price history
        history = db.get_price_history(crypto['crypto_id'], days)

        if not history:
            return jsonify({'error': 'No history available'}), 404

        # Generate CSV
        csv_data = export_price_history_to_csv(history, symbol.upper())

        # Return as downloadable file
        from flask import Response
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename={symbol}_history.csv'}
        )

    except Exception as e:
        logger.error(f"Error exporting history: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/watchlist', methods=['GET'])
@require_auth
def export_watchlist_csv(user_id):
    """Export user's watchlist as CSV"""
    try:
        from utils import export_watchlist_to_csv

        # Get watchlist
        watchlist = db.get_user_watchlist(user_id)

        if not watchlist:
            return jsonify({'error': 'Watchlist is empty'}), 404

        # Generate CSV
        csv_data = export_watchlist_to_csv(watchlist)

        # Return as downloadable file
        from flask import Response
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=my_watchlist.csv'}
        )

    except Exception as e:
        logger.error(f"Error exporting watchlist: {e}")
        return jsonify({'error': str(e)}), 500


# Alerts Routes

@app.route('/api/alerts/update', methods=['POST'])
@require_auth
def update_alert(user_id):
    """Update alert threshold for a watchlist item"""
    try:
        data = request.json
        watch_id = data.get('watch_id')
        alert_percent = data.get('alert_percent')

        if watch_id is None or alert_percent is None:
            return jsonify({'error': 'watch_id and alert_percent required'}), 400

        success = db.update_alert_threshold(watch_id, user_id, alert_percent)

        if not success:
            return jsonify({'error': 'Failed to update alert'}), 400

        return jsonify({'message': 'Alert updated successfully'}), 200

    except Exception as e:
        logger.error(f"Error updating alert: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts/history', methods=['GET'])
@require_auth
def get_alert_history(user_id):
    """Get user's alert history"""
    try:
        alerts = db.get_user_alerts(user_id)
        return jsonify(alerts), 200
    except Exception as e:
        logger.error(f"Error getting alert history: {e}")
        return jsonify({'error': str(e)}), 500


# Health Check

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    }), 200


# Error Handlers

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.info("Please check your .env file")

    # Run the app
    app.run(
        host='0.0.0.0',
        port=8000,
        debug=Config.FLASK_ENV == 'development'
    )
