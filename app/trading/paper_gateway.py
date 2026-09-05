import uuid
from app.config import settings
from app.indodax.models import OrderResult
from app.trading.gateway import TradingGateway


class PaperGateway(TradingGateway):
    mode = "paper"

    def __init__(self, fee_percent=None, slippage_percent=None):
        self.fee_rate = (fee_percent if fee_percent is not None else settings.paper_fee_percent) / 100
        self.slippage_rate = (slippage_percent if slippage_percent is not None else settings.paper_slippage_percent) / 100

    def buy(self, symbol, price, quantity, client_order_id=None):
        fill = price * (1 + self.slippage_rate)
        return OrderResult(str(uuid.uuid4()), symbol, "buy", quantity, fill, fill * quantity * self.fee_rate, "paper")

    def sell(self, symbol, price, quantity, client_order_id=None):
        fill = price * (1 - self.slippage_rate)
        return OrderResult(str(uuid.uuid4()), symbol, "sell", quantity, fill, fill * quantity * self.fee_rate, "paper")
