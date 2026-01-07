from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
import binascii
import json
import urllib.request

from .config import Settings
from .state import StateStore


class XrplServiceError(RuntimeError):
    pass


@dataclass
class EscrowResult:
    offer_sequence: int
    tx_hash: str
    validated: bool


@dataclass
class TxSubmitResult:
    tx_hash: str
    validated: bool


class XrplService:
    def __init__(self, settings: Settings, state: StateStore) -> None:
        self.settings = settings
        self.state = state
        self.mode = settings.xrpl_mode.lower()
        self._client = None
        if self.mode != "mock":
            self._init_client()

    def _init_client(self) -> None:
        try:
            from xrpl.clients import JsonRpcClient
        except ImportError as exc:
            raise XrplServiceError(
                "xrpl-py is required for XRPL mode 'testnet'. Install requirements.txt"
            ) from exc
        self._client = JsonRpcClient(self.settings.xrpl_json_rpc_url)

    def _wallet_from_seed(self, seed: str):
        from xrpl.wallet import Wallet
        from xrpl.core.keypairs.main import CryptoAlgorithm

        algorithm = (
            CryptoAlgorithm.ED25519 if seed.startswith("sEd") else CryptoAlgorithm.SECP256K1
        )
        return Wallet.from_seed(seed, algorithm=algorithm)

    def _raw_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        payload = json.dumps({"method": method, "params": [params]}).encode("utf-8")
        req = urllib.request.Request(
            self.settings.xrpl_json_rpc_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)

    def generate_condition(self) -> Dict[str, str]:
        try:
            from cryptoconditions import PreimageSha256
        except ImportError as exc:
            raise XrplServiceError(
                "cryptoconditions is required for XRPL conditional escrows"
            ) from exc
        preimage = uuid4().bytes + uuid4().bytes
        condition = PreimageSha256(preimage=preimage)
        condition_hex = binascii.hexlify(condition.condition_binary).decode("utf-8").upper()
        fulfillment_hex = binascii.hexlify(condition.serialize_binary()).decode("utf-8").upper()
        return {"condition": condition_hex, "fulfillment": fulfillment_hex}

    def create_escrow(
        self,
        payer_seed: str,
        payer_address: str,
        amount_drops: str,
        destination: str,
        cancel_after: int,
        condition: Optional[str],
    ) -> EscrowResult:
        if self.mode == "mock":
            return self._mock_create_escrow(payer_address)
        return self._real_create_escrow(
            payer_seed,
            payer_address,
            amount_drops,
            destination,
            cancel_after,
            condition,
        )

    def finish_escrow(
        self,
        merchant_seed: str,
        owner_address: str,
        offer_sequence: int,
        fulfillment: Optional[str],
    ) -> TxSubmitResult:
        if self.mode == "mock":
            return self._mock_finish_escrow()
        return self._real_finish_escrow(merchant_seed, owner_address, offer_sequence, fulfillment)

    def cancel_escrow(
        self,
        merchant_seed: str,
        owner_address: str,
        offer_sequence: int,
    ) -> TxSubmitResult:
        if self.mode == "mock":
            return self._mock_cancel_escrow()
        return self._real_cancel_escrow(merchant_seed, owner_address, offer_sequence)

    def submit_did_set(self, seed: str, address: str, did_document: str, uri: str) -> TxSubmitResult:
        if self.mode == "mock":
            return self._mock_finish_escrow()
        payload = {
            "secret": seed,
            "tx_json": {
                "TransactionType": "DIDSet",
                "Account": address,
                "DIDDocument": did_document,
                "URI": uri,
            },
        }
        result = self._raw_request("submit", payload).get("result", {})
        tx_hash = result.get("tx_json", {}).get("hash") or result.get("hash") or uuid4().hex
        validated = result.get("validated", False)
        return TxSubmitResult(tx_hash=tx_hash, validated=validated)

    def fetch_did_object(self, address: str) -> Optional[Dict[str, Any]]:
        if self.mode == "mock":
            return None
        result = self._raw_request(
            "account_objects", {"account": address, "type": "did"}
        ).get("result", {})
        objects = result.get("account_objects", [])
        if not objects:
            return None
        return objects[0]

    def find_escrow_create(
        self,
        owner_address: str,
        destination: str,
        amount_drops: str,
        condition: Optional[str],
        cancel_after: int,
        limit: int = 50,
    ) -> Optional[EscrowResult]:
        if self.mode == "mock":
            return None
        transactions = self._account_transactions(owner_address, limit)
        for entry in transactions:
            tx = entry.get("tx") or entry.get("tx_json") or {}
            if tx.get("TransactionType") != "EscrowCreate":
                continue
            if tx.get("Destination") != destination:
                continue
            if tx.get("Amount") != amount_drops:
                continue
            if condition and tx.get("Condition") != condition:
                continue
            if tx.get("CancelAfter") != cancel_after:
                continue
            validated = entry.get("validated", False)
            tx_hash = tx.get("hash") or entry.get("hash") or uuid4().hex
            offer_sequence = tx.get("Sequence")
            if offer_sequence is None:
                continue
            return EscrowResult(
                offer_sequence=int(offer_sequence),
                tx_hash=tx_hash,
                validated=validated,
            )
        return None

    def find_escrow_finish(
        self,
        merchant_address: str,
        owner_address: str,
        offer_sequence: int,
        limit: int = 50,
    ) -> Optional[TxSubmitResult]:
        if self.mode == "mock":
            return None
        transactions = self._account_transactions(merchant_address, limit)
        for entry in transactions:
            tx = entry.get("tx") or entry.get("tx_json") or {}
            if tx.get("TransactionType") != "EscrowFinish":
                continue
            if tx.get("Owner") != owner_address:
                continue
            if tx.get("OfferSequence") != offer_sequence:
                continue
            tx_hash = tx.get("hash") or entry.get("hash") or uuid4().hex
            return TxSubmitResult(tx_hash=tx_hash, validated=entry.get("validated", False))
        return None

    def find_escrow_cancel(
        self,
        merchant_address: str,
        owner_address: str,
        offer_sequence: int,
        limit: int = 50,
    ) -> Optional[TxSubmitResult]:
        if self.mode == "mock":
            return None
        transactions = self._account_transactions(merchant_address, limit)
        for entry in transactions:
            tx = entry.get("tx") or entry.get("tx_json") or {}
            if tx.get("TransactionType") != "EscrowCancel":
                continue
            if tx.get("Owner") != owner_address:
                continue
            if tx.get("OfferSequence") != offer_sequence:
                continue
            tx_hash = tx.get("hash") or entry.get("hash") or uuid4().hex
            return TxSubmitResult(tx_hash=tx_hash, validated=entry.get("validated", False))
        return None

    def _account_transactions(self, address: str, limit: int) -> List[Dict[str, Any]]:
        result = self._raw_request(
            "account_tx",
            {
                "account": address,
                "ledger_index_min": -1,
                "ledger_index_max": -1,
                "limit": limit,
                "binary": False,
            },
        ).get("result", {})
        return result.get("transactions", [])

    def _mock_create_escrow(self, payer_address: str) -> EscrowResult:
        sequence = self.state.next_sequence(payer_address)
        tx_hash = uuid4().hex
        return EscrowResult(offer_sequence=sequence, tx_hash=tx_hash, validated=True)

    def _mock_finish_escrow(self) -> TxSubmitResult:
        return TxSubmitResult(tx_hash=uuid4().hex, validated=True)

    def _mock_cancel_escrow(self) -> TxSubmitResult:
        return TxSubmitResult(tx_hash=uuid4().hex, validated=True)

    def _real_create_escrow(
        self,
        payer_seed: str,
        payer_address: str,
        amount_drops: str,
        destination: str,
        cancel_after: int,
        condition: Optional[str],
    ) -> EscrowResult:
        if not payer_seed:
            raise XrplServiceError("Missing payer seed for XRPL escrow create")
        if not self._client:
            raise XrplServiceError("XRPL client not initialized")
        from xrpl.wallet import Wallet
        from xrpl.models.transactions import EscrowCreate
        from xrpl.transaction import submit_and_wait

        wallet = self._wallet_from_seed(payer_seed)
        tx = EscrowCreate(
            account=wallet.classic_address,
            amount=amount_drops,
            destination=destination,
            cancel_after=cancel_after,
            condition=condition,
        )
        result = submit_and_wait(tx, self._client, wallet).result
        tx_hash = result.get("hash", uuid4().hex)
        offer_sequence = result.get("tx_json", {}).get("Sequence")
        if offer_sequence is None:
            offer_sequence = signed.sequence
        validated = result.get("validated", False)
        return EscrowResult(offer_sequence=int(offer_sequence), tx_hash=tx_hash, validated=validated)

    def _real_finish_escrow(
        self,
        merchant_seed: str,
        owner_address: str,
        offer_sequence: int,
        fulfillment: Optional[str],
    ) -> TxSubmitResult:
        if not merchant_seed:
            raise XrplServiceError("Missing merchant seed for XRPL escrow finish")
        if not self._client:
            raise XrplServiceError("XRPL client not initialized")
        from xrpl.wallet import Wallet
        from xrpl.models.transactions import EscrowFinish
        from xrpl.transaction import submit_and_wait

        wallet = self._wallet_from_seed(merchant_seed)
        tx = EscrowFinish(
            account=wallet.classic_address,
            owner=owner_address,
            offer_sequence=offer_sequence,
            fulfillment=fulfillment,
        )
        result = submit_and_wait(tx, self._client, wallet).result
        tx_hash = result.get("hash", uuid4().hex)
        return TxSubmitResult(tx_hash=tx_hash, validated=result.get("validated", False))

    def _real_cancel_escrow(
        self,
        merchant_seed: str,
        owner_address: str,
        offer_sequence: int,
    ) -> TxSubmitResult:
        if not merchant_seed:
            raise XrplServiceError("Missing merchant seed for XRPL escrow cancel")
        if not self._client:
            raise XrplServiceError("XRPL client not initialized")
        from xrpl.wallet import Wallet
        from xrpl.models.transactions import EscrowCancel
        from xrpl.transaction import submit_and_wait

        wallet = self._wallet_from_seed(merchant_seed)
        tx = EscrowCancel(
            account=wallet.classic_address,
            owner=owner_address,
            offer_sequence=offer_sequence,
        )
        result = submit_and_wait(tx, self._client, wallet).result
        tx_hash = result.get("hash", uuid4().hex)
        return TxSubmitResult(tx_hash=tx_hash, validated=result.get("validated", False))


@dataclass
class XrplEscrowEvent:
    handle: str
    offer_sequence: int
    tx_hash: str
    timestamp: datetime

    @classmethod
    def from_result(cls, handle: str, result: EscrowResult) -> "XrplEscrowEvent":
        return cls(
            handle=handle,
            offer_sequence=result.offer_sequence,
            tx_hash=result.tx_hash,
            timestamp=datetime.now(timezone.utc),
        )
