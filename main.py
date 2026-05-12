import asyncio
import hmac
import hashlib
import time
import json
import websockets
import requests
import os

API_KEY = os.environ["BYBIT_API_KEY"]
API_SECRET = os.environ["BYBIT_API_SECRET"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"})

def get_signature(secret, params_str):
    return hmac.new(secret.encode(), params_str.encode(), hashlib.sha256).hexdigest()

async def connect():
    uri = "wss://stream.bybit.com/v5/private"
    
    while True:
        try:
            async with websockets.connect(uri) as ws:
                expires = int((time.time() + 10) * 1000)
                sign_str = f"GET/realtime{expires}"
                signature = get_signature(API_SECRET, sign_str)
                
                auth = {"op": "auth", "args": [API_KEY, expires, signature]}
                await ws.send(json.dumps(auth))
                await asyncio.sleep(1)
                
                subscribe = {"op": "subscribe", "args": ["position", "execution"]}
                await ws.send(json.dumps(subscribe))
                print("✅ Подключено к Bybit WebSocket")
                
                async for message in ws:
                    data = json.loads(message)
                    await handle_message(data)
                    
        except Exception as e:
            print(f"Ошибка: {e}, переподключение через 5 сек...")
            await asyncio.sleep(5)

async def handle_message(data):
    if "topic" not in data:
        return
    
    if data["topic"] == "execution":
        for item in data["data"]:
            side = "🟢 ПОКУПКА" if item["side"] == "Buy" else "🔴 ПРОДАЖА"
            text = (
                f"<b>⚡ СДЕЛКА ИСПОЛНЕНА</b>\n"
                f"Пара: <b>{item['symbol']}</b>\n"
                f"Направление: {side}\n"
                f"Цена: <b>${float(item['execPrice']):,.2f}</b>\n"
                f"Количество: <b>{item['execQty']}</b>\n"
                f"Тип: {item['orderType']}"
            )
            send_telegram(text)
    
    if data["topic"] == "position":
        for item in data["data"]:
            if float(item["size"]) == 0:
                text = (
                    f"<b>🔒 ПОЗИЦИЯ ЗАКРЫТА</b>\n"
                    f"Пара: <b>{item['symbol']}</b>\n"
                    f"PnL: <b>{item['unrealisedPnl']} USDT</b>"
                )
            else:
                side = "🟢 LONG" if item["side"] == "Buy" else "🔴 SHORT"
                text = (
                    f"<b>📊 ПОЗИЦИЯ ОТКРЫТА</b>\n"
                    f"Пара: <b>{item['symbol']}</b>\n"
                    f"Направление: {side}\n"
                    f"Размер: <b>{item['size']}</b>\n"
                    f"Цена входа: <b>${float(item['avgPrice']):,.2f}</b>\n"
                    f"Плечо: {item['leverage']}x"
                )
            send_telegram(text)

asyncio.run(connect())
