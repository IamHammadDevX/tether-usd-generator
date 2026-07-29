"""Utility for generating MetaMask token-add links and QR codes."""

from io import BytesIO
from pathlib import Path
from typing import Optional

import qrcode

# ── Token metadata (mirrors FlashUSDT for test/liquidity purposes) ──────────
TOKEN_NAME = "Tether USD"
TOKEN_SYMBOL = "USDT"
TOKEN_DECIMALS = 6
TOKEN_LOGO_URI = (
    "https://s2.coinmarketcap.com/static/img/coins/64x64/825.png"
)

# ── Network → chain ID mapping ──────────────────────────────────────────────
NETWORK_CHAIN_IDS: dict[str, int] = {
    "ETH": 1,
    "BSC": 56,
    "POLY": 137,
    "POLYGON": 137,
}


def generate_token_add_link(
    contract_address: str,
    network_name: str,
) -> str:
    """Build a MetaMask / Token.im deep link to add a custom ERC-20 token.

    Parameters
    ----------
    contract_address : str
        The deployed token contract address (checksummed or raw).
    network_name : str
        One of ``"ETH"``, ``"BSC"``, ``"POLY"``, or ``"POLYGON"``.

    Returns
    -------
    str
        A fully constructed deep link.

    Raises
    ------
    ValueError
        If *network_name* is not recognised.
    """
    key = network_name.strip().upper()
    chain_id = NETWORK_CHAIN_IDS.get(key)
    if chain_id is None:
        raise ValueError(
            f"Unsupported network '{network_name}'. "
            f"Supported: {', '.join(sorted(NETWORK_CHAIN_IDS))}."
        )

    # Standard Token.im / MetaMask add-token deep-link format.
    link = (
        f"https://token.im/token/add"
        f"?network={chain_id}"
        f"&symbol={TOKEN_SYMBOL}"
        f"&name={TOKEN_NAME}"
        f"&decimals={TOKEN_DECIMALS}"
        f"&address={contract_address}"
        f"&logoUri={TOKEN_LOGO_URI}"
    )
    return link


def save_qr_code(
    link: str,
    output_path: Optional[str | Path] = None,
) -> Path:
    """Generate a QR-code PNG image from *link* and save it to disk.

    Parameters
    ----------
    link : str
        The URL to encode (typically the output of
        :func:`generate_token_add_link`).
    output_path : str or Path, optional
        Where to write the PNG file.  Defaults to
        ``./token_add_qr.png`` in the current working directory.

    Returns
    -------
    Path
        The absolute path of the saved PNG file.
    """
    if output_path is None:
        output_path = Path.cwd() / "token_add_qr.png"
    else:
        output_path = Path(output_path)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(link)
    qr.make(fit=True)

    image = qr.make_image(fill_color="#111111", back_color="#FFFFFF")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")
    return output_path.resolve()


# ── Public aliases (consumer-friendly names) ────────────────────────────────
generate_metamask_deep_link = generate_token_add_link
generate_qr_code = save_qr_code