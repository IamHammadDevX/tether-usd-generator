"""Add liquidity to Uniswap V2 (Ethereum/Polygon) or PancakeSwap V2 (BSC).

Supports:
- Uniswap V2 on Ethereum Mainnet
- Uniswap V2 on Polygon (via Quickswap, a Uniswap V2 fork)
- PancakeSwap V2 on BNB Smart Chain
"""

from decimal import Decimal, InvalidOperation

from web3 import Web3
from web3.exceptions import ContractLogicError, TimeExhausted


# ── Token constants ─────────────────────────────────────────────────────────
TOKEN_DECIMALS = 6

# ── Uniswap V2 Factory addresses ────────────────────────────────────────────
UNISWAP_V2_FACTORY_ETH = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
UNISWAP_V2_FACTORY_POLYGON = "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32"  # Quickswap

# ── Uniswap V2 Router addresses ────────────────────────────────────────────
UNISWAP_V2_ROUTER_ETH = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
UNISWAP_V2_ROUTER_POLYGON = "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff"  # Quickswap

# ── Wrapped native token addresses ──────────────────────────────────────────
WETH_ETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
WMATIC_POLYGON = "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270"
WBNB_BSC = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"

# ── PancakeSwap V2 addresses (BSC) ─────────────────────────────────────────
PANCAKESWAP_V2_FACTORY_BSC = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
PANCAKESWAP_V2_ROUTER_BSC = "0x10ED43C718714eb63d5aA57B78B54704E256024E"

# ── Minimal ERC-20 ABI (approve + balanceOf + decimals) ────────────────────
ERC20_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# ── Uniswap V2 / PancakeSwap V2 Router ABI (addLiquidityETH + factory + WETH) ──
ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "uint256", "name": "amountTokenDesired", "type": "uint256"},
            {"internalType": "uint256", "name": "amountTokenMin", "type": "uint256"},
            {"internalType": "uint256", "name": "amountETHMin", "type": "uint256"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
        ],
        "name": "addLiquidityETH",
        "outputs": [
            {"internalType": "uint256", "name": "amountToken", "type": "uint256"},
            {"internalType": "uint256", "name": "amountETH", "type": "uint256"},
            {"internalType": "uint256", "name": "liquidity", "type": "uint256"},
        ],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "factory",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "WETH",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# ── Uniswap V2 / PancakeSwap V2 Factory ABI (getPair) ─────────────────────
FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
        ],
        "name": "getPair",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]


# ── Helpers ─────────────────────────────────────────────────────────────────


def _token_units(amount: int | float | str | Decimal, decimals: int) -> int:
    """Convert a human-readable token amount to the smallest unit."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("amount must be a valid number.") from error

    if not value.is_finite() or value <= 0:
        raise ValueError("amount must be greater than zero.")

    units = value * (10**decimals)
    if units != units.to_integral_value():
        raise ValueError(f"amount cannot have more than {decimals} decimal places.")

    return int(units)


def _eth_to_wei(amount: int | float | str | Decimal) -> int:
    """Convert a human-readable ETH/BNB/MATIC amount to wei."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("amount_eth must be a valid number.") from error

    if not value.is_finite() or value <= 0:
        raise ValueError("amount_eth must be greater than zero.")

    return Web3.to_wei(value, "ether")


# ── Main function ───────────────────────────────────────────────────────────


