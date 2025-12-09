import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeRegressor

matplotlib.use('Agg')  # Use non-interactive backend


logger = logging.getLogger(__name__)


class PricePredictionModel:
    """
    Machine Learning model for cryptocurrency price prediction
    Uses Linear Regression or Decision Tree Regressor
    """

    def __init__(self, model_type: str = 'linear'):
        """
        Initialize prediction model

        Args:
            model_type: 'linear' for Linear Regression or 'tree' for Decision Tree
        """
        self.model_type = model_type

        if model_type == 'linear':
            self.model = LinearRegression()
        elif model_type == 'tree':
            self.model = DecisionTreeRegressor(max_depth=5, random_state=42)
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        self.is_trained = False
        self.metrics = {}

    def prepare_features(self, price_history: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare features from price history

        Features:
        - Day number (sequential)
        - 7-day moving average
        - Price change from previous day
        - Rolling volatility

        Returns:
            X (features), y (target prices)
        """
        if len(price_history) < 7:
            raise ValueError("Need at least 7 days of price history")

        # Convert to DataFrame
        df = pd.DataFrame(price_history)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        df['day_number'] = range(len(df))

        # Calculate features
        df['ma_7'] = df['price'].rolling(window=7, min_periods=1).mean()
        df['price_change'] = df['price'].diff().fillna(0)
        df['volatility'] = df['price'].rolling(
            window=7, min_periods=1).std().fillna(0)

        # Prepare feature matrix
        features = ['day_number', 'ma_7', 'price_change', 'volatility']
        X = df[features].values
        y = df['price'].values

        return X, y, df

    def train(self, price_history: List[Dict]) -> Dict:
        """
        Train the model on historical price data

        Returns:
            Dictionary with training metrics (RMSE, MAE, R²)
        """
        try:
            X, y, df = self.prepare_features(price_history)

            # Split data for evaluation
            if len(X) > 20:
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=0.2, shuffle=False
                )
            else:
                X_train, X_test, y_train, y_test = X, X, y, y

            # Train model
            self.model.fit(X_train, y_train)
            self.is_trained = True

            # Evaluate
            y_pred = self.model.predict(X_test)

            rmse = np.sqrt(mean_squared_error(y_test, y_pred))
            mae = mean_absolute_error(y_test, y_pred)

            # R² score
            from sklearn.metrics import r2_score
            r2 = r2_score(y_test, y_pred)

            self.metrics = {
                'rmse': float(rmse),
                'mae': float(mae),
                'r2_score': float(r2),
                'training_samples': len(X_train),
                'test_samples': len(X_test)
            }

            logger.info(
                f"Model trained successfully. RMSE: {rmse:.2f}, MAE: {mae:.2f}, R²: {r2:.3f}")

            return self.metrics

        except Exception as e:
            logger.error(f"Error training model: {e}")
            raise

    def predict_next_days(self, price_history: List[Dict], days: int = 7) -> List[Dict]:
        """
        Predict prices for the next N days

        Returns:
            List of predictions with dates and predicted prices
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before making predictions")

        try:
            X, y, df = self.prepare_features(price_history)

            # Get last known values
            last_day = df['day_number'].iloc[-1]
            last_ma = df['ma_7'].iloc[-1]
            last_price_change = df['price_change'].iloc[-1]
            last_volatility = df['volatility'].iloc[-1]
            last_timestamp = df['timestamp'].iloc[-1]

            predictions = []

            # Predict iteratively
            for i in range(1, days + 1):
                # Prepare features for next day
                next_day = last_day + i

                # Use last known moving average (simplified)
                next_features = np.array([[
                    next_day,
                    last_ma,
                    last_price_change,
                    last_volatility
                ]])

                # Predict
                predicted_price = self.model.predict(next_features)[0]

                # Update moving averages for next iteration (simplified)
                last_ma = (last_ma * 6 + predicted_price) / 7

                # Add to predictions
                prediction_date = last_timestamp + timedelta(days=i)
                predictions.append({
                    'date': prediction_date.strftime('%Y-%m-%d'),
                    'predicted_price': float(predicted_price),
                    'day_offset': i
                })

            return predictions

        except Exception as e:
            logger.error(f"Error making predictions: {e}")
            raise

    def plot_predictions(self, price_history: List[Dict], predictions: List[Dict],
                         crypto_symbol: str, output_path: str) -> str:
        """
        Create a plot comparing historical prices and predictions

        Returns:
            Path to the saved plot image
        """
        try:
            # Prepare historical data
            df_history = pd.DataFrame(price_history)
            df_history['timestamp'] = pd.to_datetime(df_history['timestamp'])
            df_history = df_history.sort_values('timestamp')

            # Prepare prediction data
            df_pred = pd.DataFrame(predictions)
            df_pred['date'] = pd.to_datetime(df_pred['date'])

            # Create plot
            plt.figure(figsize=(12, 6))

            # Plot historical prices
            plt.plot(df_history['timestamp'], df_history['price'],
                     marker='o', linestyle='-', linewidth=2, markersize=4,
                     label='Historical Prices', color='#3b82f6')

            # Plot predictions
            plt.plot(df_pred['date'], df_pred['predicted_price'],
                     marker='s', linestyle='--', linewidth=2, markersize=4,
                     label='Predicted Prices', color='#10b981')

            # Formatting
            plt.title(f'{crypto_symbol} Price History and Predictions',
                      fontsize=16, fontweight='bold')
            plt.xlabel('Date', fontsize=12)
            plt.ylabel('Price (USD)', fontsize=12)
            plt.legend(loc='best', fontsize=10)
            plt.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            plt.tight_layout()

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Save plot
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()

            logger.info(f"Prediction plot saved to {output_path}")

            return output_path

        except Exception as e:
            logger.error(f"Error creating prediction plot: {e}")
            raise

    def get_model_info(self) -> Dict:
        """Get model information and metrics"""
        return {
            'model_type': self.model_type,
            'is_trained': self.is_trained,
            'metrics': self.metrics
        }


def create_price_prediction(price_history: List[Dict], crypto_symbol: str,
                            prediction_days: int = 7, model_type: str = 'linear',
                            output_dir: str = 'static/predictions') -> Dict:
    """
    Convenience function to create a complete price prediction

    Returns:
        {
            'predictions': List[Dict],
            'metrics': Dict,
            'plot_path': str
        }
    """
    try:
        # Create model
        model = PricePredictionModel(model_type=model_type)

        # Train
        metrics = model.train(price_history)

        # Predict
        predictions = model.predict_next_days(
            price_history, days=prediction_days)

        # Create plot
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        plot_filename = f"{crypto_symbol}_{timestamp}.png"
        plot_path = os.path.join(output_dir, plot_filename)

        model.plot_predictions(price_history, predictions,
                               crypto_symbol, plot_path)

        return {
            'predictions': predictions,
            'metrics': metrics,
            'plot_path': plot_path,
            'model_type': model_type
        }

    except Exception as e:
        logger.error(f"Error creating price prediction: {e}")
        raise
