from datetime import datetime, timezone, timedelta
import time
from typing import Dict

from decimal import Decimal
from xrpl.utils import xrp_to_drops
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet, generate_faucet_wallet
from xrpl.utils import datetime_to_ripple_time, xrp_to_drops
from xrpl.models.requests import AccountInfo
from xrpl.models.transactions import EscrowCreate, EscrowFinish
from xrpl.transaction import submit_and_wait
from .config import XRPL_TESTNET_JSON_RPC, ESCROW_FINISH_AFTER_S, ESCROW_CANCEL_AFTER_S
import os
from xrpl.clients import JsonRpcClient

XRPL_RPC = os.getenv("XRPL_RPC", "https://testnet.xrpl-labs.com/")
client = JsonRpcClient(XRPL_RPC)


def _ripple_time_in(seconds_from_now: int) -> int:
    return datetime_to_ripple_time(datetime.utcnow()) + int(seconds_from_now)

def create_funded_wallet() -> Wallet:
    return generate_faucet_wallet(client)

def get_xrp_balance(address: str) -> float:
    resp = client.request(AccountInfo(account=address, ledger_index="validated")).result
    return int(resp["account_data"]["Balance"]) / 1_000_000

def get_balances(addresses: Dict[str, str]) -> Dict[str, float]:
    return {k: get_xrp_balance(v) for k, v in addresses.items()}

def escrow_create(owner_wallet, destination: str, amount_xrp: float | Decimal):
    now_utc = datetime.now(timezone.utc)

    # make it finishable shortly after submission
    finish_after = datetime_to_ripple_time(now_utc + timedelta(seconds=5))

    # cancel in e.g. 15 minutes (tune as you like)
    cancel_after = datetime_to_ripple_time(now_utc + timedelta(minutes=15))

    amount_drops = xrp_to_drops(Decimal(str(amount_xrp)))

    tx = EscrowCreate(
        account=owner_wallet.classic_address,
        destination=destination,
        amount=amount_drops,
        finish_after=finish_after,
        cancel_after=cancel_after,
    )

    print("ESCROW TX:", tx.to_xrpl())

    result = submit_and_wait(tx, client, owner_wallet).result
    return {
        "tx_hash": result.get("hash"),
        "sequence": result["tx_json"]["Sequence"],  # or offer sequence depending on your implementation
    }

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

from xrpl.models.transactions import Payment

def send_payment(sender_wallet: Wallet, destination: str, amount_xrp: float) -> str:
    tx = Payment(
        account=sender_wallet.classic_address,
        destination=destination,
        amount=xrp_to_drops(amount_xrp),
    )
    result = submit_and_wait(tx, client, sender_wallet).result
    return result.get("hash", "")

