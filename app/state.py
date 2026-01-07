from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List
from uuid import uuid4

from .models import GroupRequest, Order, Product


class StateStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self.products: Dict[str, Product] = {}
        self.orders: Dict[str, Order] = {}
        self.group_requests: Dict[str, GroupRequest] = {}
        self._sequence_by_address: Dict[str, int] = {}
        self._seed_products()

    def _seed_products(self) -> None:
        catalog = [
            Product(
                id="ticket",
                name="Concert Ticket",
                description="General admission + digital collectible stub.",
                price_xrp=18.5,
            ),
            Product(
                id="stay",
                name="Airbnb Deposit",
                description="Split a shared booking deposit with friends.",
                price_xrp=42.0,
            ),
            Product(
                id="dinner",
                name="Dinner Voucher",
                description="Prepay a tasting menu for the group.",
                price_xrp=27.75,
            ),
        ]
        self.products = {item.id: item for item in catalog}

    def list_products(self) -> List[Product]:
        return list(self.products.values())

    def get_product(self, product_id: str) -> Product:
        return self.products[product_id]

    def create_order(self, product_id: str, quantity: int, total_xrp: float) -> Order:
        with self._lock:
            order_id = uuid4().hex
            order = Order(
                id=order_id,
                product_id=product_id,
                quantity=quantity,
                total_xrp=total_xrp,
                created_at=datetime.now(timezone.utc),
            )
            self.orders[order_id] = order
            return order

    def save_order(self, order: Order) -> None:
        with self._lock:
            self.orders[order.id] = order

    def get_order(self, order_id: str) -> Order:
        return self.orders[order_id]

    def list_orders(self) -> List[Order]:
        return list(self.orders.values())

    def save_group_request(self, request: GroupRequest) -> None:
        with self._lock:
            self.group_requests[request.id] = request

    def get_group_request(self, request_id: str) -> GroupRequest:
        return self.group_requests[request_id]

    def list_group_requests(self) -> List[GroupRequest]:
        return list(self.group_requests.values())

    def next_sequence(self, address: str) -> int:
        with self._lock:
            current = self._sequence_by_address.get(address, 1)
            self._sequence_by_address[address] = current + 1
            return current
