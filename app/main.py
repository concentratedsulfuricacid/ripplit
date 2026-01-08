from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
import threading
import time
from typing import Optional

from .config import settings
from .did_registry import DidRegistry
from .group_pay import GroupPayService
from .models import (
    AppInfo,
    CreateOrderRequest,
    CreateOrderResponse,
    PayShareRequest,
    RegisterDidRequest,
)
from .state import StateStore
from .xrpl_service import XrplService, XrplServiceError


state = StateStore()
xrpl_service = XrplService(settings, state)
registry = DidRegistry(settings, xrpl_service)
group_pay = GroupPayService(settings, state, registry, xrpl_service)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")


def require_api_key(x_api_key: str = Header(default="")) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.on_event("startup")
async def startup() -> None:
    if settings.xrpl_mode == "mock" or not settings.enable_ledger_polling:
        return

    def poll() -> None:
        while True:
            try:
                registry.refresh_from_ledger()
                group_pay.sync_with_ledger()
            except Exception:
                pass
            time.sleep(settings.ledger_poll_seconds)

    thread = threading.Thread(target=poll, daemon=True)
    thread.start()


@app.get("/")
async def root(request: Request) -> RedirectResponse:
    url = "/static/marketplace.html"
    if request.url.query:
        url += f"?{request.url.query}"
    return RedirectResponse(url=url)


@app.get("/pay/{request_id}/{handle}")
async def pay_redirect(
    request_id: str,
    handle: str,
    return_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> RedirectResponse:
    url = f"/static/marketplace.html?request_id={request_id}&payer={handle}&handle={handle}"
    if return_url:
        url += f"&return_url={return_url}"
    if api_key:
        url += f"&api_key={api_key}"
    return RedirectResponse(url=url)


@app.get("/api/info", response_model=AppInfo)
async def info() -> AppInfo:
    return AppInfo(
        xrpl_mode=settings.xrpl_mode,
        merchant_address=settings.merchant_address,
        auto_finish=settings.auto_finish,
        ledger_poll_seconds=settings.ledger_poll_seconds,
        use_ledger_did=settings.use_ledger_did,
    )


@app.get("/api/products")
async def list_products():
    return state.list_products()


@app.get("/api/contacts")
async def list_contacts():
    return registry.list_contacts()


@app.get("/api/wallet/balance/{handle}")
async def wallet_balance(handle: str):
    contact = registry.get_contact(handle)
    if not contact:
        raise HTTPException(status_code=404, detail="Unknown handle")
    try:
        balance_xrp = xrpl_service.get_balance_xrp(contact.address)
    except XrplServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"handle": handle, "address": contact.address, "balance_xrp": balance_xrp}


@app.post("/api/did/register")
async def register_did(payload: RegisterDidRequest, _: None = Depends(require_api_key)):
    try:
        tx_hash = registry.register_handle(payload.handle)
        return {"tx_hash": tx_hash}
    except (ValueError, XrplServiceError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/orders", response_model=CreateOrderResponse)
async def create_order(
    payload: CreateOrderRequest,
    request: Request,
    _: None = Depends(require_api_key),
) -> CreateOrderResponse:
    if payload.payment_method != "group_pay":
        raise HTTPException(status_code=400, detail="Only group_pay is supported")
    try:
        product = state.get_product(payload.product_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown product") from exc

    total_xrp = round(product.price_xrp * payload.quantity, 6)
    order = state.create_order(payload.product_id, payload.quantity, total_xrp)
    try:
        group_request = group_pay.create_group_request(
            order=order,
            participants=payload.participants,
            split=payload.split,
            custom_amounts=payload.custom_amounts,
            deadline_minutes=payload.deadline_minutes,
        )
    except (ValueError, XrplServiceError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    base_url = str(request.base_url).rstrip("/")
    checkout_urls = {
        participant.handle: f"{base_url}/pay/{group_request.id}/{participant.handle}"
        + (f"?return_url={payload.return_url}" if payload.return_url else "")
        for participant in group_request.participants
    }

    return CreateOrderResponse(
        order=order, group_request=group_request, checkout_urls=checkout_urls
    )


@app.get("/api/orders")
async def list_orders():
    return state.list_orders()


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str):
    try:
        return state.get_order(order_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Order not found") from exc


@app.get("/api/requests")
async def list_requests():
    return await group_pay.list_requests()


@app.get("/api/requests/{request_id}")
async def get_request(request_id: str):
    try:
        return await group_pay.refresh_request(request_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc


@app.post("/api/requests/{request_id}/pay")
async def pay_share(
    request_id: str, payload: PayShareRequest, _: None = Depends(require_api_key)
):
    try:
        return await group_pay.pay_share(request_id, payload.handle)
    except (KeyError, ValueError, XrplServiceError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/requests/{request_id}/finish")
async def finish_request(request_id: str, _: None = Depends(require_api_key)):
    try:
        return await group_pay.finish_request(request_id)
    except (KeyError, XrplServiceError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
