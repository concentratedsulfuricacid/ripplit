from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uuid
from typing import Optional, Dict, Any, List

app = FastAPI(title="Marketplace")
app.mount("/static", StaticFiles(directory="static"), name="static")

ORDERS: Dict[str, Dict[str, Any]] = {}

RIPPLIT_PAY_URL = "http://127.0.0.1:8020/static/pay.html"
MARKETPLACE_BASE = "http://127.0.0.1:8010"


class CartItem(BaseModel):
    sku: str
    name: str
    unit_price_xrp: float
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
    return {"orders": list(reversed(list(ORDERS.values())))}


@app.post("/api/order/create")
def create_order(req: CreateOrderReq):
    if not req.items:
        return {"error": "Cart is empty"}

    total = 0.0
    for it in req.items:
        total += float(it.unit_price_xrp) * int(it.qty)

    order_id = f"ord_{str(uuid.uuid4())[:8]}"
    order = {
        "order_id": order_id,
        "items": [it.model_dump() for it in req.items],
        "total_xrp": round(total, 6),
        "status": "PENDING_GROUPPAY",
        "details": None,
    }
    ORDERS[order_id] = order

    return_url = f"{MARKETPLACE_BASE}/api/order/ripplit_callback"

    # Minimal deep link to Ripplit; Ripplit can fetch order details later if needed.
    redirect_url = (
        f"{RIPPLIT_PAY_URL}"
        f"?order_id={order_id}"
        f"&total_xrp={order['total_xrp']}"
        f"&return_url={return_url.replace(':', '%3A').replace('/', '%2F')}"
    )

    return {"order": order, "redirect_url": redirect_url}


@app.post("/api/order/ripplit_callback")
def ripplit_callback(cb: RipplitCallback):
    if cb.order_id not in ORDERS:
        return {"error": "Unknown order_id"}
    ORDERS[cb.order_id]["status"] = cb.status
    ORDERS[cb.order_id]["details"] = cb.details
    return {"ok": True}
