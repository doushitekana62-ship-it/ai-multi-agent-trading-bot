from abc import ABC, abstractmethod
from app.indodax.models import OrderResult

class TradingGateway(ABC):
    mode: str
    @abstractmethod
    def buy(self, symbol: str, price: float, quantity: float) -> OrderResult: ...
    @abstractmethod
    def sell(self, symbol: str, price: float, quantity: float) -> OrderResult: ...
