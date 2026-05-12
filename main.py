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
    
    try:
        if data["topic"] == "execution":
            for item in data["data"]:
                side = "🟢 ПОКУПКА" if item.get("side") == "Buy" else "🔴 ПРОДАЖА"
                price = item.get("execPrice", "—")
                qty = item.get("execQty", "—")
                symbol = item.get("symbol", "—")
                order_type = item.get("orderType", "—")
                try:
                    price_fmt = f"${float(price):,.2f}"
                except:
                    price_fmt = price
                text = (
                    f"<b>⚡ СДЕЛКА ИСПОЛНЕНА</b>\n"
                    f"Пара: <b>{symbol}</b>\n"
                    f"Направление: {side}\n"
                    f"Цена: <b>{price_fmt}</b>\n"
                    f"Количество: <b>{qty}</b>\n"
                    f"Тип: {order_type}"
                )
                send_telegram(text)
        
        if data["topic"] == "position":
            for item in data["data"]:
                symbol = item.get("symbol", "—")
                size = item.get("size", "0")
                side = item.get("side", "")
                avg_price = item.get("avgPrice") or item.get("entryPrice") or "—"
                leverage = item.get("leverage", "—")
                pnl = item.get("unrealisedPnl", "—")
                
                if str(size) == "0":
                    text = (
                        f"<b>🔒 ПОЗИЦИЯ ЗАКРЫТА</b>\n"
                        f"Пара: <b>{symbol}</b>\n"
                        f"PnL: <b>{pnl} USDT</b>"
                    )
                else:
                    side_text = "🟢 LONG" if side == "Buy" else "🔴 SHORT"
                    try:
                        price_fmt = f"${float(avg_price):,.2f}"
                    except:
                        price_fmt = avg_price
                    text = (
                        f"<b>📊 ПОЗИЦИЯ ОТКРЫТА</b>\n"
                        f"Пара: <b>{symbol}</b>\n"
                        f"Направление: {side_text}\n"
                        f"Размер: <b>{size}</b>\n"
                        f"Цена входа: <b>{price_fmt}</b>\n"
                        f"Плечо: {leverage}x"
                    )
                send_telegram(text)
    
    except Exception as e:
        print(f"Ошибка обработки: {e} | Данные: {data}")

asyncio.run(connect())
