from binance.client import Client
import pandas as pd
import plotly.graph_objects as go
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import os

# Clés API Binance (remplacez par vos propres clés)
api_key = 'VOTRE_API_KEY'
api_secret = 'VOTRE_API_SECRET'

client = Client(api_key, api_secret)

app = Flask(__name__)

# Variables globales
assets = []
data_cache = {}

# Charger la liste des assets
def load_assets():
    global assets
    with open('assets.txt', 'r') as file:
        assets = [line.strip() for line in file]

def save_assets():
    with open('assets.txt', 'w') as file:
        for asset in assets:
            file.write(f"{asset}\n")

def get_historical_data(symbol, interval, limit=5000):
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
        data_cache[asset] = get_historical_data(asset, '1h', 5000)

scheduler = BackgroundScheduler()
scheduler.add_job(func=update_data, trigger="interval", minutes=5)
scheduler.start()

@app.route('/')
def index():
    default_symbol = assets[0] if assets else 'BTCUSDT'
    interval = '1h'
    limit = 5000
    chart_type = 'candlestick'
    data = get_historical_data(default_symbol, interval, limit)
    plot_html = plot_candlestick(data, default_symbol)
    return render_template('index.html', assets=assets, plot_html=plot_html, default_symbol=default_symbol, default_interval=interval, default_limit=limit, default_chart_type=chart_type)

@app.route('/plot', methods=['POST'])
def plot():
    symbol = request.form['symbol']
    interval = request.form['interval']
    limit = int(request.form.get('limit', 5000))
    chart_type = request.form.get('chart_type', 'candlestick')
    data = get_historical_data(symbol, interval, limit)
    if chart_type == 'line':
        plot_html = plot_line(data, symbol)
    else:
        plot_html = plot_candlestick(data, symbol)
    return jsonify(plot_html=plot_html)

@app.route('/plot_ratio', methods=['POST'])
def plot_ratio_route():
    symbol1 = request.form['symbol1']
    symbol2 = request.form['symbol2']
    interval = request.form['interval']
    limit = int(request.form.get('limit', 5000))
    data1 = get_historical_data(symbol1, interval, limit)
    data2 = get_historical_data(symbol2, interval, limit)
    plot_html = plot_ratio(data1, data2, symbol1, symbol2)
    return jsonify(plot_html=plot_html)

@app.route('/refresh', methods=['POST'])
def refresh():
    update_data()
    return jsonify(success=True)

@app.route('/add_asset', methods=['POST'])
def add_asset():
    asset = request.form['asset']
    if asset not in assets:
        assets.append(asset)
        save_assets()
        update_data()
    return jsonify(success=True)

@app.route('/remove_asset', methods=['POST'])
def remove_asset():
    asset = request.form['asset']
    if asset in assets:
        assets.remove(asset)
        save_assets()
        update_data()
    return jsonify(success=True)

if __name__ == '__main__':
    load_assets()
    app.run(debug=True)
