import json
import sys
import traceback
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import qrcode
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from tronpy import Tron
from tronpy.providers import HTTPProvider

from src.deployer import deploy_token
from src.logo_helper import generate_metamask_deep_link, generate_qr_code
from src.minter import mint_tokens
from src.sender import send_tokens
from src.tron_manager import deploy_tron_token, mint_tron_tokens
from src.wallet_manager import generate_wallet, save_wallet


APP_ROOT = Path(__file__).resolve().parent
NETWORKS_PATH = APP_ROOT / "config" / "networks.json"
NETWORK_KEYS = {
    "ETH": "ethereum",
    "BSC": "binance_smart_chain",
    "POLY": "polygon",
    "TRON": "tron",
}
DEFAULT_NETWORKS = {
    "ethereum": {
        "chain_id": 1,
        "rpc_url": "https://cloudflare-eth.com",
        "native_token": "ETH",
        "usdt_contract_address": "0x...",
    },
    "binance_smart_chain": {
        "chain_id": 56,
        "rpc_url": "https://bsc-dataseed.binance.org",
        "native_token": "BNB",
        "usdt_contract_address": "0x...",
    },
    "polygon": {
        "chain_id": 137,
        "rpc_url": "https://polygon-rpc.com",
        "native_token": "MATIC",
        "usdt_contract_address": "0x...",
    },
    "tron": {
        "chain_id": 728126428,
        "rpc_url": "https://api.trongrid.io",
        "native_token": "TRX",
        "usdt_contract_address": "T...",
    },
}


class TaskThread(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        task: Callable[..., Any],
        *args: Any,
        parent: QWidget | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent)
        self.task = task
        self.args = args
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            self.succeeded.emit(self.task(*self.args, **self.kwargs))
        except Exception as error:
            message = str(error).strip() or error.__class__.__name__
            self.failed.emit(message)
            traceback.print_exc()


class FlashUSDTApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.networks = self._load_networks()
        self.workers: set[TaskThread] = set()
        self.wallets: list[dict[str, str]] = []
        self.settings_rpc_inputs: dict[str, QLineEdit] = {}

        self.setWindowTitle("Flash USDT Manager")
        self.setMinimumSize(1180, 760)
        self.resize(1360, 860)
        self._build_ui()
        self._apply_theme()

    def _load_networks(self) -> dict:
        try:
            with NETWORKS_PATH.open("r", encoding="utf-8") as config_file:
                loaded = json.load(config_file)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            loaded = {}

        networks = json.loads(json.dumps(DEFAULT_NETWORKS))
        for key, value in loaded.items():
            if key in networks and isinstance(value, dict):
                networks[key].update(value)
        return networks

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = self._build_sidebar()
        root_layout.addWidget(sidebar)

        content_shell = QWidget()
        content_layout = QVBoxLayout(content_shell)
        content_layout.setContentsMargins(34, 24, 34, 30)
        content_layout.setSpacing(18)

        header = QHBoxLayout()
        title_column = QVBoxLayout()
        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("pageTitle")
        subtitle = QLabel("Multi-chain Flash USDT control center")
        subtitle.setObjectName("muted")
        title_column.addWidget(self.page_title)
        title_column.addWidget(subtitle)
        header.addLayout(title_column)
        header.addStretch()

        status = QLabel("●  READY")
        status.setObjectName("statusBadge")
        header.addWidget(status, alignment=Qt.AlignmentFlag.AlignTop)
        content_layout.addLayout(header)

        self.stack = QStackedWidget()
        self.pages = [
            self._dashboard_page(),
            self._deploy_page(),
            self._mint_page(),
            self._send_page(),
            self._send_verify_page(),
            self._wallets_page(),
            self._settings_page(),
        ]
        for page in self.pages:
            self.stack.addWidget(page)
        content_layout.addWidget(self.stack)

        root_layout.addWidget(content_shell, 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 26, 20, 24)
        layout.setSpacing(8)

        logo_row = QHBoxLayout()
        logo = QLabel("₮")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand = QLabel("FlashUSDT")
        brand.setObjectName("brand")
        logo_row.addWidget(logo)
        logo_row.addWidget(brand)
        logo_row.addStretch()
        layout.addLayout(logo_row)
        layout.addSpacing(28)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        page_names = ["Dashboard", "Deploy", "Mint", "Send", "Send & Verify", "Wallets", "Settings"]
        for index, name in enumerate(page_names):
            button = QPushButton(name)
            button.setCheckable(True)
            button.setObjectName("navButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, page=index, title=name: self._navigate(
                    page,
                    title,
                )
            )
            self.nav_group.addButton(button, index)
            layout.addWidget(button)
            if index == 0:
                button.setChecked(True)

        layout.addStretch()
        version = QLabel("Desktop Manager\nv1.0")
        version.setObjectName("muted")
        layout.addWidget(version)
        return sidebar

    def _navigate(self, page_index: int, title: str) -> None:
        self.stack.setCurrentIndex(page_index)
        self.page_title.setText(title)

    def _dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(22)

        welcome = self._card()
        welcome_layout = QVBoxLayout(welcome)
        welcome_layout.setContentsMargins(28, 26, 28, 26)
        heading = QLabel("Flash USDT Operations")
        heading.setObjectName("sectionTitle")
        description = QLabel(
            "Deploy, mint, send, and manage wallets across Ethereum, "
            "BNB Smart Chain, Polygon, and TRON."
        )
        description.setObjectName("muted")
        description.setWordWrap(True)
        welcome_layout.addWidget(heading)
        welcome_layout.addWidget(description)
        layout.addWidget(welcome)

        cards = QGridLayout()
        cards.setHorizontalSpacing(16)
        cards.setVerticalSpacing(16)
        items = [
            ("4", "Supported Networks"),
            ("6", "Token Decimals"),
            ("0", "Initial Supply"),
            ("USDT", "Token Symbol"),
        ]
        for index, (value, label) in enumerate(items):
            cards.addWidget(self._metric_card(value, label), 0, index)
        layout.addLayout(cards)

        quick = self._card()
        quick_layout = QVBoxLayout(quick)
        quick_layout.setContentsMargins(28, 24, 28, 24)
        quick_layout.addWidget(self._section_label("Quick start"))
        instructions = QLabel(
            "1. Configure RPC endpoints in Settings.\n"
            "2. Deploy FlashUSDT with the owner wallet.\n"
            "3. Mint tokens to a recipient.\n"
            "4. Transfer tokens using Send."
        )
        instructions.setObjectName("bodyText")
        instructions.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        quick_layout.addWidget(instructions)
        layout.addWidget(quick)
        layout.addStretch()
        return page

    def _deploy_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        card = self._card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(18)
        card_layout.addWidget(self._section_label("Deploy FlashUSDT"))

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        self.deploy_network = self._network_combo(include_tron=True)
        self.deploy_rpc = QLineEdit()
        self.deploy_rpc.setPlaceholderText("Network RPC URL")
        self.deploy_key = self._secret_input("Owner private key")
        form.addRow("Network", self.deploy_network)
        form.addRow("RPC URL", self.deploy_rpc)
        form.addRow("Owner Private Key", self.deploy_key)
        card_layout.addLayout(form)

        self.deploy_network.currentTextChanged.connect(
            lambda name: self._set_rpc_for_combo(name, self.deploy_rpc)
        )
        self._set_rpc_for_combo(self.deploy_network.currentText(), self.deploy_rpc)

        self.deploy_button = QPushButton("Deploy Contract")
        self.deploy_button.setObjectName("primaryButton")
        self.deploy_button.clicked.connect(self._start_deploy)
        card_layout.addWidget(self.deploy_button)

        self.deploy_result = QTextEdit()
        self.deploy_result.setReadOnly(True)
        self.deploy_result.setPlaceholderText(
            "Contract address and transaction result will appear here."
        )
        self.deploy_result.setMinimumHeight(180)
        card_layout.addWidget(self.deploy_result)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _mint_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        card = self._card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(18)
        card_layout.addWidget(self._section_label("Mint Tokens"))

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        self.mint_network = self._network_combo(include_tron=True)
        self.mint_rpc = QLineEdit()
        self.mint_contract = QLineEdit()
        self.mint_contract.setPlaceholderText("Deployed contract address")
        self.mint_key = self._secret_input("Owner private key")
        self.mint_recipient = QLineEdit()
        self.mint_recipient.setPlaceholderText("Recipient address")
        self.mint_amount = QLineEdit()
        self.mint_amount.setPlaceholderText("Amount in USDT")
        form.addRow("Network", self.mint_network)
        form.addRow("RPC URL", self.mint_rpc)
        form.addRow("Contract Address", self.mint_contract)
        form.addRow("Owner Private Key", self.mint_key)
        form.addRow("Recipient Address", self.mint_recipient)
        form.addRow("Amount", self.mint_amount)
        card_layout.addLayout(form)

        self.mint_network.currentTextChanged.connect(
            lambda name: self._set_rpc_for_combo(name, self.mint_rpc)
        )
        self._set_rpc_for_combo(self.mint_network.currentText(), self.mint_rpc)

        self.mint_button = QPushButton("Mint Tokens")
        self.mint_button.setObjectName("primaryButton")
        self.mint_button.clicked.connect(self._start_mint)
        card_layout.addWidget(self.mint_button)
        self.mint_result = QTextEdit()
        self.mint_result.setReadOnly(True)
        self.mint_result.setMinimumHeight(130)
        self.mint_result.setPlaceholderText("Mint transaction result")
        card_layout.addWidget(self.mint_result)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _send_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        form_card = self._card()
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(28, 26, 28, 26)
        form_layout.setSpacing(18)
        form_layout.addWidget(self._section_label("Send FlashUSDT"))

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        self.send_network = self._network_combo(include_tron=False)
        self.send_rpc = QLineEdit()
        self.send_key = self._secret_input("Sender private key")
        self.send_contract = QLineEdit()
        self.send_contract.setPlaceholderText("Contract address")
        self.send_recipient = QLineEdit()
        self.send_recipient.setPlaceholderText("Recipient address")
        self.send_amount = QLineEdit()
        self.send_amount.setPlaceholderText("Amount in USDT")
        form.addRow("Network", self.send_network)
        form.addRow("RPC URL", self.send_rpc)
        form.addRow("Sender Private Key", self.send_key)
        form.addRow("Contract Address", self.send_contract)
        form.addRow("Recipient Address", self.send_recipient)
        form.addRow("Amount", self.send_amount)
        form_layout.addLayout(form)

        self.send_network.currentTextChanged.connect(
            lambda name: self._set_rpc_for_combo(name, self.send_rpc)
        )
        self._set_rpc_for_combo(self.send_network.currentText(), self.send_rpc)
        self.send_recipient.textChanged.connect(self._update_send_qr)

        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("primaryButton")
        self.send_button.clicked.connect(self._start_send)
        form_layout.addWidget(self.send_button)
        self.send_result = QTextEdit()
        self.send_result.setReadOnly(True)
        self.send_result.setMinimumHeight(120)
        self.send_result.setPlaceholderText("Transfer transaction result")
        form_layout.addWidget(self.send_result)
        layout.addWidget(form_card, 3)

        qr_card = self._card()
        qr_layout = QVBoxLayout(qr_card)
        qr_layout.setContentsMargins(24, 26, 24, 26)
        qr_layout.addWidget(self._section_label("Recipient QR"))
        self.send_qr = self._qr_label("Enter recipient address")
        qr_layout.addWidget(self.send_qr, alignment=Qt.AlignmentFlag.AlignCenter)
        qr_layout.addStretch()
        layout.addWidget(qr_card, 2)
        return page

    def _send_verify_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        form_card = self._card()
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(28, 26, 28, 26)
        form_layout.setSpacing(18)
        form_layout.addWidget(self._section_label("Send & Verify — Deposit Link"))

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)

        self.sv_network = QComboBox()
        self.sv_network.addItems(["ETH", "BSC", "POLY"])
        self.sv_contract = QLineEdit()
        self.sv_contract.setPlaceholderText("Deployed contract address")
        self.sv_recipient = QLineEdit()
        self.sv_recipient.setPlaceholderText("Recipient address (optional)")

        form.addRow("Network", self.sv_network)
        form.addRow("Contract Address", self.sv_contract)
        form.addRow("Recipient Address", self.sv_recipient)
        form_layout.addLayout(form)

        self.sv_generate_button = QPushButton("Generate Deposit Link & QR")
        self.sv_generate_button.setObjectName("primaryButton")
        self.sv_generate_button.clicked.connect(self._generate_deposit_link)
        form_layout.addWidget(self.sv_generate_button)

        self.sv_link_output = QTextEdit()
        self.sv_link_output.setReadOnly(True)
        self.sv_link_output.setPlaceholderText(
            "Generated MetaMask deep link will appear here."
        )
        self.sv_link_output.setMinimumHeight(60)
        self.sv_link_output.setMaximumHeight(80)
        form_layout.addWidget(self.sv_link_output)

        qr_card = self._card()
        qr_layout = QVBoxLayout(qr_card)
        qr_layout.setContentsMargins(24, 26, 24, 26)
        qr_layout.addWidget(self._section_label("QR Code"))
        self.sv_qr_label = self._qr_label("Generate a link to see the QR code")
        qr_layout.addWidget(self.sv_qr_label, alignment=Qt.AlignmentFlag.AlignCenter)
        qr_layout.addStretch()

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(form_card, 3)
        bottom_row.addWidget(qr_card, 2)
        layout.addLayout(bottom_row)
        layout.addStretch()
        return page

    def _generate_deposit_link(self) -> None:
        network = self.sv_network.currentText()
        contract = self.sv_contract.text().strip()

        if not contract:
            QMessageBox.warning(
                self, "Missing Information", "Contract address is required."
            )
            return

        try:
            link = generate_metamask_deep_link(contract, network)
        except ValueError as error:
            QMessageBox.critical(self, "Error", str(error))
            return

        self.sv_link_output.setPlainText(link)

        qr_path = generate_qr_code(link)
        pixmap = QPixmap()
        if pixmap.load(str(qr_path)):
            self.sv_qr_label.setText("")
            self.sv_qr_label.setPixmap(
                pixmap.scaled(
                    220,
                    220,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def _wallets_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        action_row = QHBoxLayout()
        generate_button = QPushButton("Generate New Wallet")
        generate_button.setObjectName("primaryButton")
        generate_button.clicked.connect(self._generate_wallet)
        action_row.addWidget(generate_button)
        action_row.addStretch()
        layout.addLayout(action_row)

        table_card = self._card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(20, 20, 20, 20)
        table_layout.setSpacing(14)
        self.wallet_table = QTableWidget(0, 3)
        self.wallet_table.setHorizontalHeaderLabels(
            ["Address", "Private Key", "Mnemonic"]
        )
        self.wallet_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.wallet_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.wallet_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.wallet_table.itemSelectionChanged.connect(self._wallet_selection_qr)
        table_layout.addWidget(self.wallet_table)

        qr_row = QHBoxLayout()
        self.wallet_qr = self._qr_label("Select wallet row for address QR")
        qr_row.addWidget(self.wallet_qr)
        qr_row.addStretch()
        export_button = QPushButton("Export Selected Wallet")
        export_button.setObjectName("secondaryButton")
        export_button.clicked.connect(self._export_selected_wallet)
        qr_row.addWidget(export_button, alignment=Qt.AlignmentFlag.AlignBottom)
        table_layout.addLayout(qr_row)
        layout.addWidget(table_card)
        return page

    def _settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        card = self._card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(18)
        card_layout.addWidget(self._section_label("Network RPC Settings"))

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        for display_name, config_key in NETWORK_KEYS.items():
            rpc_input = QLineEdit(self.networks[config_key].get("rpc_url", ""))
            rpc_input.setPlaceholderText(f"{display_name} RPC URL")
            self.settings_rpc_inputs[display_name] = rpc_input
            form.addRow(f"{display_name} RPC", rpc_input)
        card_layout.addLayout(form)

        save_button = QPushButton("Save Settings")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save_settings)
        card_layout.addWidget(save_button)
        self.settings_result = QLabel("")
        self.settings_result.setObjectName("successText")
        card_layout.addWidget(self.settings_result)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        return card

    def _metric_card(self, value: str, label: str) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        description = QLabel(label)
        description.setObjectName("muted")
        layout.addWidget(value_label)
        layout.addWidget(description)
        return card

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _network_combo(self, include_tron: bool) -> QComboBox:
        combo = QComboBox()
        combo.addItems(["ETH", "BSC", "POLY"])
        if include_tron:
            combo.addItem("TRON")
        return combo

    def _secret_input(self, placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText(placeholder)
        field.setEchoMode(QLineEdit.EchoMode.Password)
        return field

    def _qr_label(self, placeholder: str) -> QLabel:
        label = QLabel(placeholder)
        label.setObjectName("qrLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setFixedSize(240, 240)
        return label

    def _rpc_for(self, display_name: str) -> str:
        config_key = NETWORK_KEYS[display_name]
        return str(self.networks[config_key].get("rpc_url", ""))

    def _set_rpc_for_combo(self, display_name: str, field: QLineEdit) -> None:
        field.setText(self._rpc_for(display_name))

    def _required(self, fields: dict[str, QLineEdit]) -> dict[str, str] | None:
        values = {name: field.text().strip() for name, field in fields.items()}
        missing = [name for name, value in values.items() if not value]
        if missing:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Complete required fields: " + ", ".join(missing),
            )
            return None
        return values

    def _tron_client(self, rpc_url: str) -> Tron:
        if rpc_url:
            return Tron(HTTPProvider(endpoint_uri=rpc_url, timeout=30))
        return Tron()

    def _start_deploy(self) -> None:
        values = self._required(
            {
                "RPC URL": self.deploy_rpc,
                "Owner Private Key": self.deploy_key,
            }
        )
        if values is None:
            return

        network = self.deploy_network.currentText()
        self.deploy_result.setPlainText("Deploying contract…")
        if network == "TRON":
            task = lambda: deploy_tron_token(
                self._tron_client(values["RPC URL"]),
                values["Owner Private Key"],
            )
        else:
            task = lambda: deploy_token(
                network,
                values["Owner Private Key"],
                values["RPC URL"],
            )

        self._run_task(
            task,
            self.deploy_button,
            lambda address: self.deploy_result.setPlainText(
                f"Deployment successful.\nContract Address: {address}"
            ),
            lambda error: self.deploy_result.setPlainText(
                f"Deployment failed.\n{error}"
            ),
        )

    def _start_mint(self) -> None:
        values = self._required(
            {
                "RPC URL": self.mint_rpc,
                "Contract Address": self.mint_contract,
                "Owner Private Key": self.mint_key,
                "Recipient Address": self.mint_recipient,
                "Amount": self.mint_amount,
            }
        )
        if values is None:
            return

        network = self.mint_network.currentText()
        self.mint_result.setPlainText("Submitting mint transaction…")
        if network == "TRON":
            task = lambda: mint_tron_tokens(
                self._tron_client(values["RPC URL"]),
                values["Contract Address"],
                values["Owner Private Key"],
                values["Recipient Address"],
                values["Amount"],
            )
        else:
            task = lambda: mint_tokens(
                values["RPC URL"],
                values["Contract Address"],
                values["Owner Private Key"],
                values["Recipient Address"],
                values["Amount"],
            )

        self._run_task(
            task,
            self.mint_button,
            lambda tx_hash: self.mint_result.setPlainText(
                f"Mint successful.\nTransaction Hash: {tx_hash}"
            ),
            lambda error: self.mint_result.setPlainText(f"Mint failed.\n{error}"),
        )

    def _start_send(self) -> None:
        values = self._required(
            {
                "RPC URL": self.send_rpc,
                "Sender Private Key": self.send_key,
                "Contract Address": self.send_contract,
                "Recipient Address": self.send_recipient,
                "Amount": self.send_amount,
            }
        )
        if values is None:
            return

        self.send_result.setPlainText("Submitting transfer…")
        task = lambda: send_tokens(
            values["RPC URL"],
            values["Contract Address"],
            values["Sender Private Key"],
            values["Recipient Address"],
            values["Amount"],
        )
        self._run_task(
            task,
            self.send_button,
            lambda tx_hash: self.send_result.setPlainText(
                f"Transfer successful.\nTransaction Hash: {tx_hash}"
            ),
            lambda error: self.send_result.setPlainText(
                f"Transfer failed.\n{error}"
            ),
        )

    def _run_task(
        self,
        task: Callable[[], Any],
        button: QPushButton,
        on_success: Callable[[Any], None],
        on_failure: Callable[[str], None],
    ) -> None:
        button.setEnabled(False)
        worker = TaskThread(task, parent=self)
        self.workers.add(worker)
        worker.succeeded.connect(on_success)
        worker.failed.connect(on_failure)
        worker.finished.connect(lambda: button.setEnabled(True))
        worker.finished.connect(lambda: self._release_worker(worker))
        worker.start()

    def _release_worker(self, worker: TaskThread) -> None:
        self.workers.discard(worker)
        worker.deleteLater()

    def _generate_wallet(self) -> None:
        try:
            wallet = generate_wallet()
        except Exception as error:
            QMessageBox.critical(self, "Wallet Error", str(error))
            return

        self.wallets.append(wallet)
        row = self.wallet_table.rowCount()
        self.wallet_table.insertRow(row)
        for column, key in enumerate(("address", "private_key", "mnemonic")):
            item = QTableWidgetItem(wallet[key])
            item.setForeground(QColor("#F4F4F4"))
            self.wallet_table.setItem(row, column, item)
        self.wallet_table.selectRow(row)

    def _export_selected_wallet(self) -> None:
        row = self.wallet_table.currentRow()
        if row < 0 or row >= len(self.wallets):
            QMessageBox.warning(self, "No Wallet", "Select a wallet to export.")
            return

        filename = APP_ROOT / f"wallet_{row + 1}.json"
        try:
            save_wallet(self.wallets[row], filename)
        except OSError as error:
            QMessageBox.critical(self, "Export Error", str(error))
            return

        QMessageBox.information(
            self,
            "Wallet Exported",
            f"Wallet saved to:\n{filename}",
        )

    def _wallet_selection_qr(self) -> None:
        row = self.wallet_table.currentRow()
        if row < 0:
            self._set_qr(self.wallet_qr, "")
            return
        address_item = self.wallet_table.item(row, 0)
        self._set_qr(self.wallet_qr, address_item.text() if address_item else "")

    def _update_send_qr(self, address: str) -> None:
        self._set_qr(self.send_qr, address.strip())

    def _set_qr(self, label: QLabel, value: str) -> None:
        if not value:
            label.clear()
            label.setText("Enter or select an address")
            return

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(value)
        qr.make(fit=True)
        image = qr.make_image(fill_color="#111111", back_color="#FFFFFF")
        buffer = BytesIO()
        image.save(buffer, format="PNG")

        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")
        label.setText("")
        label.setPixmap(
            pixmap.scaled(
                220,
                220,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _save_settings(self) -> None:
        for display_name, rpc_input in self.settings_rpc_inputs.items():
            config_key = NETWORK_KEYS[display_name]
            self.networks[config_key]["rpc_url"] = rpc_input.text().strip()

        try:
            NETWORKS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with NETWORKS_PATH.open("w", encoding="utf-8") as config_file:
                json.dump(self.networks, config_file, indent=2)
                config_file.write("\n")
        except OSError as error:
            self.settings_result.setText(f"Could not save settings: {error}")
            return

        self._set_rpc_for_combo(self.deploy_network.currentText(), self.deploy_rpc)
        self._set_rpc_for_combo(self.mint_network.currentText(), self.mint_rpc)
        self._set_rpc_for_combo(self.send_network.currentText(), self.send_rpc)
        self.settings_result.setText("RPC settings saved.")

    def _apply_theme(self) -> None:
        QApplication.instance().setFont(QFont("Segoe UI", 10))
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #1E1E1E;
                color: #F4F4F4;
            }
            #sidebar {
                background-color: #171717;
                border-right: 1px solid #2D2D2D;
            }
            #logo {
                min-width: 38px;
                max-width: 38px;
                min-height: 38px;
                max-height: 38px;
                border-radius: 19px;
                background-color: #26A17B;
                color: white;
                font-size: 23px;
                font-weight: 700;
            }
            #brand {
                font-size: 18px;
                font-weight: 700;
                color: white;
            }
            #navButton {
                background: transparent;
                border: none;
                border-radius: 8px;
                color: #A8A8A8;
                font-size: 14px;
                padding: 12px 14px;
                text-align: left;
            }
            #navButton:hover {
                background-color: #242424;
                color: white;
            }
            #navButton:checked {
                background-color: #203B33;
                color: #4ED6AA;
                font-weight: 600;
            }
            #pageTitle {
                font-size: 28px;
                font-weight: 700;
                color: white;
            }
            #sectionTitle {
                font-size: 18px;
                font-weight: 650;
                color: white;
            }
            #metricValue {
                color: #4ED6AA;
                font-size: 26px;
                font-weight: 700;
            }
            #muted {
                color: #989898;
                font-size: 12px;
            }
            #bodyText {
                color: #D6D6D6;
                line-height: 1.5;
            }
            #statusBadge {
                background-color: #203B33;
                color: #4ED6AA;
                border: 1px solid #285444;
                border-radius: 12px;
                padding: 6px 11px;
                font-size: 11px;
                font-weight: 700;
            }
            #card {
                background-color: #252525;
                border: 1px solid #343434;
                border-radius: 12px;
            }
            QLineEdit, QComboBox, QTextEdit {
                background-color: #191919;
                color: #F2F2F2;
                border: 1px solid #3A3A3A;
                border-radius: 7px;
                padding: 10px 11px;
                selection-background-color: #26A17B;
            }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
                border: 1px solid #26A17B;
            }
            QComboBox::drop-down {
                border: none;
                width: 26px;
            }
            QComboBox QAbstractItemView {
                background-color: #242424;
                color: white;
                selection-background-color: #26A17B;
            }
            #primaryButton {
                background-color: #26A17B;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 11px 18px;
                font-weight: 700;
            }
            #primaryButton:hover {
                background-color: #2DB58A;
            }
            #primaryButton:disabled {
                background-color: #315C4E;
                color: #9ABAAF;
            }
            #secondaryButton {
                background-color: #333333;
                color: white;
                border: 1px solid #454545;
                border-radius: 8px;
                padding: 10px 16px;
            }
            #secondaryButton:hover {
                border-color: #26A17B;
            }
            #qrLabel {
                background-color: #F8F8F8;
                color: #555555;
                border: 8px solid #F8F8F8;
                border-radius: 8px;
            }
            #successText {
                color: #4ED6AA;
            }
            QTableWidget {
                background-color: #1C1C1C;
                alternate-background-color: #222222;
                color: white;
                border: 1px solid #363636;
                border-radius: 8px;
                gridline-color: #343434;
                selection-background-color: #285444;
            }
            QHeaderView::section {
                background-color: #2A2A2A;
                color: #CFCFCF;
                border: none;
                border-right: 1px solid #3A3A3A;
                padding: 10px;
                font-weight: 600;
            }
            QScrollBar:vertical {
                background: #202020;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #4A4A4A;
                border-radius: 5px;
                min-height: 30px;
            }
            QLabel {
                background: transparent;
            }
            """
        )


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Flash USDT Manager")
    app.setOrganizationName("FlashUSDT")
    window = FlashUSDTApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
