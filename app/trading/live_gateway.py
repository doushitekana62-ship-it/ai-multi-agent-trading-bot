from app.indodax.client import IndodaxClient
from app.indodax.models import OrderResult
from app.trading.gateway import TradingGateway


class LiveGateway(TradingGateway):
    mode = "live"

    def __init__(self):
        self.client = IndodaxClient()

    def buy(self, symbol, price, quantity, client_order_id=None):
        data = self.client.trade(symbol, "buy", price, quantity, client_order_id=client_order_id)
        order_id = str(data.get("return", {}).get("order_id", data.get("order_id", "")))
        if not order_id:
            raise RuntimeError("Indodax buy returned no order id")
        return OrderResult(order_id, symbol, "buy", quantity, price, 0.0, "live")

    def sell(self, symbol, price, quantity, client_order_id=None):
        data = self.client.trade(symbol, "sell", price, quantity, client_order_id=client_order_id)
        order_id = str(data.get("return", {}).get("order_id", data.get("order_id", "")))
        if not order_id:
            raise RuntimeError("Indodax sell returned no order id")
        return OrderResult(order_id, symbol, "sell", quantity, price, 0.0, "live")
