# ripplit/app/did_registry.py
from .state import STATE

def seed_demo_dids():
    # Demo DID mapping (off-ledger for MVP)
    STATE["dids"] = {
        "did:ripplit:alice": STATE["wallets"]["alice"].classic_address,
        "did:ripplit:bob": STATE["wallets"]["bob"].classic_address,
        "did:ripplit:chen": STATE["wallets"]["chen"].classic_address,
    }

def resolve_did(did: str) -> str:
    if did not in STATE["dids"]:
        raise ValueError(f"Unknown DID: {did}")
    return STATE["dids"][did]