def add_liquidity(
    network_rpc: str,
    contract_address: str,
    owner_private_key: str,
    amount_usdt: int | float | str | Decimal,
    amount_eth: int | float | str | Decimal,
    router_address: str,
    weth_address: str,
) -> str:
    """Add USDT–native token liquidity to a Uniswap V2 / PancakeSwap pool.

    This performs two sequential transactions:
        1. Approve the DEX Router to spend the specified amount of USDT.
        2. Call ``addLiquidityETH`` on the Router, sending the native token
           (ETH / BNB / MATIC) as ``msg.value``.

    Parameters
    ----------
    network_rpc : str
        Blockchain RPC endpoint URL.
    contract_address : str
        Deployed FlashUSDT contract address.
    owner_private_key : str
        Private key of the wallet that holds USDT and native tokens for gas.
    amount_usdt : int | float | str | Decimal
        Amount of USDT to deposit (human-readable, e.g. ``1000.0``).
    amount_eth : int | float | str | Decimal
        Amount of native token (ETH / BNB / MATIC) to deposit
        (human-readable, e.g. ``0.5``).
    router_address : str
        DEX Router contract address (Uniswap V2 or PancakeSwap V2).
    weth_address : str
        Wrapped native token address (WETH / WBNB / WMATIC).

    Returns
    -------
    str
        The on-chain pool (pair) address for the USDT–native token pair.
    """
    # ── Connect ─────────────────────────────────────────────────────────
    web3 = Web3(Web3.HTTPProvider(network_rpc, request_kwargs={"timeout": 30}))
    if not web3.is_connected():
        raise ConnectionError(f"Could not connect to RPC endpoint: {network_rpc}")

    account = web3.eth.account.from_key(owner_private_key)
    sender = account.address
    checksum_token = Web3.to_checksum_address(contract_address)
    checksum_router = Web3.to_checksum_address(router_address)
    checksum_weth = Web3.to_checksum_address(weth_address)

    # ── Contract instances ──────────────────────────────────────────────
    token_contract = web3.eth.contract(address=checksum_token, abi=ERC20_ABI)
    router_contract = web3.eth.contract(address=checksum_router, abi=ROUTER_ABI)

    # ── Convert amounts ─────────────────────────────────────────────────
    token_decimals = token_contract.functions.decimals().call()
    usdt_units = _token_units(amount_usdt, decimals=token_decimals)
    native_wei = _eth_to_wei(amount_eth)

    chain_id = web3.eth.chain_id
    gas_price = web3.eth.gas_price

    # ═════════════════════════════════════════════════════════════════════
    # STEP 1 — Approve the Router to spend USDT
    # ═════════════════════════════════════════════════════════════════════
    print("Approving Router to spend USDT tokens…")
    nonce = web3.eth.get_transaction_count(sender, "pending")

    approve_tx = token_contract.functions.approve(
        checksum_router,
        usdt_units,
    ).build_transaction({
        "from": sender,
        "nonce": nonce,
        "chainId": chain_id,
        "gasPrice": gas_price,
    })

    # Estimate gas for approve; fall back to a safe default if it fails
    try:
        estimated_approve = token_contract.functions.approve(
            checksum_router, usdt_units,
        ).estimate_gas({"from": sender})
        approve_tx["gas"] = (estimated_approve * 120 + 99) // 100
    except (ContractLogicError, ValueError):
        approve_tx["gas"] = 100_000

    signed_approve = account.sign_transaction(approve_tx)
    raw_approve = getattr(signed_approve, "raw_transaction", None)
    if raw_approve is None:
        raw_approve = signed_approve.rawTransaction

    approve_hash = web3.eth.send_raw_transaction(raw_approve)
    approve_receipt = web3.eth.wait_for_transaction_receipt(
        approve_hash, timeout=120, poll_latency=2,
    )

    if approve_receipt.status != 1:
        raise RuntimeError(f"Approve transaction reverted: {approve_hash.hex()}")

    print(f"✅ Approve confirmed. Tx: {approve_hash.hex()}")

    # ═════════════════════════════════════════════════════════════════════
    # STEP 2 — Add liquidity via addLiquidityETH
    # ═════════════════════════════════════════════════════════════════════
    print("Adding liquidity…")
    # 20-minute deadline from the latest block
    deadline = web3.eth.get_block("latest")["timestamp"] + 60 * 20

    # 1% slippage tolerance
    min_usdt = int(usdt_units * 99 / 100)
    min_native = int(native_wei * 99 / 100)

    nonce = web3.eth.get_transaction_count(sender, "pending")

    add_liquidity_tx = router_contract.functions.addLiquidityETH(
        checksum_token,
        usdt_units,
        min_usdt,
        min_native,
        sender,
        deadline,
    ).build_transaction({
        "from": sender,
        "nonce": nonce,
        "chainId": chain_id,
        "gasPrice": gas_price,
        "value": native_wei,
    })

    # Estimate gas for addLiquidityETH; fall back to a safe default
    try:
        estimated_gas = router_contract.functions.addLiquidityETH(
            checksum_token, usdt_units, min_usdt, min_native, sender, deadline,
        ).estimate_gas({
            "from": sender,
            "value": native_wei,
        })
        add_liquidity_tx["gas"] = (estimated_gas * 120 + 99) // 100
    except (ContractLogicError, ValueError):
        add_liquidity_tx["gas"] = 300_000

    signed_liquidity = account.sign_transaction(add_liquidity_tx)
    raw_liquidity = getattr(signed_liquidity, "raw_transaction", None)
    if raw_liquidity is None:
        raw_liquidity = signed_liquidity.rawTransaction

    liquidity_hash = web3.eth.send_raw_transaction(raw_liquidity)
    liquidity_receipt = web3.eth.wait_for_transaction_receipt(
        liquidity_hash, timeout=300, poll_latency=2,
    )

    if liquidity_receipt.status != 1:
        raise RuntimeError(
            f"addLiquidityETH transaction reverted: {liquidity_hash.hex()}"
        )

    print(f"✅ addLiquidityETH confirmed. Tx: {liquidity_hash.hex()}")

    # ═════════════════════════════════════════════════════════════════════
    # STEP 3 — Derive and return the pool (pair) address
    # ═════════════════════════════════════════════════════════════════════
    factory_address = router_contract.functions.factory().call()
    checksum_factory = Web3.to_checksum_address(factory_address)
    factory_contract = web3.eth.contract(address=checksum_factory, abi=FACTORY_ABI)
    pool_address = factory_contract.functions.getPair(
        checksum_token, checksum_weth,
    ).call()

    print(f"🔥 Liquidity Added! Pool Address: {pool_address}")
    return pool_address


# ── Example / standalone usage ──────────────────────────────────────────────

if __name__ == "__main__":
    # ── Ethereum example ────────────────────────────────────────────────
    add_liquidity(
        network_rpc="https://cloudflare-eth.com",
        contract_address="0xYourTokenAddressHere",
        owner_private_key="0xYourPrivateKeyHere",
        amount_usdt=1_000,
        amount_eth=0.5,
        router_address=UNISWAP_V2_ROUTER_ETH,
        weth_address=WETH_ETH,
    )
