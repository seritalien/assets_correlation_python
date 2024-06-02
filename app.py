import os
import sys
import logging
from flask import Flask, jsonify, render_template, request
from binance.client import Client
from binance.exceptions import BinanceAPIException
import pandas as pd
import plotly.graph_objects as go
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
logger = logging.getLogger()

# Load environment variables from .env file if present
load_dotenv()

# Get API key and secret from environment variables
api_key = os.getenv('API_KEY')
api_secret = os.getenv('API_SECRET')

if not api_key or not api_secret:
    raise ValueError("API_KEY and API_SECRET environment variables are required")

logger.debug(f"API_KEY: {api_key[:4]}...")  # Mask part of the key for security
logger.debug(f"API_SECRET: {api_secret[:4]}...")  # Mask part of the secret for security

client = Client(api_key, api_secret)

app = Flask(__name__)

# Variables globales
assets = []
data_cache = {}
comparison_asset = None

# Charger la liste des assets
def load_assets():
    global assets
    if os.path.exists('assets.txt'):
        with open('assets.txt', 'r') as file:
            assets = [line.strip() for line in file]

def save_assets():
    with open('assets.txt', 'w') as file:
        for asset in assets:
            file.write(f"{asset}\n")

def get_historical_data(symbol, interval, limit=500):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    data = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 
        'close_time', 'quote_asset_volume', 'number_of_trades', 
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
    data[['open', 'high', 'low', 'close', 'volume']] = data[['open', 'high', 'low', 'close', 'volume']].astype(float)
    return data[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

def plot_candlestick(data, symbol):
    fig = go.Figure(data=[go.Candlestick(
        x=data['timestamp'],
        open=data['open'],
        high=data['high'],
        low=data['low'],
        close=data['close'],
        increasing_line_color='royalblue',
        decreasing_line_color='black'
    )])
    fig.update_layout(title=f'Historical Price Data for {symbol}', xaxis_title='Date', yaxis_title='Price', height=800)
    fig.update_yaxes(fixedrange=False)
    return fig.to_html()

def plot_line(data, symbol):
    fig = go.Figure(data=[go.Scatter(
        x=data['timestamp'],
        y=data['close'],
        line=dict(color='royalblue')
    )])
    fig.update_layout(title=f'Historical Price Data for {symbol}', xaxis_title='Date', yaxis_title='Price', height=800)
    fig.update_yaxes(fixedrange=False)
    return fig.to_html()

def plot_ratio(data1, data2, symbol1, symbol2):
    ratio = data1['close'] / data2['close']
    fig = go.Figure(data=[go.Scatter(
        x=data1['timestamp'],
        y=ratio,
        line=dict(color='royalblue')
    )])
    fig.update_layout(title=f'Ratio {symbol1}/{symbol2}', xaxis_title='Date', yaxis_title='Ratio', height=800)
    fig.update_yaxes(fixedrange=False)
    return fig.to_html()

def update_data():
    global data_cache
    for asset in assets:
        if '/' not in asset:
            data_cache[asset] = get_historical_data(asset, '1d', 500)
        else:
            asset1, asset2 = asset.split('/')
            data1 = get_historical_data(asset1, '1d', 500)
            data2 = get_historical_data(asset2, '1d', 500)
            data_cache[asset] = data1, data2

scheduler = BackgroundScheduler()
scheduler.add_job(func=update_data, trigger="interval", minutes=5)
scheduler.start()

@app.route('/')
def index():
    try:
        default_symbol = assets[0] if assets else 'BTCUSDT'
        interval = '1d'
        limit = 500
        chart_type = 'candlestick'
        if '/' in default_symbol:
            asset1, asset2 = default_symbol.split('/')
            data1 = get_historical_data(asset1, interval, limit)
            data2 = get_historical_data(asset2, interval, limit)
            plot_html = plot_ratio(data1, data2, asset1, asset2)
        else:
            data = get_historical_data(default_symbol, interval, limit)
            plot_html = plot_candlestick(data, default_symbol)
        return render_template('index.html', assets=assets, plot_html=plot_html, default_symbol=default_symbol, default_interval=interval, default_limit=limit, default_chart_type=chart_type)
    except Exception as e:
        logger.error(f"Error in index route: {e}")
        return "An error occurred", 500

@app.route('/plot', methods=['POST'])
def plot():
    try:
        symbol = request.form['symbol']
        interval = request.form['interval']
        limit = int(request.form.get('limit', 500))
        chart_type = request.form.get('chart_type', 'candlestick')
        if '/' in symbol:
            asset1, asset2 = symbol.split('/')
            data1 = get_historical_data(asset1, interval, limit)
            data2 = get_historical_data(asset2, interval, limit)
            plot_html = plot_ratio(data1, data2, asset1, asset2)
        else:
            data = get_historical_data(symbol, interval, limit)
            if chart_type == 'line':
                plot_html = plot_line(data, symbol)
            else:
                plot_html = plot_candlestick(data, symbol)
        return jsonify(plot_html=plot_html)
    except Exception as e:
        logger.error(f"Error in plot route: {e}")
        return jsonify(error=str(e)), 500

@app.route('/plot_ratio', methods=['POST'])
def plot_ratio_route():
    try:
        symbol1 = request.form['symbol1']
        symbol2 = request.form['symbol2']
        interval = request.form['interval']
        limit = int(request.form.get('limit', 500))
        data1 = get_historical_data(symbol1, interval, limit)
        data2 = get_historical_data(symbol2, interval, limit)
        comparison_asset = f"{symbol1}/{symbol2}"
        plot_html = plot_ratio(data1, data2, symbol1, symbol2)
        if comparison_asset not in assets:
            assets.append(comparison_asset)
            save_assets()
        return jsonify(plot_html=plot_html, comparison_asset=comparison_asset)
    except Exception as e:
        logger.error(f"Error in plot_ratio route: {e}")
        return jsonify(error=str(e)), 500

@app.route('/refresh', methods=['POST'])
def refresh():
    try:
        update_data()
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"Error in refresh route: {e}")
        return jsonify(error=str(e)), 500

@app.route('/add_asset', methods=['POST'])
def add_asset():
    asset = request.form['asset']
    try:
        get_historical_data(asset, '1d', 1)  # Test if the asset exists by fetching a single data point
        if asset not in assets:
            assets.append(asset)
            save_assets()
            update_data()
        return jsonify(success=True)
    except BinanceAPIException as e:
        logger.error(f"BinanceAPIException in add_asset route: {e}")
        return jsonify(success=False, error=str(e))
    except Exception as e:
        logger.error(f"Error in add_asset route: {e}")
        return jsonify(success=False, error=str(e))

@app.route('/remove_asset', methods=['POST'])
def remove_asset():
    asset = request.form['asset']
    try:
        if asset in assets:
            assets.remove(asset)
            save_assets()
            update_data()
        return jsonify(success=True)
    except Exception as e:
        logger.error(f"Error in remove_asset route: {e}")
        return jsonify(success=False, error=str(e))

if __name__ == '__main__':
    load_assets()
    app.run(debug=True)
