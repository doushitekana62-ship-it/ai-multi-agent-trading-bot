from app.indodax.client import IndodaxClient
from app.indodax.models import OrderResult
from app.trading.gateway import TradingGateway

class LiveGateway(TradingGateway):
    mode = "live"
    def __init__(self): self.client = IndodaxClient()
    def buy(self, symbol, price, quantity):
        data = self.client.trade(symbol, "buy", price, quantity)
        order_id = str(data.get("return", {}).get("order_id", data.get("order_id", "")))
        return OrderResult(order_id, symbol, "buy", quantity, price, 0.0, "live")
    def sell(self, symbol, price, quantity):
        data = self.client.trade(symbol, "sell", price, quantity)
        order_id = str(data.get("return", {}).get("order_id", data.get("order_id", "")))
        return OrderResult(order_id, symbol, "sell", quantity, price, 0.0, "live")
