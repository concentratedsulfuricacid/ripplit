from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uuid
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode
import os

app = FastAPI(title="Marketplace")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

ORDERS: Dict[str, Dict[str, Any]] = {}

RIPPLIT_PAY_URL = os.getenv("RIPPLIT_PAY_URL", "http://127.0.0.1:8000/static/login.html")
RIPPLIT_API_BASE = os.getenv("RIPPLIT_API_BASE", "http://127.0.0.1:8000")
RIPPLIT_API_KEY = os.getenv("RIPPLIT_API_KEY", os.getenv("API_KEY", ""))
MARKETPLACE_BASE = os.getenv("MARKETPLACE_BASE", "http://127.0.0.1:8010")
MARKETPLACE_NAME = os.getenv("MARKETPLACE_NAME", "Nimbus Market")



# def _build_redirect(order: Dict[str, Any]) -> str:
#     items = order.get("items") or []
#     if not items:
#         return ""
#     item = items[0]
#     return_url = f"{MARKETPLACE_BASE}/api/order/ripplit_callback"
#     params = {
#         "merchant": MARKETPLACE_NAME,
#         "order_id": order.get("order_id"),
#         "product_id": item.get("sku"),
#         "quantity": item.get("qty"),
#         "total_xrp": order.get("total_xrp"),
#         "return_url": return_url,
#         "merchant_url": MARKETPLACE_BASE,
#         "api_base": RIPPLIT_API_BASE,
#     }
#     if RIPPLIT_API_KEY:
#         params["api_key"] = RIPPLIT_API_KEY
#     return f"{RIPPLIT_PAY_URL}?{urlencode(params)}"
def _build_redirect(order: Dict[str, Any]) -> str:
    items = order.get("items") or []
    if not items:
        return ""
    item = items[0]
    return_url = f"{MARKETPLACE_BASE}/api/order/ripplit_callback"
    params = {
        "merchant": MARKETPLACE_NAME,
        "order_id": order.get("order_id"),
        "product_id": item.get("sku"),
        "quantity": item.get("qty"),

        # NEW:
        "total_rlusd": order.get("total_rlusd"),
        "currency": order.get("currency", "RLUSD"),

        "return_url": return_url,
        "merchant_url": MARKETPLACE_BASE,
        "api_base": RIPPLIT_API_BASE,
    }
    if RIPPLIT_API_KEY:
        params["api_key"] = RIPPLIT_API_KEY
    return f"{RIPPLIT_PAY_URL}?{urlencode(params)}"



# class CartItem(BaseModel):
#     sku: str
#     name: str
#     unit_price_xrp: float
#     qty: int

class CartItem(BaseModel):
    sku: str
    name: str
    unit_price_rlusd: float
    qty: int



class CreateOrderReq(BaseModel):
    items: List[CartItem]


class RipplitCallback(BaseModel):
    order_id: str
    status: str  # "PAID" or "FAILED"
    details: Optional[dict] = None


@app.get("/", response_class=HTMLResponse)
def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/orders")
def list_orders():
    # newest first
    orders = list(reversed(list(ORDERS.values())))
    return {"orders": [{**o, "redirect_url": _build_redirect(o)} for o in orders]}


# @app.post("/api/order/create")
# def create_order(req: CreateOrderReq):
#     if not req.items:
#         return {"error": "Cart is empty"}
#     if len(req.items) != 1:
#         return {"error": "GroupPay demo supports one item per checkout."}

#     total = 0.0
#     for it in req.items:
#         total += float(it.unit_price_xrp) * int(it.qty)

#     order_id = f"ord_{str(uuid.uuid4())[:8]}"
#     order = {
#         "order_id": order_id,
#         "items": [it.model_dump() for it in req.items],
#         "total_xrp": round(total, 6),
#         "status": "PENDING_GROUPPAY",
#         "details": None,
#     }
#     ORDERS[order_id] = order

#     redirect_url = _build_redirect(order)

#     return {"order": order, "redirect_url": redirect_url}

@app.post("/api/order/create")
def create_order(req: CreateOrderReq):
    if not req.items:
        return {"error": "Cart is empty"}
    if len(req.items) != 1:
        return {"error": "GroupPay demo supports one item per checkout."}

    total = 0.0
    for it in req.items:
        total += float(it.unit_price_rlusd) * int(it.qty)

    order_id = f"ord_{str(uuid.uuid4())[:8]}"
    order = {
        "order_id": order_id,
        "items": [it.model_dump() for it in req.items],
        "total_rlusd": round(total, 6),
        "currency": "RLUSD",
        "status": "PENDING_GROUPPAY",
        "details": None,
    }
    ORDERS[order_id] = order

    redirect_url = _build_redirect(order)
    return {"order": order, "redirect_url": redirect_url}



@app.post("/api/order/ripplit_callback")
def ripplit_callback(cb: RipplitCallback):
    if cb.order_id not in ORDERS:
        return {"error": "Unknown order_id"}
    ORDERS[cb.order_id]["status"] = cb.status
    ORDERS[cb.order_id]["details"] = cb.details
    return {"ok": True}
