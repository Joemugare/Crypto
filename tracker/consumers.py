import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .utils import fetch_market_data  # make sure this returns a dict

class MarketTickerConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        # Send initial data
        market_data = fetch_market_data()
        await self.send(text_data=json.dumps({'market_data': market_data}))

    async def receive(self, text_data):
        # Can handle client messages if needed
        pass

    async def disconnect(self, close_code):
        pass
