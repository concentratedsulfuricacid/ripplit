from xrpl.clients import JsonRpcClient
from xrpl.wallet import generate_faucet_wallet
XRPL_RPC = "https://testnet.xrpl-labs.com/"

# XRPL_RPC = "https://s.altnet.rippletest.net:51234"  # testnet JSON-RPC
client = JsonRpcClient(XRPL_RPC)

def mk(name: str):
    w = generate_faucet_wallet(client)
    print(f"{name}_SEED={w.seed}")
    print(f"{name}_ADDRESS={w.classic_address}")
    print()

if __name__ == "__main__":
    for n in ["ALICE", "BOB", "CHEN", "VAULT", "MERCHANT"]:
        mk(n)
