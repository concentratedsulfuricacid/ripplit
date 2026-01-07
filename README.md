# XRPL GroupPay Demo

This repo contains a demo project for an XRPL group payment flow with escrow-based coordination.

## Structure

- `project_structure.yaml`: File manifest used to generate the project tree.
- `app/`: FastAPI backend and GroupPay logic.
- `static/`: Hosted checkout and payer web views.
- `requirements.txt`: Python dependencies.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/` to view the hosted checkout.

## Hosted checkout (redirect)

The root page behaves like a Stripe/PayPal-style hosted checkout. You can pass
merchant context as query params so the UI looks like a redirect from a store:

```
http://127.0.0.1:8000/?merchant=Amazon&order_id=ORDER-123&product_id=ticket&quantity=2&return_url=https://merchant.example.com/return
```

- If `product_id` is provided, the item and quantity are locked.
- If `return_url` is provided, the checkout shows a “Return to merchant” link.
- If `API_KEY` is set, append `&api_key=YOUR_KEY` so the UI can call write APIs.

## XRPL configuration

By default the app runs in `mock` mode so you can demo the flow without Testnet
wallets. To use XRPL Testnet escrows, set these environment variables:

- `XRPL_MODE=testnet`
- `XRPL_JSON_RPC_URL=https://s.altnet.rippletest.net:51234`
- `MERCHANT_ADDRESS=...`
- `MERCHANT_SEED=...`
- `DEMO_ALICE_ADDRESS=...`, `DEMO_ALICE_SEED=...`
- `DEMO_BOB_ADDRESS=...`, `DEMO_BOB_SEED=...`
- `DEMO_CHEN_ADDRESS=...`, `DEMO_CHEN_SEED=...`

The app uses canonical PREIMAGE-SHA-256 crypto-conditions via `cryptoconditions`.

## Ledger polling and DID registry

When `XRPL_MODE=testnet`, the backend polls the ledger (default every 8s) to:

- detect EscrowCreate/Finish/Cancel transactions for the request
- keep the order status in sync with on-ledger activity
- refresh DID metadata for configured contacts

You can configure polling with:

- `LEDGER_POLL_SECONDS=8`
- `ENABLE_LEDGER_POLLING=true`
- `USE_LEDGER_DID=true`

To publish an on-ledger DID for a handle:

```bash
curl -X POST http://127.0.0.1:8000/api/did/register \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"handle":"alice"}'
```

## API key auth (optional)

If you set `API_KEY=...`, write endpoints require the header `X-API-Key`.
You can pass it to the UI by appending `?api_key=YOUR_KEY` to the URL.

## Stripe-style redirect links

If a merchant backend creates the order, the response includes `checkout_urls`
for each payer:

```
/pay/{request_id}/{handle}
```

These redirect to the wallet page and can include `return_url` so payers can
return to the originating site after completing payment.

### Merchant API example

```bash
curl -X POST http://127.0.0.1:8000/api/orders \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_KEY" \
  -d '{
    "product_id": "ticket",
    "quantity": 1,
    "participants": ["alice", "bob", "chen"],
    "split": "equal",
    "deadline_minutes": 15,
    "return_url": "https://merchant.example.com/return"
  }'
```
