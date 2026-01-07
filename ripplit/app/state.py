# ripplit/app/state.py
from typing import Dict, Any

STATE: Dict[str, Any] = {
    "wallets": {},          # "alice"/"bob"/"chen" -> xrpl.wallet.Wallet
    "merchant": None,       # xrpl.wallet.Wallet
    "coordinator": None,    # xrpl.wallet.Wallet (submits EscrowFinish)
    "dids": {},             # did -> classic_address
    "requests": {},         # request_id -> dict
}
