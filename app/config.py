XRPL_TESTNET_JSON_RPC = "https://s.altnet.rippletest.net:51234"

# Escrow timing (seconds)
ESCROW_FINISH_AFTER_S = 3
ESCROW_CANCEL_AFTER_S = 900  # not used for refunds in MVP, but required by tx

# App-level "payment request expires" timer
REQUEST_EXPIRES_S = 120  # 2 mins -> mark as Expired in history/UI

DEMO_TOKEN_CODE = "RUSD" 
DEMO_TOKEN_NAME = "RLUSD-demo"