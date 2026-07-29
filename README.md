# ⚡ Flash USDT Manager

> **Multi-chain desktop application for deploying, minting, sending, and managing custom USDT tokens (ERC-20 / BEP-20 / TRC-20).**

![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python)
![Solidity](https://img.shields.io/badge/Solidity-0.8.17-363636?logo=solidity)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#️-architecture)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage Guide](#-usage-guide)
- [Smart Contract](#-smart-contract)
- [Module Reference](#-module-reference)
- [Trust Wallet Integration](#-trust-wallet-integration)
- [Security Notes](#-security-notes)
- [Troubleshooting](#-troubleshooting)
- [License](#-license)

---

## 📌 Overview

Flash USDT Manager is a **PyQt6-based desktop GUI** that provides a unified interface for operating a custom USDT token across **four blockchains** simultaneously:

| Network  | Type     | Native Token | Chain ID  |
|----------|----------|--------------|-----------|
| Ethereum | EVM      | ETH          | 1         |
| BSC      | EVM      | BNB          | 56        |
| Polygon  | EVM      | MATIC        | 137       |
| TRON     | TVM      | TRX          | 728126428 |

The token contract (`FlashUSDT.sol`) mirrors the real **Tether USD** interface — 6 decimals, name `"Tether USD"`, symbol `"USDT"` — with an owner-controlled `mint()` function, making it suitable for **test environments, liquidity provisioning, or private token operations**.

---

## ✨ Key Features

### 💻 Desktop Application
- **Dark-themed GUI** built with PyQt6
- **7-page navigation**: Dashboard, Deploy, Mint, Send, Send & Verify, Wallets, Settings
- **Async blockchain operations** — UI stays responsive during transactions (QThread workers)
- **Live QR code generation** for recipient addresses and token deep links

### 🔗 Cross-Chain Operations
- **Deploy** the same contract on Ethereum, BSC, Polygon, **or** TRON
- **Mint** tokens to any wallet on any supported network
- **Send** tokens between wallets
- **Configurable RPC endpoints** per network

### 📜 Token Features
- **Owner-only mint & burn** — unlimited supply controlled by deployer
- **6 decimals** (matches real USDT)
- **Logo URI** for wallet / explorer display (`logoURI()`)
- **ERC-20 / BEP-20 / TRC-20** compatible

### 🧰 Additional Tools
- **Wallet generator** — BIP-39 mnemonic-based Ethereum wallets
- **MetaMask deep links** — one-click token addition to MetaMask
- **QR code generator** — for addresses and token-add links
- **Liquidity manager** — add USDT-native token liquidity on Uniswap V2, Quickswap, or PancakeSwap

---

## 🏗️ Architecture

```
TetherUSD/
├── main_app.py                  # PyQt6 desktop GUI — entry point
│
├── config/
│   └── networks.json            # RPC endpoints & chain config per network
│
├── contracts/
│   ├── FlashUSDT.sol            # ERC-20 / BEP-20 / TRC-20 token (Solc 0.8.17)
│   └── newcontract.sol          # Modernized Tether clone (Solc 0.8.20, OpenZeppelin)
│
├── src/
│   ├── deployer.py              # EVM contract compilation & deployment
│   ├── tron_manager.py          # TRON-specific deployment & minting
│   ├── minter.py                # EVM token minting
│   ├── sender.py                # EVM token transfers
│   ├── wallet_manager.py        # BIP-39 wallet generation & JSON export
│   ├── logo_helper.py           # MetaMask deep links + QR codes
│   └── liquidity_manager.py     # Uniswap V2 / PancakeSwap liquidity addition
│
├── node_modules/
│   └── @openzeppelin/contracts/ # OpenZeppelin Solidity dependencies
│
├── package.json                 # npm dependency: @openzeppelin/contracts
├── .gitignore
└── README.md
```

### Data Flow

```
┌──────────┐     ┌──────────────┐     ┌─────────────────┐
│  PyQt6   │────▶│  TaskThread  │────▶│  web3.py /      │
│   GUI    │     │  (QThread)   │     │  tronpy         │
└──────────┘     └──────────────┘     └────────┬────────┘
                                               │
                                               ▼
                                        ┌─────────────────┐
                                        │  Blockchain     │
                                        │  (ETH / BSC /   │
                                        │   POLY / TRON)  │
                                        └─────────────────┘
```

- The GUI captures user inputs and spawns a **background worker** (`TaskThread`)
- The worker executes the blockchain operation (deploy / mint / send)
- Results are emitted back to the UI via signals (`succeeded` / `failed`)
- Network config is persisted in `config/networks.json`

---

## 📦 Prerequisites

### Required
| Tool        | Version    | Purpose                        |
|-------------|------------|--------------------------------|
| Python      | ≥ 3.10     | Runtime                        |
| Node.js     | ≥ 16       | npm package installation       |
| npm         | ≥ 8        | Installing OpenZeppelin        |

### Optional
| Tool        | Purpose                        |
|-------------|--------------------------------|
| Git         | Version control                |
| MetaMask    | Browser wallet for EVM chains  |
| Trust Wallet| Mobile wallet for testing      |
| TronLink    | Browser wallet for TRON        |

---

## 🔧 Installation

### 1️⃣ Clone the repository

```bash
git clone https://github.com/your-username/tether-usd-manager.git
cd tether-usd-manager
```

### 2️⃣ Install Python dependencies

```bash
pip install PyQt6 web3 tronpy py-solc-x qrcode bip39
```

Or using the requirements file:

```bash
pip install -r requirements.txt
```

### 3️⃣ Install Solidity dependencies (OpenZeppelin)

```bash
npm install
```

This installs `@openzeppelin/contracts@4.9.6` — required for compiling `FlashUSDT.sol`.

### 4️⃣ Verify Solc installation

The app uses `py-solc-x` to manage Solidity compilers. It will auto-download Solc **0.8.17** on first deployment. You can pre-install it:

```bash
python -c "from solcx import install_solc; install_solc('0.8.17')"
```

---

## ⚙️ Configuration

### Network Settings

Edit `config/networks.json` or use the **Settings** page in the GUI:

```json
{
  "ethereum": {
    "chain_id": 1,
    "rpc_url": "https://cloudflare-eth.com",
    "native_token": "ETH",
    "usdt_contract_address": "0x..."
  },
  "binance_smart_chain": {
    "chain_id": 56,
    "rpc_url": "https://bsc-dataseed.binance.org",
    "native_token": "BNB",
    "usdt_contract_address": "0x..."
  },
  "polygon": {
    "chain_id": 137,
    "rpc_url": "https://polygon-rpc.com",
    "native_token": "MATIC",
    "usdt_contract_address": "0x..."
  },
  "tron": {
    "chain_id": 728126428,
    "rpc_url": "https://api.trongrid.io",
    "native_token": "TRX",
    "usdt_contract_address": "T..."
  }
}
```

> **Note:** Default RPCs are public endpoints. For production, use your own RPC (Infura, Alchemy, QuickNode, etc.).

---

## 🚀 Usage Guide

### Launch the Application

```bash
python main_app.py
```

### 🖥️ Dashboard

Shows a summary view with metrics and a quick-start guide. Use the **sidebar** to navigate between modules.

---

### 1️⃣ Deploy a Token

1. Go to **Deploy** tab
2. Select **Network** (ETH / BSC / POLY / TRON)
3. Enter or confirm the **RPC URL**
4. Paste the **Owner Private Key** (this wallet becomes the contract owner)
5. Click **Deploy Contract**
6. Wait 30–120 seconds for confirmation
7. Copy the returned **Contract Address**

---

### 2️⃣ Mint Tokens

1. Go to **Mint** tab
2. Select **Network**
3. Enter **Contract Address** (from deployment)
4. Enter **Owner Private Key**
5. Enter **Recipient Address**
6. Enter **Amount** (in human-readable USDT, e.g. `10000`)
7. Click **Mint Tokens**

---

### 3️⃣ Send Tokens

1. Go to **Send** tab
2. Select **Network** (EVM chains only)
3. Enter **RPC URL**, **Sender Private Key**, **Contract Address**
4. Enter **Recipient Address** (QR code updates live)
5. Enter **Amount**
6. Click **Send**

---

### 4️⃣ Generate Deposit Link & QR

1. Go to **Send & Verify** tab
2. Select **Network** (ETH / BSC / POLY)
3. Enter **Contract Address**
4. Optionally enter **Recipient Address**
5. Click **Generate Deposit Link & QR**
6. A MetaMask deep link and QR code are generated — scan to add the token to any wallet

---

### 5️⃣ Manage Wallets

1. Go to **Wallets** tab
2. Click **Generate New Wallet** — a BIP-39 wallet is created (address, private key, mnemonic)
3. Select a row to see its **QR code**
4. Click **Export Selected Wallet** to save as `wallet_N.json`

---

### 6️⃣ Add Liquidity (Programmatic)

```python
from src.liquidity_manager import add_liquidity, PANCAKESWAP_V2_ROUTER_BSC, WBNB_BSC

add_liquidity(
    network_rpc="https://bsc-dataseed.binance.org",
    contract_address="0xYourDeployedContract",
    owner_private_key="0xYourPrivateKey",
    amount_usdt=5000,
    amount_eth=0.1,              # BNB on BSC
    router_address=PANCAKESWAP_V2_ROUTER_BSC,
    weth_address=WBNB_BSC,
)
```

Supported DEXes:
| Network | DEX | Factory | Router |
|---------|-----|---------|--------|
| Ethereum | Uniswap V2 | `0x5C69...aA6f` | `0x7a25...488D` |
| Polygon | Quickswap | `0x5757...3Ab32` | `0xa5E0...78ff` |
| BSC | PancakeSwap V2 | `0xcA14...0c73` | `0x10ED...024E` |

---

## 📄 Smart Contract

### FlashUSDT.sol (Solc 0.8.17)

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract FlashUSDT is ERC20, Ownable {
    constructor() ERC20("Tether USD", "USDT") {}

    function decimals() public pure override returns (uint8) { return 6; }

    function logoURI() public view returns (string memory) {
        return "https://s2.coinmarketcap.com/static/img/coins/64x64/825.png";
    }

    function mint(address account, uint256 amount) external onlyOwner {
        _mint(account, amount);
    }

    function burn(uint256 amount) external onlyOwner {
        _burn(_msgSender(), amount);
    }
}
```

**Key points:**
- Standard **OpenZeppelin ERC-20** with `Ownable`
- **6 decimals** — matches real USDT
- **Owner-only mint** — unlimited supply
- **No tax, no blacklist, no pause** — minimal and gas-efficient
- **Compiles identically on EVM and TRON** (TVM)

---

## 📚 Module Reference

| Module | File | Purpose |
|--------|------|---------|
| `deployer` | `src/deployer.py` | Compiles & deploys to EVM chains |
| `tron_manager` | `src/tron_manager.py` | Compiles & deploys to TRON |
| `minter` | `src/minter.py` | Mints tokens on EVM chains |
| `sender` | `src/sender.py` | Transfers tokens on EVM chains |
| `wallet_manager` | `src/wallet_manager.py` | Generates BIP-39 wallets |
| `logo_helper` | `src/logo_helper.py` | MetaMask deep links + QR |
| `liquidity_manager` | `src/liquidity_manager.py` | DEX liquidity provision |

### Key Functions

```python
# Deploy
deploy_token(network_name, private_key, rpc_url) -> str  # returns contract address
deploy_tron_token(tron_client, private_key_hex) -> str

# Mint
mint_tokens(network_rpc, contract_address, owner_key, recipient, amount) -> str
mint_tron_tokens(tron_client, contract_address, owner_key, recipient, amount) -> str

# Send
send_tokens(network_rpc, contract_address, sender_key, recipient, amount) -> str

# Liquidity
add_liquidity(network_rpc, contract_address, owner_key, amount_usdt, amount_eth, router, weth) -> str

# Wallet
generate_wallet() -> dict  # {private_key, address, mnemonic}
save_wallet(wallet_data, filename) -> None
```

---

## 📱 Trust Wallet Integration

### Adding a Custom Token

1. Open **Trust Wallet** → tap the filter icon → **Add Custom Token**
2. Select the correct **Network** (Ethereum / Smart Chain / Polygon)
3. Paste the **Contract Address**
4. Name / Symbol / Decimals auto-populate to:
   - **Name**: `Tether USD`
   - **Symbol**: `USDT`
   - **Decimals**: `6`
5. Tap **Import**

### Getting Logo to Display

Trust Wallet does not read `logoURI()` from the contract. To get the logo to appear:

1. Submit a PR to [trustwallet/assets](https://github.com/trustwallet/assets) GitHub repo
2. Include your contract address, logo PNG (64×64), and `info.json`
3. After approval (~1–2 weeks), the logo will appear for all users

Until then, the token works perfectly — balance, transfers, and trading all function; only the logo will show a generic placeholder.

---

## ⚠️ Security Notes

> **⚠️ WARNING: This software creates and manages tokens with unlimited mint capability.**

1. **Private Keys** — These are entered directly into the GUI. The app does not send them anywhere, but any process with access to your machine could read them. Use a dedicated test wallet.
2. **Minting Power** — The contract owner can mint unlimited tokens. This is by design for testing/liquidity, but it means **no real value should be associated with these tokens**.
3. **No Audit** — This project has not been audited. Use only on test networks or with funds you can afford to lose.
4. **Network Fees** — All blockchain operations require native tokens (ETH/BNB/MATIC/TRX) for gas. Ensure the owner wallet is funded.
5. **Exported Wallets** — `wallet_*.json` files contain plaintext private keys. Keep them secure and never commit them to Git (excluded via `.gitignore`).

---

## 🔍 Troubleshooting

### GUI won't start
```bash
# Check Python and PyQt6 installation
python -c "from PyQt6.QtWidgets import QApplication; print('OK')"
```

### Solc compilation fails
```bash
# Manually install the compiler
python -c "from solcx import install_solc; install_solc('0.8.17')"
```

### OpenZeppelin not found
```bash
# Ensure npm dependencies are installed
cd TetherUSD
npm install
```

### "Could not connect to RPC endpoint"
- Verify the RPC URL is correct in **Settings**
- For testnets, ensure you have test tokens from a faucet
- Some public RPCs rate-limit — try using a private RPC

### "Nonce too low"
- Pending transactions are stuck. Use a wallet tool to clear them, or wait.
- The app uses `"pending"` nonce, but if a previous transaction was dropped, the nonce may be out of sync.

### TRON deployment fails
- Ensure the owner wallet has enough TRX (>10 TRX recommended for deployment)
- Use `api.shasta.trongrid.io` for TRON testnet
- TRON mainnet requires frozen energy/bandwidth for contract deployment

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

- [OpenZeppelin](https://openzeppelin.com/contracts/) — Secure smart contract libraries
- [web3.py](https://web3py.readthedocs.io/) — Ethereum interaction library
- [tronpy](https://github.com/andelf/tronpy) — TRON interaction library
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — Python GUI framework
- [py-solc-x](https://github.com/iamdefinitelyahuman/py-solc-x) — Solidity compiler management

---

<p align="center">
  <sub>Built for educational and testing purposes. Not affiliated with Tether Limited or Bitfinex.</sub>
</p>
