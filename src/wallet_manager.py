import json
import secrets
from pathlib import Path

import bip39
from web3 import Web3


ETHEREUM_ACCOUNT_PATH = "m/44'/60'/0'/0/0"


def generate_wallet() -> dict[str, str]:
    entropy = secrets.token_bytes(16)
    mnemonic = bip39.encode_bytes(entropy)

    account_api = Web3().eth.account
    account_api.enable_unaudited_hdwallet_features()
    account = account_api.from_mnemonic(
        mnemonic,
        account_path=ETHEREUM_ACCOUNT_PATH,
    )

    return {
        "private_key": Web3.to_hex(account.key),
        "address": account.address,
        "mnemonic": mnemonic,
    }


def save_wallet(wallet_data: dict[str, str], filename: str | Path) -> None:
    output_path = Path(filename)
    if output_path.suffix.lower() != ".json":
        output_path = output_path.with_suffix(".json")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as wallet_file:
        json.dump(wallet_data, wallet_file, indent=2)
        wallet_file.write("\n")
