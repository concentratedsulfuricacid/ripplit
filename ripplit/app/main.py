# ripplit/app/main.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .state import STATE
from .models import InitResponse, StartFromRedirect, PayAction
from .xrpl_service import create_funded_wallet, get_balances, get_xrp_balance
from .did_registry import seed_demo_dids
from .group_pay import (
    create_request_from_redirect,
    list_history_for_alice,
    inbox_for,
    pay,
)

app = FastAPI(title="Ripplit")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def root():
    return """<meta http-equiv="refresh" content="0; url=/static/pay.html">"""

@app.post("/api/admin/init", response_model=InitResponse)
def init_wallets():
    # Create + fund demo wallets
    STATE["wallets"] = {}
    STATE["requests"] = {}

    STATE["wallets"]["alice"] = create_funded_wallet()
    STATE["wallets"]["bob"] = create_funded_wallet()
    STATE["wallets"]["chen"] = create_funded_wallet()

    STATE["merchant"] = create_funded_wallet()
    STATE["coordinator"] = create_funded_wallet()

    seed_demo_dids()

    addrs = {
        "alice": STATE["wallets"]["alice"].classic_address,
        "bob": STATE["wallets"]["bob"].classic_address,
        "chen": STATE["wallets"]["chen"].classic_address,
        "merchant": STATE["merchant"].classic_address,
        "coordinator": STATE["coordinator"].classic_address,
    }
    return InitResponse(wallets=addrs, dids=STATE["dids"], balances_xrp=get_balances(addrs))

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
    return {"history": list_history_for_alice()}

@app.get("/api/ripplit/request/{request_id}")
def request_details(request_id: str):
    if request_id not in STATE["requests"]:
        return {"error": "Unknown request_id"}
    return {"request": STATE["requests"][request_id]}

@app.get("/api/ripplit/inbox/{user}")
def inbox(user: str):
    if user not in ["bob", "chen"]:
        return {"error": "Inbox only for bob/chen in this MVP"}
    return {"requests": inbox_for(user)}

@app.post("/api/ripplit/pay/{request_id}")
def pay_api(request_id: str, action: PayAction):
    req = pay(request_id, action.payer)
    return {"request": req}
