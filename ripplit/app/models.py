# ripplit/app/models.py
from pydantic import BaseModel
from typing import Dict, List, Literal, Optional

User = Literal["alice", "bob", "chen"]

class InitResponse(BaseModel):
    wallets: Dict[str, str]
    dids: Dict[str, str]
    balances_xrp: Dict[str, float]

class StartFromRedirect(BaseModel):
    order_id: str
    total_xrp: float
    return_url: str
    item_label: Optional[str] = "Marketplace order"
    # which contacts Alice selected (Bob/Chen)
    selected_payees: List[User]  # e.g. ["bob","chen"]

class PayAction(BaseModel):
    payer: User

class Participant(BaseModel):
    did: str
    address: str
    share_xrp: float
    status: Literal["REQUESTED", "PAID"] = "REQUESTED"
    escrow_owner: Optional[str] = None
    escrow_offer_sequence: Optional[int] = None
    escrow_create_tx_hash: Optional[str] = None

class RequestSummary(BaseModel):
    request_id: str
    order_id: str
    total_xrp: float
    status: Literal["PENDING", "FULFILLED", "EXPIRED"]
    created_at_unix: int
    expires_at_unix: int
