# ripplit/app/config.py
XRPL_TESTNET_JSON_RPC = "https://s.altnet.rippletest.net:51234"

# Escrow timing (seconds)
ESCROW_FINISH_AFTER_S = 3
ESCROW_CANCEL_AFTER_S = 900  # refund window later (not required for MVP demo)

# App-level "payment request expires" timer
REQUEST_EXPIRES_S = 120  # after 2 mins, mark Expired in history/UI
