from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .state import STATE
from .models import InitResponse, StartFromRedirect, PayAction
from .xrpl_service import create_funded_wallet, get_balances, get_xrp_balance
from .did_registry import seed_demo_dids
from .group_pay import create_request_from_redirect, list_history, inbox_for, pay

BASE_DIR = Path(__file__).resolve().parent  # .../app
STATIC_DIR = BASE_DIR / "static"           # .../app/static

app = FastAPI(title="Ripplit")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
def root():
    return """<meta http-equiv="refresh" content="0; url=/static/login.html">"""

@app.get("/api/admin/balances")
def admin_balances():
    addrs = {
        "alice": STATE["wallets"]["alice"].classic_address,
        "bob": STATE["wallets"]["bob"].classic_address,
        "chen": STATE["wallets"]["chen"].classic_address,
        "vault": STATE["coordinator"].classic_address,
        "merchant": STATE["merchant"].classic_address,
    }
    return {"wallets": addrs, "balances_xrp": get_balances(addrs)}

@app.get("/api/wallet/balance/{user}")
def wallet_balance(user: str):
    if user not in ["alice", "bob", "chen", "merchant", "coordinator"]:
        return {"error": "Unknown user"}

    if user in ["merchant", "coordinator"]:
        w = STATE[user]
        if w is None:
            return {"error": "Not initialized"}
        return {"user": user, "address": w.classic_address, "balance_xrp": get_xrp_balance(w.classic_address)}

    if not STATE["wallets"]:
        return {"error": "Not initialized"}

    w = STATE["wallets"][user]
    return {"user": user, "address": w.classic_address, "balance_xrp": get_xrp_balance(w.classic_address)}

@app.post("/api/ripplit/start")
def start_from_marketplace(req: StartFromRedirect):
    gpr = create_request_from_redirect(req)
    return {"request": gpr}

@app.get("/api/ripplit/history")
def history():
    return {"history": list_history()}

@app.get("/api/ripplit/inbox/{user}")
def inbox(user: str):
    if user not in ["bob", "chen"]:
        return {"error": "Inbox only for bob/chen in this MVP"}
    return {"requests": inbox_for(user)}

@app.post("/api/ripplit/pay/{request_id}")
def pay_api(request_id: str, action: PayAction):
    req = pay(request_id, action.payer)
    return {"request": req}

import os
from dotenv import load_dotenv
from pathlib import Path
from xrpl.wallet import Wallet

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"   # repo root
load_dotenv(ENV_PATH)

def w(seed_name: str) -> Wallet:
    seed = os.getenv(seed_name)
    if not seed:
        raise RuntimeError(f"Missing {seed_name} in .env")
    return Wallet.from_seed(seed)

@app.on_event("startup")
def startup():
    STATE["wallets"] = {
        "alice": w("ALICE_SEED"),
        "bob": w("BOB_SEED"),
        "chen": w("CHEN_SEED"),
    }
    STATE["coordinator"] = w("VAULT_SEED")   # vault account
    STATE["merchant"] = w("MERCHANT_SEED")   # optional
    seed_demo_dids()

    STATE.setdefault("requests", {})

from xrpl.models.requests import ServerInfo

@app.get("/api/admin/server_info")
def server_info():
    return xrpl_service.client.request(ServerInfo()).result

from fastapi import HTTPException

@app.post("/api/ripplit/start")
def start_from_marketplace(req: StartFromRedirect):
    try:
        return {"request": create_request_from_redirect(req)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
from fastapi import HTTPException

@app.get("/api/ripplit/history/{user}")
def history(user: str):
    # validate user
    from .state import STATE
    if user not in ("alice", "bob", "chen"):
        raise HTTPException(status_code=400, detail="Unknown user. Use alice/bob/chen.")

    # If you still have ensure_inited(), keep it:
    from .group_pay import ensure_inited, list_history
    ensure_inited()

    # list_history() returns all tx summaries; we enrich with participants + unpaid list
    out = []
    for tx in STATE["requests"].values():
        if user not in tx["participants"]:
            continue

        # compute status (reuse your logic if you already have _compute_status)
        from .group_pay import _compute_status
        status = _compute_status(tx)

        unpaid = [u for u, p in tx["participants"].items() if p.get("status") != "PAID"]

        out.append({
            "request_id": tx["request_id"],
            "order_id": tx["order_id"],
            "item_label": tx.get("item_label", ""),
            "total_xrp": tx["total_xrp"],
            "status": status,  # PENDING / FULFILLED / EXPIRED
            "created_at_unix": tx["created_at_unix"],
            "expires_at_unix": tx["expires_at_unix"],
            "unpaid": unpaid,
            "participants": {
                u: {
                    "status": p.get("status"),
                    "share_xrp": p.get("share_xrp"),
                } for u, p in tx["participants"].items()
            }
        })

    out.sort(key=lambda x: x["created_at_unix"], reverse=True)
    return {"history": out}


