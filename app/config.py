from dataclasses import dataclass
from datetime import datetime, timezone
import os


RIPPLE_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Settings:
    app_name: str = "XRPL GroupPay Demo"
    xrpl_mode: str = os.getenv("XRPL_MODE", "mock")
    xrpl_json_rpc_url: str = os.getenv(
        "XRPL_JSON_RPC_URL", "https://s.altnet.rippletest.net:51234"
    )
    merchant_address: str = os.getenv(
        "MERCHANT_ADDRESS", "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"
    )
    merchant_seed: str = os.getenv("MERCHANT_SEED", "")
    default_deadline_minutes: int = int(os.getenv("DEFAULT_DEADLINE_MINUTES", "15"))
    auto_finish: bool = os.getenv("AUTO_FINISH", "true").lower() == "true"
    use_condition: bool = os.getenv("USE_ESCROW_CONDITION", "true").lower() == "true"
    api_key: str = os.getenv("API_KEY", "")
    ledger_poll_seconds: int = int(os.getenv("LEDGER_POLL_SECONDS", "8"))
    enable_ledger_polling: bool = (
        os.getenv("ENABLE_LEDGER_POLLING", "true").lower() == "true"
    )
    use_ledger_did: bool = os.getenv("USE_LEDGER_DID", "true").lower() == "true"


settings = Settings()


def to_ripple_time(dt: datetime) -> int:
    return int((dt.astimezone(timezone.utc) - RIPPLE_EPOCH).total_seconds())
