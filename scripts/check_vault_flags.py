import os
from dotenv import load_dotenv
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_PATH)

rpc = os.getenv("XRPL_RPC", "https://testnet.xrpl-labs.com/")
vault_addr = os.getenv("VAULT_ADDRESS")  # optional, if you saved it
vault_seed = os.getenv("VAULT_SEED")

client = JsonRpcClient(rpc)

# If you didn't store VAULT_ADDRESS, just print it from your app logs or add it to .env once.
if not vault_addr:
    raise RuntimeError("Set VAULT_ADDRESS in .env (your vault classic address)")

res = client.request(AccountInfo(account=vault_addr, ledger_index="validated")).result
print(res["account_data"].get("Flags"))
print(res["account_data"])
