from decimal import Decimal, InvalidOperation

from web3 import Web3
from web3.exceptions import ContractLogicError, TimeExhausted


TOKEN_DECIMALS = 6
FALLBACK_GAS_LIMIT = 65_000
TRANSFER_ABI = [
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "account",
                "type": "address",
            }
        ],
        "name": "balanceOf",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "to",
                "type": "address",
            },
            {
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256",
            },
        ],
        "name": "transfer",
        "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool",
            }
        ],
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


def send_tokens(
    network_rpc: str,
    contract_address: str,
    sender_private_key: str,
    recipient_address: str,
    amount_usdt: int | float | str | Decimal,
) -> str:
    amount, amount_units = _token_units(amount_usdt)
    web3 = Web3(Web3.HTTPProvider(network_rpc, request_kwargs={"timeout": 30}))

    if not web3.is_connected():
        raise ConnectionError(f"Could not connect to RPC endpoint: {network_rpc}")

    try:
        sender = web3.eth.account.from_key(sender_private_key)
        checksum_contract = Web3.to_checksum_address(contract_address)
        checksum_recipient = Web3.to_checksum_address(recipient_address)
        contract = web3.eth.contract(address=checksum_contract, abi=TRANSFER_ABI)
        transfer_call = contract.functions.transfer(
            checksum_recipient,
            amount_units,
        )
        sender_balance = contract.functions.balanceOf(sender.address).call()
        if sender_balance < amount_units:
            available_usdt = Decimal(sender_balance) / (10**TOKEN_DECIMALS)
            raise RuntimeError(
                "Insufficient token balance. "
                f"Available: {format(available_usdt, 'f')} USDT; "
                f"requested: {format(amount, 'f')} USDT."
            )

        transaction_parameters = {
            "from": sender.address,
            "nonce": web3.eth.get_transaction_count(sender.address, "pending"),
            "chainId": web3.eth.chain_id,
            "gasPrice": web3.eth.gas_price,
        }

        estimated_gas = transfer_call.estimate_gas(transaction_parameters)
        transaction_parameters["gas"] = max(
            (estimated_gas * 120 + 99) // 100,
            FALLBACK_GAS_LIMIT,
        )

        transaction = transfer_call.build_transaction(transaction_parameters)
        signed_transaction = sender.sign_transaction(transaction)
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
                f"Transfer transaction reverted: {transaction_hash.hex()}"
            )

        transaction_hash_hex = transaction_hash.hex()
        print(
            f"Sent {format(amount, 'f')} USDT to {checksum_recipient}. "
            f"Tx Hash: {transaction_hash_hex}"
        )
        return transaction_hash_hex

    except ContractLogicError as error:
        raise RuntimeError(
            f"Transfer reverted. Check token balance and recipient: {error}"
        ) from error
    except TimeExhausted as error:
        raise TimeoutError(
            "Transfer was sent but receipt confirmation timed out."
        ) from error
    except ValueError as error:
        message = str(error)
        lowered = message.lower()
        if "insufficient funds" in lowered:
            raise RuntimeError(
                f"Sender lacks native tokens for gas: {message}"
            ) from error
        if "nonce" in lowered or "replacement transaction underpriced" in lowered:
            raise RuntimeError(
                f"Nonce error; refresh pending nonce and retry: {message}"
            ) from error
        raise RuntimeError(f"RPC rejected the transfer: {message}") from error
