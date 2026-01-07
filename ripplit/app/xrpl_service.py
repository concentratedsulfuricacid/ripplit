# ripplit/app/xrpl_service.py
from datetime import datetime
import time
from typing import Dict

from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet, generate_faucet_wallet
from xrpl.utils import datetime_to_ripple_time, xrp_to_drops
from xrpl.models.requests import AccountInfo
from xrpl.models.transactions import EscrowCreate, EscrowFinish
from xrpl.transaction import submit_and_wait

from .config import XRPL_TESTNET_JSON_RPC, ESCROW_FINISH_AFTER_S, ESCROW_CANCEL_AFTER_S

client = JsonRpcClient(XRPL_TESTNET_JSON_RPC)

def _ripple_time_in(seconds_from_now: int) -> int:
    return datetime_to_ripple_time(datetime.utcnow()) + int(seconds_from_now)

def create_funded_wallet() -> Wallet:
    # Testnet faucet-funded wallet
    return generate_faucet_wallet(client)

def get_xrp_balance(address: str) -> float:
    resp = client.request(AccountInfo(account=address, ledger_index="validated")).result
    return int(resp["account_data"]["Balance"]) / 1_000_000

def get_balances(addresses: Dict[str, str]) -> Dict[str, float]:
    return {k: get_xrp_balance(v) for k, v in addresses.items()}

def escrow_create(owner_wallet: Wallet, destination: str, amount_xrp: float) -> Dict:
    tx = EscrowCreate(
        account=owner_wallet.classic_address,
        amount=xrp_to_drops(amount_xrp),
        destination=destination,
        finish_after=_ripple_time_in(ESCROW_FINISH_AFTER_S),
        cancel_after=_ripple_time_in(ESCROW_CANCEL_AFTER_S),
    )
    result = submit_and_wait(tx, client, owner_wallet).result
    seq = result.get("tx_json", {}).get("Sequence")
    if seq is None:
        raise RuntimeError(f"Missing Sequence in EscrowCreate result: {result}")
    return {"sequence": int(seq), "tx_hash": result.get("hash", "")}

def wait_until_finishable():
    time.sleep(max(ESCROW_FINISH_AFTER_S + 1, 2))

def escrow_finish(finisher_wallet: Wallet, owner_address: str, offer_sequence: int) -> str:
    tx = EscrowFinish(
        account=finisher_wallet.classic_address,
        owner=owner_address,
        offer_sequence=int(offer_sequence),
    )
    result = submit_and_wait(tx, client, finisher_wallet).result
    return result.get("hash", "")
