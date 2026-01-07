from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Dict, List, Optional
from uuid import uuid4

from .config import Settings, to_ripple_time
from .did_registry import DidRegistry
from .models import (
    GroupRequest,
    GroupStatus,
    Order,
    OrderStatus,
    Participant,
    ParticipantStatus,
)
from .state import StateStore
from .xrpl_service import XrplEscrowEvent, XrplService, XrplServiceError


DROPS_PER_XRP = 1_000_000


def xrp_to_drops(amount_xrp: float) -> str:
    return str(int(round(amount_xrp * DROPS_PER_XRP)))


class GroupPayService:
    def __init__(
        self,
        settings: Settings,
        state: StateStore,
        registry: DidRegistry,
        xrpl_service: XrplService,
    ) -> None:
        self.settings = settings
        self.state = state
        self.registry = registry
        self.xrpl = xrpl_service

    def create_group_request(
        self,
        order: Order,
        participants: List[str],
        split: str,
        custom_amounts: Optional[Dict[str, float]],
        deadline_minutes: Optional[int],
    ) -> GroupRequest:
        contacts = []
        for handle in participants:
            contact = self.registry.get_contact(handle)
            if not contact:
                raise ValueError(f"Unknown handle: {handle}")
            contacts.append(contact)

        amounts = self._split_amounts(order.total_xrp, participants, split, custom_amounts)
        deadline = datetime.now(timezone.utc) + timedelta(
            minutes=deadline_minutes or self.settings.default_deadline_minutes
        )
        fulfillment = None
        condition = None
        if self.settings.use_condition:
            condition_payload = self.xrpl.generate_condition()
            condition = condition_payload["condition"]
            fulfillment = condition_payload["fulfillment"]

        participant_rows: List[Participant] = []
        for contact in contacts:
            amount_xrp = amounts[contact.handle]
            participant_rows.append(
                Participant(
                    handle=contact.handle,
                    address=contact.address,
                    amount_xrp=amount_xrp,
                    amount_drops=xrp_to_drops(amount_xrp),
                )
            )

        terms_hash = self._terms_hash(order, participant_rows, deadline, condition)
        request = GroupRequest(
            id=uuid4().hex,
            order_id=order.id,
            terms_hash=terms_hash,
            participants=participant_rows,
            deadline=deadline,
            condition=condition,
            fulfillment=fulfillment,
            status=GroupStatus.FUNDING,
            created_at=datetime.now(timezone.utc),
        )
        order.status = OrderStatus.FUNDING
        order.request_id = request.id
        self.state.save_order(order)
        self.state.save_group_request(request)
        return request

    def pay_share(self, request_id: str, handle: str) -> GroupRequest:
        request = self.state.get_group_request(request_id)
        self._expire_if_needed(request)
        if request.status in {GroupStatus.PAID, GroupStatus.EXPIRED}:
            raise ValueError("Request is no longer payable")
        participant = self._get_participant(request, handle)
        if participant.status in {ParticipantStatus.ESCROWED, ParticipantStatus.FINISHED}:
            return request

        seed = self.registry.get_seed(handle)
        if self.xrpl.mode != "mock" and not seed:
            raise XrplServiceError(f"Missing seed for {handle} in XRPL mode")

        cancel_after = to_ripple_time(request.deadline)
        escrow_result = self.xrpl.create_escrow(
            payer_seed=seed or "",
            payer_address=participant.address,
            amount_drops=participant.amount_drops,
            destination=self.settings.merchant_address,
            cancel_after=cancel_after,
            condition=request.condition,
        )
        event = XrplEscrowEvent.from_result(handle, escrow_result)
        participant.status = ParticipantStatus.ESCROWED
        participant.escrow = self._new_escrow(participant.address, event, request.condition)
        request.status = GroupStatus.FUNDING
        self.state.save_group_request(request)
        self._maybe_finish(request)
        return request

    def finish_request(self, request_id: str) -> GroupRequest:
        request = self.state.get_group_request(request_id)
        self._finish_all(request)
        return request

    def refresh_request(self, request_id: str) -> GroupRequest:
        request = self.state.get_group_request(request_id)
        self.sync_with_ledger(requests=[request])
        self._expire_if_needed(request)
        return request

    def list_requests(self) -> List[GroupRequest]:
        requests = self.state.list_group_requests()
        self.sync_with_ledger(requests=requests)
        for request in requests:
            self._expire_if_needed(request)
        return requests

    def sync_with_ledger(self, requests: Optional[List[GroupRequest]] = None) -> None:
        if self.xrpl.mode == "mock":
            return
        active_requests = requests or self.state.list_group_requests()
        now = datetime.now(timezone.utc)
        for request in active_requests:
            if request.status in {GroupStatus.PAID, GroupStatus.EXPIRED}:
                continue
            cancel_after = to_ripple_time(request.deadline)
            for participant in request.participants:
                if participant.status == ParticipantStatus.UNPAID:
                    match = self.xrpl.find_escrow_create(
                        owner_address=participant.address,
                        destination=self.settings.merchant_address,
                        amount_drops=participant.amount_drops,
                        condition=request.condition,
                        cancel_after=cancel_after,
                    )
                    if match and match.validated:
                        event = XrplEscrowEvent.from_result(participant.handle, match)
                        participant.status = ParticipantStatus.ESCROWED
                        participant.escrow = self._new_escrow(
                            participant.address, event, request.condition
                        )
                if participant.status == ParticipantStatus.ESCROWED and participant.escrow:
                    finish = self.xrpl.find_escrow_finish(
                        merchant_address=self.settings.merchant_address,
                        owner_address=participant.address,
                        offer_sequence=participant.escrow.offer_sequence,
                    )
                    if finish and finish.validated:
                        participant.status = ParticipantStatus.FINISHED
                        participant.escrow.finish_tx_hash = finish.tx_hash
                        participant.escrow.finished_at = now
                        continue
                    cancel = self.xrpl.find_escrow_cancel(
                        merchant_address=self.settings.merchant_address,
                        owner_address=participant.address,
                        offer_sequence=participant.escrow.offer_sequence,
                    )
                    if cancel and cancel.validated:
                        participant.status = ParticipantStatus.REFUNDED
                        participant.escrow.cancel_tx_hash = cancel.tx_hash
                        participant.escrow.canceled_at = now

            if all(p.status == ParticipantStatus.FINISHED for p in request.participants):
                request.status = GroupStatus.PAID
                order = self.state.get_order(request.order_id)
                order.status = OrderStatus.PAID
                self.state.save_order(order)
            elif all(
                p.status in {ParticipantStatus.ESCROWED, ParticipantStatus.FINISHED}
                for p in request.participants
            ):
                request.status = GroupStatus.READY
            else:
                request.status = GroupStatus.FUNDING

            self.state.save_group_request(request)

    def _split_amounts(
        self,
        total_xrp: float,
        participants: List[str],
        split: str,
        custom_amounts: Optional[Dict[str, float]],
    ) -> Dict[str, float]:
        if split == "custom":
            if not custom_amounts:
                raise ValueError("custom_amounts required for custom split")
            total = round(sum(custom_amounts.values()), 6)
            if round(total_xrp, 6) != total:
                raise ValueError("Custom amounts must sum to total")
            return custom_amounts

        count = len(participants)
        if count == 0:
            raise ValueError("Participants required")
        share = round(total_xrp / count, 6)
        amounts = {handle: share for handle in participants}
        remainder = round(total_xrp - sum(amounts.values()), 6)
        if remainder != 0:
            amounts[participants[-1]] = round(amounts[participants[-1]] + remainder, 6)
        return amounts

    def _terms_hash(
        self,
        order: Order,
        participants: List[Participant],
        deadline: datetime,
        condition: Optional[str],
    ) -> str:
        payload = {
            "order_id": order.id,
            "amounts": {p.handle: p.amount_xrp for p in participants},
            "deadline": deadline.isoformat(),
            "merchant": self.settings.merchant_address,
            "participants": [p.handle for p in participants],
            "condition": condition,
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _get_participant(self, request: GroupRequest, handle: str) -> Participant:
        for participant in request.participants:
            if participant.handle == handle:
                return participant
        raise ValueError(f"Handle {handle} not part of request")

    def _maybe_finish(self, request: GroupRequest) -> None:
        if not self.settings.auto_finish:
            return
        if any(p.status != ParticipantStatus.ESCROWED for p in request.participants):
            return
        request.status = GroupStatus.READY
        self._finish_all(request)

    def _finish_all(self, request: GroupRequest) -> None:
        if request.status in {GroupStatus.PAID, GroupStatus.EXPIRED}:
            return
        if any(p.status == ParticipantStatus.UNPAID for p in request.participants):
            request.status = GroupStatus.FUNDING
            self.state.save_group_request(request)
            return
        for participant in request.participants:
            if participant.status != ParticipantStatus.ESCROWED or not participant.escrow:
                continue
            result = self.xrpl.finish_escrow(
                merchant_seed=self.settings.merchant_seed,
                owner_address=participant.address,
                offer_sequence=participant.escrow.offer_sequence,
                fulfillment=request.fulfillment,
            )
            if result.validated:
                participant.status = ParticipantStatus.FINISHED
                participant.escrow.finished_at = datetime.now(timezone.utc)
                participant.escrow.finish_tx_hash = result.tx_hash
        if all(p.status == ParticipantStatus.FINISHED for p in request.participants):
            request.status = GroupStatus.PAID
            order = self.state.get_order(request.order_id)
            order.status = OrderStatus.PAID
            self.state.save_order(order)
        self.state.save_group_request(request)

    def _expire_if_needed(self, request: GroupRequest) -> None:
        if request.status in {GroupStatus.PAID, GroupStatus.EXPIRED}:
            return
        if datetime.now(timezone.utc) <= request.deadline:
            return
        for participant in request.participants:
            if participant.escrow and participant.status == ParticipantStatus.ESCROWED:
                result = self.xrpl.cancel_escrow(
                    merchant_seed=self.settings.merchant_seed,
                    owner_address=participant.address,
                    offer_sequence=participant.escrow.offer_sequence,
                )
                if result.validated:
                    participant.status = ParticipantStatus.REFUNDED
                    participant.escrow.canceled_at = datetime.now(timezone.utc)
                    participant.escrow.cancel_tx_hash = result.tx_hash
        request.status = GroupStatus.EXPIRED
        order = self.state.get_order(request.order_id)
        order.status = OrderStatus.EXPIRED
        self.state.save_order(order)
        self.state.save_group_request(request)

    def _new_escrow(
        self,
        owner_address: str,
        event: XrplEscrowEvent,
        condition: Optional[str],
    ) -> "EscrowRef":
        from .models import EscrowRef

        return EscrowRef(
            owner_address=owner_address,
            offer_sequence=event.offer_sequence,
            tx_hash=event.tx_hash,
            condition=condition,
            created_at=event.timestamp,
        )
