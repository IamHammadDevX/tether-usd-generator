from pathlib import Path
from time import sleep
from typing import Callable, TypeVar

from solcx import (
    compile_standard,
    get_installed_solc_versions,
    install_solc,
    link_code,
)
from web3 import Web3
from web3.exceptions import ContractLogicError, TimeExhausted


SOLC_VERSION = "0.8.17"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = PROJECT_ROOT / "contracts" / "FlashUSDT.sol"
OPENZEPPELIN_PATH = (
    PROJECT_ROOT / "node_modules" / "@openzeppelin" / "contracts"
)
SUPPORTED_NETWORKS = {"ethereum", "eth", "polygon", "bsc", "binance smart chain"}
RPC_RESULT = TypeVar("RPC_RESULT")


def _rpc_call(
    operation_name: str,
    operation: Callable[[], RPC_RESULT],
    attempts: int = 3,
) -> RPC_RESULT:
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except ValueError as error:
            message = str(error).lower()
            retryable = (
                "-32046" in message
                or "cannot fulfill request" in message
                or "temporarily unavailable" in message
                or "rate limit" in message
            )
            if not retryable or attempt == attempts:
                raise RuntimeError(
                    f"RPC operation '{operation_name}' failed: {error}"
                ) from error
            sleep(attempt * 2)

    raise RuntimeError(f"RPC operation '{operation_name}' failed.")


def compile_contract() -> tuple[list, str]:
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

    source = CONTRACT_PATH.read_text(encoding="utf-8")
    compiler_input = {
        "language": "Solidity",
        "sources": {
            "contracts/FlashUSDT.sol": {
                "content": source,
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
    abi = contract_data["abi"]
    bytecode = contract_data["evm"]["bytecode"]["object"]

    if not bytecode:
        raise RuntimeError("Compiler returned empty contract bytecode.")

    # FlashUSDT currently has no external libraries; this preserves support if
    # library placeholders are added later.
    bytecode = link_code(bytecode, {}, solc_version=SOLC_VERSION)
    return abi, bytecode


def deploy_token(network_name: str, private_key: str, rpc_url: str) -> str:
    normalized_network = network_name.strip().lower()
    if normalized_network not in SUPPORTED_NETWORKS:
        raise ValueError(
            f"Unsupported network '{network_name}'. Use Ethereum, Polygon, or BSC."
        )

    try:
        web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        if not web3.is_connected():
            raise ConnectionError(f"Could not connect to {network_name}: {rpc_url}")

        account = web3.eth.account.from_key(private_key)
        abi, bytecode = compile_contract()
        contract = web3.eth.contract(abi=abi, bytecode=bytecode)

        nonce = _rpc_call(
            "get pending nonce",
            lambda: web3.eth.get_transaction_count(account.address, "pending"),
        )
        gas_price = _rpc_call("get gas price", lambda: web3.eth.gas_price)
        chain_id = _rpc_call("get chain ID", lambda: web3.eth.chain_id)
        constructor = contract.constructor()

        transaction_parameters = {
            "from": account.address,
            "nonce": nonce,
            "chainId": chain_id,
            "gasPrice": gas_price,
        }
        estimated_gas = _rpc_call(
            "estimate deployment gas",
            lambda: constructor.estimate_gas(transaction_parameters),
        )
        transaction_parameters["gas"] = (estimated_gas * 120 + 99) // 100

        transaction = constructor.build_transaction(transaction_parameters)
        signed_transaction = account.sign_transaction(transaction)
        raw_transaction = getattr(signed_transaction, "raw_transaction", None)
        if raw_transaction is None:
            raw_transaction = signed_transaction.rawTransaction

        def broadcast_signed_transaction():
            try:
                return web3.eth.send_raw_transaction(raw_transaction)
            except ValueError as error:
                if "already known" in str(error).lower():
                    return Web3.keccak(raw_transaction)
                raise

        transaction_hash = _rpc_call(
            "broadcast deployment transaction",
            broadcast_signed_transaction,
        )
        receipt = _rpc_call(
            "wait for deployment receipt",
            lambda: web3.eth.wait_for_transaction_receipt(
                transaction_hash,
                timeout=300,
                poll_latency=2,
            ),
        )

        if receipt.status != 1:
            raise RuntimeError(
                f"Deployment transaction reverted: {transaction_hash.hex()}"
            )

        contract_address = Web3.to_checksum_address(receipt.contractAddress)
        print(f"Contract Address: {contract_address}")
        print(f"Transaction Hash: {transaction_hash.hex()}")
        return contract_address

    except (ValueError, ContractLogicError, TimeExhausted) as error:
        raise RuntimeError(
            f"{network_name} deployment failed. Check private key, nonce, "
            f"account balance, gas settings, and RPC response: {error}"
        ) from error


if __name__ == "__main__":
    POLYGON_PRIVATE_KEY = "0xYOUR_PRIVATE_KEY"
    POLYGON_RPC_URL = "https://polygon-rpc.com"

    try:
        deploy_token(
            network_name="Polygon",
            private_key=POLYGON_PRIVATE_KEY,
            rpc_url=POLYGON_RPC_URL,
        )
    except Exception as error:
        print(f"Deployment error: {error}")
