from typing import Dict, Any

STATE: Dict[str, Any] = {
    "wallets": {},          # "alice"/"bob"/"chen" -> Wallet
    "merchant": None,       # Wallet
    "coordinator": None,    # Wallet (submits EscrowFinish)
    "dids": {},             # did -> classic_address
    "requests": {},         # request_id -> dict
}
