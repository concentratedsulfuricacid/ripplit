from typing import Dict, List, Optional
import json
import os

from .config import Settings
from .models import Contact
from .xrpl_service import XrplService


class DidRegistry:
    def __init__(self, settings: Settings, xrpl_service: XrplService) -> None:
        self.settings = settings
        self.xrpl = xrpl_service
        self._contacts: Dict[str, Contact] = {}
        self._seeds: Dict[str, str] = {}
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        defaults = {
            "alice": os.getenv("DEMO_ALICE_ADDRESS", "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"),
            "bob": os.getenv("DEMO_BOB_ADDRESS", "rLUEXYuLiQptky37CqLcm9USQpPiz5rkpD"),
            "chen": os.getenv("DEMO_CHEN_ADDRESS", "rH3v7pS4K2a5rNf1QZzzzzzzzzzzzzzzzz"),
        }
        statements = {
            "alice": "I am @alice and my payout address is rPT1...",
            "bob": "I am @bob and my payout address is rLUE...",
            "chen": "I am @chen and my payout address is rH3v...",
        }
        seeds = {
            "alice": os.getenv("DEMO_ALICE_SEED", ""),
            "bob": os.getenv("DEMO_BOB_SEED", ""),
            "chen": os.getenv("DEMO_CHEN_SEED", ""),
        }
        for handle, address in defaults.items():
            self._contacts[handle] = Contact(
                handle=handle, address=address, statement=statements.get(handle)
            )
            if seeds.get(handle):
                self._seeds[handle] = seeds[handle]

    def list_contacts(self) -> List[Contact]:
        return list(self._contacts.values())

    def get_contact(self, handle: str) -> Optional[Contact]:
        return self._contacts.get(handle)

    def get_seed(self, handle: str) -> Optional[str]:
        return self._seeds.get(handle)

    def register_handle(self, handle: str) -> str:
        contact = self._contacts.get(handle)
        if not contact:
            raise ValueError(f"Unknown handle: {handle}")
        seed = self._seeds.get(handle)
        if not seed:
            raise ValueError(f"Missing seed for {handle}")
        did_document = self._build_did_document(handle, contact.address)
        did_hex = json.dumps(did_document, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        ).hex().upper()
        uri_hex = f"@{handle}".encode("utf-8").hex().upper()
        result = self.xrpl.submit_did_set(seed, contact.address, did_hex, uri_hex)
        return result.tx_hash

    def refresh_from_ledger(self) -> None:
        if self.xrpl.mode == "mock" or not self.settings.use_ledger_did:
            return
        for handle, contact in list(self._contacts.items()):
            did_object = self.xrpl.fetch_did_object(contact.address)
            if not did_object:
                updated = contact.copy(update={"verified": False, "did_document": None})
                self._contacts[handle] = updated
                continue
            did_document = self._decode_did_document(did_object.get("DIDDocument"))
            uri = self._decode_hex(did_object.get("URI"))
            verified = False
            if did_document and did_document.get("handle") == handle:
                verified = True
            if uri in {handle, f"@{handle}"}:
                verified = True
            updated = contact.copy(update={"verified": verified, "did_document": did_document})
            self._contacts[handle] = updated

    def _decode_hex(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        try:
            return bytes.fromhex(value).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None

    def _decode_did_document(self, value: Optional[str]) -> Optional[Dict]:
        if not value:
            return None
        decoded = self._decode_hex(value)
        if not decoded:
            return None
        try:
            return json.loads(decoded)
        except json.JSONDecodeError:
            return None

    def _build_did_document(self, handle: str, address: str) -> Dict:
        return {
            "id": f"did:xrpl:{address}",
            "handle": handle,
            "address": address,
            "alsoKnownAs": [f"@{handle}"],
        }
