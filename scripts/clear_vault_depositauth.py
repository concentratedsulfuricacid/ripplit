import os
from dotenv import load_dotenv
from pathlib import Path
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import AccountSet, AccountSetAsfFlag
from xrpl.transaction import submit_and_wait

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_PATH)

rpc = os.getenv("XRPL_RPC", "https://testnet.xrpl-labs.com/")
vault_seed = os.getenv("VAULT_SEED")
if not vault_seed:
    raise RuntimeError("Missing VAULT_SEED in .env")

client = JsonRpcClient(rpc)

# Handle both seed types (sEd... = ED25519)
try:
    vault = Wallet.from_seed(vault_seed)  # usually OK
except Exception:
    from xrpl.core.keypairs.main import CryptoAlgorithm
    algo = CryptoAlgorithm.ED25519 if vault_seed.startswith("sEd") else CryptoAlgorithm.SECP256K1
    vault = Wallet.from_seed(vault_seed, algorithm=algo)

tx = AccountSet(
    account=vault.classic_address,
    clear_flag=AccountSetAsfFlag.ASF_DEPOSIT_AUTH,  # clears DepositAuth
)

result = submit_and_wait(tx, client, vault).result
print("AccountSet result:", result)
print("Vault address:", vault.classic_address)
