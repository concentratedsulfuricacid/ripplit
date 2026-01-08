import time
import uuid
from typing import Dict, List

import httpx

from .state import STATE
from .models import Participant, User, StartFromRedirect
from .did_registry import resolve_did
from .xrpl_service import escrow_create, escrow_finish, wait_until_finishable
from .config import REQUEST_EXPIRES_S

def _id(prefix: str) -> str:
    return f"{prefix}_{str(uuid.uuid4())[:8]}"

def ensure_inited():
    if not STATE["wallets"] or STATE["merchant"] is None or STATE["coordinator"] is None:
        raise RuntimeError("Ripplit not initialized. Click 'Initialize Wallet' first.")

def _now() -> int:
    return int(time.time())

def _compute_status(req: Dict) -> str:
    if req["status"] == "FULFILLED":
        return "FULFILLED"
    if _now() >= req["expires_at_unix"]:
        return "EXPIRED"
    return "PENDING"

def list_history():
    ensure_inited()
    out = []
    for req_id, req in STATE["requests"].items():
        status = _compute_status(req)
        if status == "EXPIRED" and req["status"] != "FULFILLED":
            req["status"] = "EXPIRED"
            STATE["requests"][req_id] = req
        out.append({
            "request_id": req_id,
            "order_id": req["order_id"],
            "total_xrp": req["total_xrp"],
            "status": _compute_status(req),
            "created_at_unix": req["created_at_unix"],
            "expires_at_unix": req["expires_at_unix"],
        })
    out.sort(key=lambda x: x["created_at_unix"], reverse=True)
    return out

def create_request_from_redirect(req: StartFromRedirect) -> Dict:
    ensure_inited()
    vault_address = STATE["coordinator"].classic_address
    merchant_address = STATE["merchant"].classic_address

    selected = [u for u in req.selected_payees if u in ["bob", "chen"]]
    participants_users: List[User] = ["alice"] + selected
    n = len(participants_users)
    if n < 2:
        raise ValueError("Select at least one co-payee (Bob or Chen).")

    share = float(req.total_xrp) / n

    merchant_address = STATE["merchant"].classic_address
    created_at = _now()
    expires_at = created_at + REQUEST_EXPIRES_S

    request_id = _id("tx")

    participants: Dict[User, Dict] = {}
    for u in participants_users:
        did = f"did:ripplit:{u}"
        addr = resolve_did(did)
        participants[u] = Participant(did=did, address=addr, share_xrp=share).model_dump()

    request_obj = {
        "vault_address": vault_address,
        "request_id": request_id,
        "order_id": req.order_id,
        "item_label": req.item_label or "Marketplace order",
        "total_xrp": float(req.total_xrp),
        "return_url": req.return_url,
        "merchant_address": merchant_address,
        "created_at_unix": created_at,
        "expires_at_unix": expires_at,
        "status": "PENDING",
        "participants": participants,
        "finish_tx_hashes": {},
    }

    STATE["requests"][request_id] = request_obj

    # Alice immediately pays her share
    _pay_internal(request_id, "alice")
    return STATE["requests"][request_id]

def inbox_for(user: User):
    ensure_inited()
    out = []
    for req in STATE["requests"].values():
        status = _compute_status(req)
        if status != "PENDING":
            continue
        if user not in req["participants"]:
            continue
        if req["participants"][user]["status"] == "REQUESTED":
            out.append(req)
    out.sort(key=lambda r: r["created_at_unix"], reverse=True)
    return out

def pay(request_id: str, payer: User) -> Dict:
    ensure_inited()
    if request_id not in STATE["requests"]:
        raise ValueError("Unknown request_id")
    return _pay_internal(request_id, payer)

def _pay_internal(request_id: str, payer: User) -> Dict:
    req = STATE["requests"][request_id]
    status = _compute_status(req)

    if status == "EXPIRED":
        req["status"] = "EXPIRED"
        STATE["requests"][request_id] = req
        return req

    if status == "FULFILLED":
        return req

    if payer not in req["participants"]:
        raise ValueError(f"{payer} is not part of this request.")

    p = req["participants"][payer]
    if p["status"] == "PAID":
        return req

    payer_wallet = STATE["wallets"][payer]

    vault_dest = req.get("vault_address") or STATE["coordinator"].classic_address
    print("ESCROW DEST:", (req.get("vault_address")), "MERCHANT:", req.get("merchant_address"))
    info = escrow_create(payer_wallet, vault_dest, float(p["share_xrp"]))

    p["status"] = "PAID"
    p["escrow_owner"] = payer_wallet.classic_address
    p["escrow_offer_sequence"] = info["sequence"]
    p["escrow_create_tx_hash"] = info["tx_hash"]
    req["participants"][payer] = p

    if all(pp["status"] == "PAID" for pp in req["participants"].values()):
        _settle_and_callback(req)

    STATE["requests"][request_id] = req
    return req

def _settle_and_callback(req: Dict):
    wait_until_finishable()
    finisher = STATE["coordinator"]
    finish_hashes = {}

    for u, p in req["participants"].items():
        finish_hashes[u] = escrow_finish(
            finisher_wallet=finisher,
            owner_address=p["escrow_owner"],
            offer_sequence=int(p["escrow_offer_sequence"]),
        )

    req["finish_tx_hashes"] = finish_hashes
    req["status"] = "FULFILLED"

    payload = {
        "order_id": req["order_id"],
        "status": "PAID",
        "details": {
            "ripplit_request_id": req["request_id"],
            "finish_tx_hashes": finish_hashes,
            "escrow_create_hashes": {u: req["participants"][u]["escrow_create_tx_hash"] for u in req["participants"]},
        },
    }

    try:
        httpx.post(req["return_url"], json=payload, timeout=15.0)
    except Exception:
        pass

    from .xrpl_service import send_payment

    vault = STATE["coordinator"]
    merchant = req["merchant_address"]
    pay_hash = send_payment(vault, merchant, float(req["total_xrp"]))
    req["merchant_payment_tx_hash"] = pay_hash

    def history_for(user: str):
        ensure_inited()
        out = []
        for req_id, req in STATE["requests"].items():
            if user not in req["participants"]:
                continue

            status = _compute_status(req)

            # unpaid list for pending requests
            unpaid = []
            if status == "PENDING":
                for u, p in req["participants"].items():
                    if p.get("status") != "PAID":
                        unpaid.append(u)

            out.append({
                "request_id": req_id,
                "order_id": req["order_id"],
                "item_label": req.get("item_label", ""),
                "total_xrp": req["total_xrp"],
                "status": status,
                "created_at_unix": req["created_at_unix"],
                "expires_at_unix": req["expires_at_unix"],
                "unpaid": unpaid,
                "participants": req["participants"],  # useful so UI can show "your share" & "your status"
            })

        out.sort(key=lambda x: x["created_at_unix"], reverse=True)
        return out

