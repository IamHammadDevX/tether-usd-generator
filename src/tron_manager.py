import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from solcx import (
    compile_standard,
    get_installed_solc_versions,
    install_solc,
)
from tronpy import Contract, Tron
from tronpy.keys import PrivateKey


SOLC_VERSION = "0.8.17"
TOKEN_DECIMALS = 6
DEPLOY_FEE_LIMIT = 1_000_000_000
MINT_FEE_LIMIT = 100_000_000

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = PROJECT_ROOT / "contracts" / "FlashUSDT.sol"
OPENZEPPELIN_PATH = (
    PROJECT_ROOT / "node_modules" / "@openzeppelin" / "contracts"
)
ARTIFACT_PATH = PROJECT_ROOT / "build" / "FlashUSDT.tron.json"


def _private_key(private_key_hex: str) -> PrivateKey:
    normalized_key = private_key_hex.strip()
    if normalized_key.startswith(("0x", "0X")):
        normalized_key = normalized_key[2:]

    if len(normalized_key) != 64:
        raise ValueError("TRON private key must contain exactly 64 hex characters.")

    try:
        return PrivateKey.fromhex(normalized_key)
    except (TypeError, ValueError) as error:
        raise ValueError("TRON private key is not valid hexadecimal.") from error


def _compile_flash_usdt() -> dict:
    if not CONTRACT_PATH.is_file():
        raise FileNotFoundError(f"Contract not found: {CONTRACT_PATH}")

    if not OPENZEPPELIN_PATH.is_dir():
        raise FileNotFoundError(
            "OpenZeppelin contracts not found. Install them with: "
            "npm install @openzeppelin/contracts@^4.7.0"
        )

    installed_versions = {str(version) for version in get_installed_solc_versions()}
    if SOLC_VERSION not in installed_versions:
        install_solc(SOLC_VERSION)

    compiler_input = {
        "language": "Solidity",
        "sources": {
            "contracts/FlashUSDT.sol": {
                "content": CONTRACT_PATH.read_text(encoding="utf-8"),
            }
        },
        "settings": {
            "optimizer": {
                "enabled": True,
                "runs": 200,
            },
            "remappings": [
                "@openzeppelin/=node_modules/@openzeppelin/",
            ],
            "outputSelection": {
                "*": {
                    "*": [
                        "abi",
                        "evm.bytecode.object",
                    ]
                }
            },
        },
    }

    compiled = compile_standard(
        compiler_input,
        solc_version=SOLC_VERSION,
        base_path=str(PROJECT_ROOT),
        allow_paths=str(PROJECT_ROOT),
    )
    contract_data = compiled["contracts"]["contracts/FlashUSDT.sol"]["FlashUSDT"]
    artifact = {
        "contractName": "FlashUSDT",
        "abi": contract_data["abi"],
        "bytecode": contract_data["evm"]["bytecode"]["object"],
    }

    if not artifact["bytecode"]:
        raise RuntimeError("Compiler returned empty FlashUSDT bytecode.")

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(artifact, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifact


def _token_units(amount_usdt: int | float | str | Decimal) -> int:
    try:
        amount = Decimal(str(amount_usdt))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("amount_usdt must be a valid number.") from error

    if not amount.is_finite() or amount <= 0:
        raise ValueError("amount_usdt must be greater than zero.")

    units = amount * (10**TOKEN_DECIMALS)
    if units != units.to_integral_value():
        raise ValueError("amount_usdt cannot have more than 6 decimal places.")

    return int(units)


def deploy_tron_token(
    tron_client: Tron,
    owner_private_key_hex: str,
) -> str:
    tron_client.get_latest_block_number()
    owner_private_key = _private_key(owner_private_key_hex)
    owner_address = owner_private_key.public_key.to_base58check_address()
    artifact = _compile_flash_usdt()

    contract = Contract(
        name=artifact["contractName"],
        bytecode=artifact["bytecode"],
        abi=artifact["abi"],
    )
    transaction = (
        tron_client.trx.deploy_contract(owner_address, contract)
        .fee_limit(DEPLOY_FEE_LIMIT)
        .build()
        .sign(owner_private_key)
    )
    result = transaction.broadcast()
    receipt = result.wait(timeout=180)

    receipt_status = receipt.get("receipt", {}).get("result")
    contract_address = receipt.get("contract_address")
    if receipt_status != "SUCCESS" or not contract_address:
        raise RuntimeError(
            "TRON deployment failed: "
            + json.dumps(receipt, separators=(",", ":"), default=str)
        )

    print(f"Contract Address: {contract_address}")
    print(f"Transaction ID: {transaction.txid}")
    return contract_address


def mint_tron_tokens(
    tron_client: Tron,
    contract_address: str,
    owner_private_key_hex: str,
    recipient_address: str,
    amount_usdt: int | float | str | Decimal,
) -> str:
    tron_client.get_latest_block_number()
    if not tron_client.is_base58check_address(contract_address):
        raise ValueError("Invalid TRON contract address.")
    if not tron_client.is_base58check_address(recipient_address):
        raise ValueError("Invalid TRON recipient address.")

    owner_private_key = _private_key(owner_private_key_hex)
    owner_address = owner_private_key.public_key.to_base58check_address()
    amount_units = _token_units(amount_usdt)
    contract = tron_client.get_contract(contract_address)

    transaction = (
        contract.functions.mint(recipient_address, amount_units)
        .with_owner(owner_address)
        .fee_limit(MINT_FEE_LIMIT)
        .build()
        .sign(owner_private_key)
    )
    result = transaction.broadcast()
    receipt = result.wait(timeout=120)

    receipt_status = receipt.get("receipt", {}).get("result")
    if receipt_status != "SUCCESS":
        raise RuntimeError(
            "TRON mint failed: "
            + json.dumps(receipt, separators=(",", ":"), default=str)
        )

    print(f"Transaction ID: {transaction.txid}")
    return transaction.txid

