from decimal import Decimal, InvalidOperation

from web3 import Web3
from web3.exceptions import ContractLogicError, TimeExhausted


TOKEN_DECIMALS = 6
MINT_ABI = [
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "account",
                "type": "address",
            },
            {
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256",
            },
        ],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


def _token_units(amount_usdt: int | float | str | Decimal) -> tuple[Decimal, int]:
    try:
        amount = Decimal(str(amount_usdt))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("amount_usdt must be a valid number.") from error

    if not amount.is_finite() or amount <= 0:
        raise ValueError("amount_usdt must be greater than zero.")

    units = amount * (10**TOKEN_DECIMALS)
    if units != units.to_integral_value():
        raise ValueError("amount_usdt cannot have more than 6 decimal places.")

    return amount, int(units)


def _rpc_error_message(error: ValueError) -> str:
    message = str(error)
    lowered = message.lower()

    if "insufficient funds" in lowered or "intrinsic gas too low" in lowered:
        return f"Insufficient Gas: fund the owner wallet with native tokens. {message}"

    nonce_errors = (
        "nonce too low",
        "nonce too high",
        "invalid nonce",
        "replacement transaction underpriced",
        "already known",
    )
    if any(text in lowered for text in nonce_errors):
        return f"Wrong Nonce: refresh the pending nonce and retry. {message}"

    return f"RPC rejected the mint transaction: {message}"


def mint_tokens(
    network_rpc: str,
    contract_address: str,
    owner_private_key: str,
    recipient_address: str,
    amount_usdt: int | float | str | Decimal,
) -> str:
    amount, amount_units = _token_units(amount_usdt)
    web3 = Web3(Web3.HTTPProvider(network_rpc, request_kwargs={"timeout": 30}))

    if not web3.is_connected():
        raise ConnectionError(f"Could not connect to RPC endpoint: {network_rpc}")

    try:
        owner = web3.eth.account.from_key(owner_private_key)
        checksum_contract = Web3.to_checksum_address(contract_address)
        checksum_recipient = Web3.to_checksum_address(recipient_address)
        contract = web3.eth.contract(address=checksum_contract, abi=MINT_ABI)

        mint_call = contract.functions.mint(checksum_recipient, amount_units)
        transaction_parameters = {
            "from": owner.address,
            "nonce": web3.eth.get_transaction_count(owner.address, "pending"),
            "chainId": web3.eth.chain_id,
            "gasPrice": web3.eth.gas_price,
        }
        estimated_gas = mint_call.estimate_gas(transaction_parameters)
        transaction_parameters["gas"] = (estimated_gas * 120 + 99) // 100

        transaction = mint_call.build_transaction(transaction_parameters)
        signed_transaction = owner.sign_transaction(transaction)
        raw_transaction = getattr(signed_transaction, "raw_transaction", None)
        if raw_transaction is None:
            raw_transaction = signed_transaction.rawTransaction
        transaction_hash = web3.eth.send_raw_transaction(raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(
            transaction_hash,
            timeout=300,
            poll_latency=2,
        )

        if receipt.status != 1:
            raise RuntimeError(
                f"Mint transaction reverted: {transaction_hash.hex()}"
            )

        transaction_hash_hex = transaction_hash.hex()
        print(
            f"Minted {format(amount, 'f')} USDT to {checksum_recipient}. "
            f"Tx Hash: {transaction_hash_hex}"
        )
        return transaction_hash_hex

    except ContractLogicError as error:
        raise RuntimeError(
            "Mint reverted. Confirm the signer owns the contract and the "
            f"recipient is valid: {error}"
        ) from error
    except TimeExhausted as error:
        raise TimeoutError(
            "Mint transaction was sent but receipt confirmation timed out."
        ) from error
    except ValueError as error:
        raise RuntimeError(_rpc_error_message(error)) from error
