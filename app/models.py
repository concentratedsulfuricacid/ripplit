from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FUNDING = "FUNDING"
    READY = "READY"
    PAID = "PAID"
    EXPIRED = "EXPIRED"


class GroupStatus(str, Enum):
    PENDING = "PENDING"
    FUNDING = "FUNDING"
    READY = "READY"
    PAID = "PAID"
    EXPIRED = "EXPIRED"


class ParticipantStatus(str, Enum):
    UNPAID = "UNPAID"
    ESCROWED = "ESCROWED"
    FINISHED = "FINISHED"
    REFUNDED = "REFUNDED"


class Product(BaseModel):
    id: str
    name: str
    description: str
    price_xrp: float


class Contact(BaseModel):
    handle: str
    address: str
    statement: Optional[str] = None
    verified: bool = False
    did_document: Optional[Dict] = None


class EscrowRef(BaseModel):
    owner_address: str
    offer_sequence: int
    tx_hash: str
    condition: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
    finish_tx_hash: Optional[str] = None
    canceled_at: Optional[datetime] = None
    cancel_tx_hash: Optional[str] = None


class Participant(BaseModel):
    handle: str
    address: str
    amount_xrp: float
    amount_drops: str
    status: ParticipantStatus = ParticipantStatus.UNPAID
    escrow: Optional[EscrowRef] = None


class GroupRequest(BaseModel):
    id: str
    order_id: str
    terms_hash: str
    participants: List[Participant]
    deadline: datetime
    condition: Optional[str] = None
    fulfillment: Optional[str] = None
    status: GroupStatus = GroupStatus.PENDING
    created_at: datetime


class Order(BaseModel):
    id: str
    product_id: str
    quantity: int
    total_xrp: float
    status: OrderStatus = OrderStatus.PENDING
    request_id: Optional[str] = None
    created_at: datetime


class CreateOrderRequest(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1)
    payment_method: str = "group_pay"
    participants: List[str]
    split: str = "equal"
    custom_amounts: Optional[Dict[str, float]] = None
    deadline_minutes: Optional[int] = None
    return_url: Optional[str] = None


class CreateOrderResponse(BaseModel):
    order: Order
    group_request: GroupRequest
    checkout_urls: Optional[Dict[str, str]] = None


class PayShareRequest(BaseModel):
    handle: str


class RegisterDidRequest(BaseModel):
    handle: str


class AppInfo(BaseModel):
    xrpl_mode: str
    merchant_address: str
    auto_finish: bool
    ledger_poll_seconds: int
    use_ledger_did: bool
