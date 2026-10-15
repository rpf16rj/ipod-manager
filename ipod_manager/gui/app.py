"""Janela principal do iPod Manager (PySide6).

Layout (ver specs/design.md):
- Toolbar: combo de unidade, "Detectar iPod", "Adicionar arquivos",
  "Remover", "Exportar", espaço livre, "Salvar no iPod", "Ejetar".
- Esquerda: playlists do iPod.
- Centro: tabela de músicas com edição inline, filtro, drag-and-drop.
- Direita: painel YouTube Music (busca, playlist por URL, fila de download).
- Status bar: mensagens + progresso global.

Toda mutação passa pelo ``IPodService`` e marca ``dirty``; a gravação real
só acontece em "Salvar no iPod" (com backup automático feito pelo service).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QByteArray, Qt, QMimeData, QObject, QTimer, QThread, QUrl,
    Signal, Slot,
)
from PySide6.QtGui import (
    QAction, QBrush, QCloseEvent, QColor, QDesktopServices,
    QDragEnterEvent, QDropEvent, QKeySequence, QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ipod_manager import APP_NAME, __version__
from ipod_manager.i18n import LANG_NAMES, set_lang, tr
from ipod_manager.ipod_service import IPodService
from ipod_manager.downloader import Downloader, YTMusicClient
from ipod_manager.gui.workers import (
    AddFilesWorker,
    DownloadWorker,
    ExportWorker,
    LoadWorker,
    OrphanScanWorker,
    PlaylistFetchWorker,
    RemoveTracksWorker,
    SaveWorker,
    SearchWorker,
)
from ipod_manager.gui.theme import (
    APP_STYLESHEET,
    animate_progress,
    fade_in,
    flash_color_steps,
)
from ipod_manager.gui.bulk_edit import BulkEditDialog

APP_TITLE = f"{APP_NAME} v{__version__}"

DONATE_URL = "https://www.buymeacoffee.com/rpf16rj"

logger = logging.getLogger("ipod_manager")

# Formatos que o iPod não toca (flac/ogg/opus/wma/ape/webm/mka) são
# convertidos automaticamente para MP3 via ffmpeg no service.
AUDIO_EXTS = {
    ".mp3", ".m4a", ".m4b", ".aac", ".wav", ".aif", ".aiff",
    ".flac", ".ogg", ".opus", ".wma", ".ape", ".webm", ".mka",
}
AUDIO_FILTER = (
    "Arquivos de áudio (*.mp3 *.m4a *.m4b *.aac *.wav *.aif *.aiff *.flac "
    "*.ogg *.opus *.wma *.ape *.webm *.mka);;"
    "Todos os arquivos (*.*)"
)

# Tipo MIME customizado para arrastar faixas da tabela p/ playlists.
TRACKIDS_MIME = "application/x-ipodmanager-trackids"

# Sentinela: "playlist atualmente aberta" vs. None = biblioteca.
_CURRENT = object()

# Colunas da tabela de músicas
(
    COL_TITLE, COL_ARTIST, COL_ALBUM, COL_GENRE, COL_YEAR, COL_NUM,
    COL_DUR, COL_STAR, COL_SIZE, COL_ADDED, COL_PL,
) = range(11)
_HEADER_KEYS = [
    "col_title", "col_artist", "col_album", "col_genre", "col_year",
    "col_num", "col_dur", "col_star", "col_size", "col_added",
    "col_playlists",
]


def table_headers() -> list[str]:
    """Cabeçalhos da tabela no idioma ativo."""
    return [tr(k) for k in _HEADER_KEYS]
# Larguras iniciais quando não há estado salvo no config.
COL_DEFAULT_WIDTHS = {
    COL_TITLE: 300, COL_ARTIST: 170, COL_ALBUM: 170, COL_GENRE: 110,
    COL_YEAR: 55, COL_NUM: 45, COL_DUR: 75, COL_STAR: 100,
    COL_SIZE: 75, COL_ADDED: 100, COL_PL: 160,
}
# coluna → campo editável de TrackInfo
EDITABLE_FIELDS = {
    COL_TITLE: "title",
    COL_ARTIST: "artist",
    COL_ALBUM: "album",
    COL_GENRE: "genre",
    COL_YEAR: "year",
    COL_NUM: "track_number",
    COL_STAR: "rating",
}


# --------------------------------------------------------------------------
# Helpers de formatação / config
# --------------------------------------------------------------------------

def fmt_duration_ms(ms: int) -> str:
    """'m:ss' a partir de milissegundos."""
    total = max(0, int(ms or 0)) // 1000
    return f"{total // 60}:{total % 60:02d}"


def fmt_duration_s(s: int) -> str:
    """'m:ss' a partir de segundos."""
    total = max(0, int(s or 0))
    return f"{total // 60}:{total % 60:02d}"


def fmt_bytes(n: int) -> str:
    size = float(max(0, int(n or 0)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def fmt_added(ts: int) -> str:
    """Epoch (s) → 'dd/mm/aaaa' (vazio se inválido)."""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%d/%m/%Y")
    except (OSError, OverflowError, ValueError):
        return ""


def rating_to_stars(rating: int) -> str:
    """0–100 → string de 5 posições com ★ preenchidas e ☆ vazias."""
    filled = max(0, min(5, round(int(rating or 0) / 20)))
    return "★" * filled + "☆" * (5 - filled)


def parse_rating(text: str) -> int | None:
    """Aceita '★★★', '3' (0–5) ou '60' (0–100). Retorna rating 0–100 ou None."""
    text = (text or "").strip()
    if not text:
        return 0
    if "★" in text or "☆" in text:
        return max(0, min(5, text.count("★"))) * 20
    try:
        value = int(text)
    except ValueError:
        return None
    if 0 <= value <= 5:
        return value * 20
    if 0 <= value <= 100:
        return round(value / 20) * 20
    return None


def _config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "iPodManager"


def _app_dir() -> Path:
    """Pasta do executável (frozen) ou raiz do projeto (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _legacy_staging_dir() -> Path:
    """Staging antigo (<=v0.1) em %LOCALAPPDATA% — para migração."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "iPodManager" / "staging"


def _default_staging_dir() -> Path:
    # Downloads ficam ao lado do exe/projeto: pasta "downloads".
    return _app_dir() / "downloads"


CONFIG_PATH = _config_dir() / "config.json"
LOG_PATH = _config_dir() / "ipodmanager.log"


def load_config() -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "staging_dir": str(_default_staging_dir()),
        "last_mount": "",
        "table_state": "",
        "lang": "pt",
        "donate_shown": False,
    }
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in cfg})
    except Exception:  # noqa: BLE001 — config ausente/corrompida → defaults
        pass
    # Migração: staging do config igual ao default antigo → novo default.
    try:
        if Path(cfg["staging_dir"]) == _legacy_staging_dir():
            cfg["staging_dir"] = str(_default_staging_dir())
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001 — falha ao gravar config não é fatal
        pass


def yt_track_label(track: Any) -> str:
    artist = getattr(track, "artist", "") or "—"
    album = getattr(track, "album", "") or ""
    dur = fmt_duration_s(getattr(track, "duration_s", 0))
    label = f"{track.title} — {artist}"
    if album:
        label += f" ({album})"
    return f"{label} [{dur}]"


# --------------------------------------------------------------------------
# Widgets auxiliares
# --------------------------------------------------------------------------

class _NumericItem(QTableWidgetItem):
    """Item de tabela com ordenação numérica (Ano, Nº, Duração, ★)."""

    def __init__(self, text: str = "", value: float = 0.0) -> None:
        super().__init__(text)
        self._sort_value = float(value)

    def __lt__(self, other: QTableWidgetItem) -> bool:  # ordenação por coluna
        if isinstance(other, _NumericItem):
            return self._sort_value < other._sort_value
        return super().__lt__(other)


def _audio_paths_from_mime(mime) -> list[str]:  # noqa: ANN001
    """Extrai paths de áudio de um QMimeData; pastas são varridas."""
    if not mime.hasUrls():
        return []
    paths: list[str] = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        p = Path(url.toLocalFile())
        if p.is_dir():
            paths.extend(
                str(f) for f in sorted(p.rglob("*"))
                if f.is_file() and f.suffix.lower() in AUDIO_EXTS
            )
        elif p.suffix.lower() in AUDIO_EXTS:
            paths.append(str(p))
    return paths


class _TrackTable(QTableWidget):
    """QTableWidget: drop de arquivos e drag de faixas p/ playlists."""

    files_dropped = Signal(list)  # list[str]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        # Drag das linhas selecionadas (mime TRACKIDS_MIME) p/ playlists.
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setDragDropOverwriteMode(False)

    def mimeData(self, items: list) -> QMimeData:
        """Produz os track_ids selecionados para o drag interno."""
        ids = []
        for item in items or ():
            if item.column() != 0:
                continue
            tid = getattr(
                item.data(Qt.ItemDataRole.UserRole), "track_id", None
            )
            if tid is not None:
                ids.append(tid)
        mime = QMimeData()
        mime.setData(
            TRACKIDS_MIME, json.dumps(sorted(set(ids))).encode("utf-8")
        )
        return mime

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _audio_paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:
        if _audio_paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = _audio_paths_from_mime(event.mimeData())
        if paths:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
        else:
            # Drag interno (TRACKIDS) nunca move linhas da tabela.
            event.ignore()


class _PlaylistList(QListWidget):
    """Lista de playlists que aceita drop de faixas e de arquivos."""

    tracks_dropped = Signal(object, list)  # PlaylistInfo|None, [track_id]
    files_dropped = Signal(object, list)   # PlaylistInfo|None, [path]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def _target(self, pos) -> Any:  # noqa: ANN001
        item = self.itemAt(pos)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _acceptable(self, mime) -> bool:  # noqa: ANN001
        return mime.hasFormat(TRACKIDS_MIME) or bool(
            _audio_paths_from_mime(mime)
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._acceptable(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:
        if self._acceptable(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        pl = self._target(event.position().toPoint())
        mime = event.mimeData()
        if mime.hasFormat(TRACKIDS_MIME):
            try:
                ids = json.loads(bytes(mime.data(TRACKIDS_MIME)))
            except Exception:  # noqa: BLE001
                ids = []
            if ids and pl is not None:
                event.setDropAction(Qt.DropAction.CopyAction)
                event.acceptProposedAction()
                self.tracks_dropped.emit(pl, ids)
            else:
                event.ignore()
            return
        paths = _audio_paths_from_mime(mime)
        if paths:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.acceptProposedAction()
            self.files_dropped.emit(pl, paths)
        else:
            event.ignore()


class _QueueRow(QWidget):
    """Linha da fila de downloads: nome, barra de progresso e erro."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.label = QLabel(text)
        self.label.setToolTip(text)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFixedWidth(110)
        self.bar.setTextVisible(True)
        top.addWidget(self.label, stretch=1)
        top.addWidget(self.bar)
        layout.addLayout(top)
        self.err_label = QLabel()
        self.err_label.setStyleSheet("color: #c0392b; font-size: 11px;")
        self.err_label.setWordWrap(True)
        self.err_label.setVisible(False)
        layout.addWidget(self.err_label)

    def set_progress(self, pct: int) -> None:
        self.bar.setValue(max(0, min(100, pct)))

    def set_done(self, path: str) -> None:
        self.bar.setValue(100)
        self.setToolTip(path)

    def set_failed(self, err: str) -> None:
        self.bar.setValue(100)
        self.bar.setFormat("falhou")
        self.label.setText(f"⚠ {self.label.text()}")
        resumo = (err or "erro desconhecido").splitlines()[0][:140]
        self.err_label.setText(f"Motivo: {resumo}")
        self.err_label.setVisible(True)
        self.setToolTip(err)


class QtLogHandler(QObject, logging.Handler):
    """Handler de logging que emite cada registro via signal p/ a GUI.

    O signal atravessa threads com segurança (queued connection), então
    logs vindos dos workers aparecem no painel sem risco de corrupção.
    """

    record = Signal(str)

    def __init__(self) -> None:
        QObject.__init__(self)
        logging.Handler.__init__(self)
        self.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                              datefmt="%H:%M:%S")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.record.emit(self.format(record))
        except Exception:  # noqa: BLE001 — log nunca deve derrubar o app
            pass


# --------------------------------------------------------------------------
# MainWindow
# --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Janela única do aplicativo."""

    # Emitido pela thread que está terminando; o slot roda na GUI.
    _release_thread_worker = Signal(object, object)  # (thread, worker)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(APP_TITLE)
        self.resize(1200, 700)

        # Estado da sessão
        self._config = load_config()
        set_lang(self._config.get("lang", "pt"))
        self._service: Any = None
        self._device_info: Any = None
        self._tracks: dict[int, Any] = {}            # track_id → TrackInfo
        self._playlists: list[Any] = []              # list[PlaylistInfo]
        self._current_playlist_id: int | None = None  # None = biblioteca

        self._yt_client: Any = None
        self._downloader: Any = None
        self._loaded_playlist_name: str | None = None

        self._busy = 0                  # workers que mutam o service ativos
        self._wait_cursor = False       # WaitCursor ativo durante _busy
        self._dl_worker: Any = None     # DownloadWorker ativo (p/ cancel)
        self._anims: set = set()        # animações em andamento (refs)
        self._flash_ids: set | None = None  # ids p/ flash após _populate
        self._threads: set[QThread] = set()
        self._workers: set = set()      # refs vivas p/ evitar GC do worker
        self._release_thread_worker.connect(
            self._on_release_thread_worker
        )
        self._suspend_table_events = False
        self._closing = False
        self._dl_rows: list[_QueueRow] = []
        self._dl_total = 0
        self._dl_finished_count = 0
        self._dl_active = False  # um lote de download por vez
        self._dl_tracks: list[Any] = []      # YTTrack do último lote
        self._dl_failed: dict[int, Any] = {}  # idx -> YTTrack que falhou
        self._dl_to_ipod = False             # último lote foi p/ o iPod?
        self._dl_playlist_name_ctx: str | None = None

        self.setAcceptDrops(True)  # drop de arquivos em qualquer lugar
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._build_log_dock()
        self._update_actions()

        # Detecção automática ao abrir (R1.1), já em thread.
        QTimer.singleShot(0, self._detect_ipods)
        # Convite de apoio — só na primeira abertura.
        QTimer.singleShot(1500, self._maybe_show_donate)

    # ------------------------------------------------------------------
    # Construção da UI
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Principal")
        tb.setObjectName("mainToolbar")
        tb.setMovable(False)

        tb.addWidget(QLabel(" " + tr("drive_label") + " "))
        self.drive_combo = QComboBox()
        self.drive_combo.setEditable(True)
        self.drive_combo.setMinimumWidth(110)
        self.drive_combo.setPlaceholderText("ex.: I:\\")
        self.drive_combo.setToolTip(tr("drive_tip"))
        self.drive_combo.activated.connect(self._on_drive_activated)
        tb.addWidget(self.drive_combo)

        self.act_detect = tb.addAction(tr("detect"))
        self.act_detect.setToolTip(tr("detect_tip"))
        self.act_detect.setShortcut(QKeySequence.StandardKey.Refresh)
        self.act_detect.triggered.connect(self._detect_ipods)

        tb.addSeparator()

        self.act_add = tb.addAction(tr("add_files"))
        self.act_add.setToolTip(tr("add_files_tip"))
        self.act_add.triggered.connect(self._choose_files)

        self.act_remove = tb.addAction(tr("remove"))
        self.act_remove.setToolTip(tr("remove_tip"))
        self.act_remove.triggered.connect(self._remove_selected_tracks)

        self.act_bulk = tb.addAction(tr("bulk_edit"))
        self.act_bulk.setToolTip(tr("bulk_edit_tip"))
        self.act_bulk.triggered.connect(self._bulk_edit)

        self.act_export = tb.addAction(tr("export"))
        self.act_export.setToolTip(tr("export_tip"))
        self.act_export.triggered.connect(self._export_selected_tracks)

        tb.addSeparator()

        self.space_label = QLabel(" " + tr("no_ipod_short") + " ")
        tb.addWidget(self.space_label)

        tb.addSeparator()

        self.act_save = tb.addAction(tr("save"))
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.setToolTip(tr("save_tip"))
        self.act_save.triggered.connect(self._save_ipod)
        # Botão de destaque no tema (objectName "saveButton" no QSS).
        btn = tb.widgetForAction(self.act_save)
        if btn is not None:
            btn.setObjectName("saveButton")

        self.act_eject = tb.addAction(tr("eject"))
        self.act_eject.setToolTip(tr("eject_tip"))
        self.act_eject.triggered.connect(self._eject_ipod)

        tb.addSeparator()

        self.act_log = tb.addAction(tr("log"))
        self.act_log.setCheckable(True)
        self.act_log.setChecked(True)
        self.act_log.setToolTip(tr("log"))
        self.act_log.triggered.connect(self._toggle_log)

        # Menu "Opções": idioma, apoiar o projeto, sobre.
        self.options_btn = QToolButton()
        self.options_btn.setText(tr("options"))
        self.options_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        options = QMenu(self.options_btn)

        lang_menu = options.addMenu(tr("language"))
        self._lang_actions: dict[str, QAction] = {}
        for code, name in LANG_NAMES.items():
            act = lang_menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(
                code == self._config.get("lang", "pt")
            )
            act.triggered.connect(
                lambda checked, c=code: self._set_language(c)
            )
            self._lang_actions[code] = act

        options.addSeparator()
        act_donate = options.addAction(tr("support"))
        act_donate.triggered.connect(self._open_donate)
        act_about = options.addAction(tr("about"))
        act_about.triggered.connect(self._show_about)

        self.options_btn.setMenu(options)
        tb.addWidget(self.options_btn)

    def _build_central(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_playlist_panel())
        splitter.addWidget(self._build_tracks_panel())
        splitter.addWidget(self._build_yt_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([200, 620, 380])
        self.setCentralWidget(splitter)

    # -- painel esquerdo: playlists ------------------------------------

    def _build_playlist_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(QLabel(tr("playlists") + " — iPod"))

        self.playlist_list = _PlaylistList()
        self.playlist_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.playlist_list.customContextMenuRequested.connect(
            self._playlist_context_menu
        )
        self.playlist_list.itemSelectionChanged.connect(
            self._on_playlist_selected
        )
        self.playlist_list.tracks_dropped.connect(
            self._on_tracks_dropped_on_playlist
        )
        self.playlist_list.files_dropped.connect(
            self._on_files_dropped_on_playlist
        )
        self.playlist_list.setToolTip(tr("drop_tip"))
        layout.addWidget(self.playlist_list, stretch=1)

        row = QHBoxLayout()
        self.btn_new_playlist = QPushButton(tr("new_playlist"))
        self.btn_new_playlist.setToolTip(tr("new_playlist_tip"))
        self.btn_new_playlist.clicked.connect(self._create_playlist)
        row.addWidget(self.btn_new_playlist)
        row.addStretch(1)
        layout.addLayout(row)
        return panel

    # -- painel central: tabela de músicas ------------------------------

    def _build_tracks_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filtrar músicas…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)

        self.table = _TrackTable()
        self.table.setColumnCount(len(_HEADER_KEYS))
        self.table.setHorizontalHeaderLabels(table_headers())
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table.customContextMenuRequested.connect(
            self._table_context_menu
        )
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.files_dropped.connect(self._add_files_to_ipod)
        self.table.itemSelectionChanged.connect(
            self._on_selection_changed
        )
        # Del remove a seleção — só quando a tabela tem foco.
        self._del_shortcut = QShortcut(QKeySequence.Delete, self.table)
        self._del_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self._del_shortcut.activated.connect(self._remove_selected_tracks)

        header = self.table.horizontalHeader()
        # Colunas redimensionáveis pelo usuário (arrastar a divisória);
        # larguras/visibilidade persistidas no config.
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        state = self._config.get("table_state")
        restored = False
        if state:
            try:
                restored = header.restoreState(
                    QByteArray.fromBase64(state.encode("ascii"))
                )
            except Exception:  # noqa: BLE001
                restored = False
        if not restored:
            for col, width in COL_DEFAULT_WIDTHS.items():
                self.table.setColumnWidth(col, width)
        header.setStretchLastSection(True)  # Playlists ocupa a sobra
        # Menu de contexto do cabeçalho: mostrar/ocultar colunas.
        header.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        header.customContextMenuRequested.connect(self._header_menu)
        layout.addWidget(self.table, stretch=1)
        return panel

    def _header_menu(self, pos) -> None:  # noqa: ANN001
        """Menu do cabeçalho: mostrar/ocultar cada coluna."""
        header = self.table.horizontalHeader()
        menu = QMenu(self)
        for col, title in enumerate(table_headers()):
            act = menu.addAction(title)
            act.setCheckable(True)
            visible = not self.table.isColumnHidden(col)
            act.setChecked(visible)
            if col == COL_TITLE:
                act.setEnabled(False)  # coluna principal sempre visível
            act.triggered.connect(
                lambda checked, c=col: self._toggle_column(c, checked)
            )
        menu.exec(header.mapToGlobal(pos))

    def _toggle_column(self, col: int, visible: bool) -> None:
        self.table.setColumnHidden(col, not visible)
        self._persist_table_state()

    def _persist_table_state(self) -> None:
        try:
            state = self.table.horizontalHeader().saveState()
            self._config["table_state"] = bytes(
                state.toBase64()
            ).decode("ascii")
            save_config(self._config)
        except Exception:  # noqa: BLE001
            pass

    # -- painel direito: YouTube Music ----------------------------------

    def _build_yt_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)

        layout.addWidget(QLabel(tr("yt_title")))

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("search_tip"))
        self.search_edit.returnPressed.connect(self._start_search)
        self.btn_search = QPushButton(tr("btn_search"))
        self.btn_search.clicked.connect(self._start_search)
        search_row.addWidget(self.search_edit, stretch=1)
        search_row.addWidget(self.btn_search)
        layout.addLayout(search_row)

        self.search_results = QListWidget()
        self.search_results.setAlternatingRowColors(True)
        layout.addWidget(self.search_results, stretch=2)

        layout.addWidget(QLabel(tr("url_label")))
        url_row = QHBoxLayout()
        self.playlist_url_edit = QLineEdit()
        self.playlist_url_edit.setPlaceholderText(
            "https://music.youtube.com/playlist?list=…"
        )
        self.playlist_url_edit.setToolTip(tr("url_tip"))
        self.playlist_url_edit.returnPressed.connect(self._fetch_playlist)
        self.btn_fetch_playlist = QPushButton(tr("btn_load_pl"))
        self.btn_fetch_playlist.clicked.connect(self._fetch_playlist)
        url_row.addWidget(self.playlist_url_edit, stretch=1)
        url_row.addWidget(self.btn_fetch_playlist)
        layout.addLayout(url_row)

        self.playlist_name_label = QLabel(tr("playlist_label"))
        layout.addWidget(self.playlist_name_label)

        self.playlist_tracks_list = QListWidget()
        self.playlist_tracks_list.setAlternatingRowColors(True)
        layout.addWidget(self.playlist_tracks_list, stretch=2)

        self.chk_to_ipod = QCheckBox(tr("chk_to_ipod"))
        self.chk_to_ipod.setChecked(True)
        layout.addWidget(self.chk_to_ipod)

        dl_row = QHBoxLayout()
        self.btn_dl_selected = QPushButton(tr("dl_selected"))
        self.btn_dl_selected.clicked.connect(self._download_selected)
        self.btn_dl_all = QPushButton(tr("dl_all"))
        self.btn_dl_all.clicked.connect(self._download_all)
        self.btn_dl_playlist = QPushButton(tr("dl_playlist_ipod"))
        self.btn_dl_playlist.setToolTip(tr("dl_playlist_tip"))
        self.btn_dl_playlist.clicked.connect(self._download_playlist_to_ipod)
        dl_row.addWidget(self.btn_dl_selected)
        dl_row.addWidget(self.btn_dl_all)
        dl_row.addWidget(self.btn_dl_playlist)
        layout.addLayout(dl_row)

        self.btn_retry = QPushButton(tr("retry_failed"))
        self.btn_retry.setToolTip(tr("retry_tip"))
        self.btn_retry.setVisible(False)
        self.btn_retry.clicked.connect(self._retry_failed_downloads)
        layout.addWidget(self.btn_retry)

        self.btn_cancel_dl = QPushButton(tr("cancel_dl"))
        self.btn_cancel_dl.setToolTip(tr("cancel_dl_tip"))
        self.btn_cancel_dl.setVisible(False)
        self.btn_cancel_dl.clicked.connect(self._cancel_downloads)
        layout.addWidget(self.btn_cancel_dl)

        layout.addWidget(QLabel(tr("queue")))
        self.download_queue = QListWidget()
        layout.addWidget(self.download_queue, stretch=2)
        return panel

    def _build_statusbar(self) -> None:
        self.status_label = QLabel(tr("ready"))
        self.statusBar().addWidget(self.status_label, stretch=1)
        self.sel_label = QLabel("")
        self.statusBar().addPermanentWidget(self.sel_label)
        self.status_progress = QProgressBar()
        self.status_progress.setRange(0, 100)
        self.status_progress.setFixedWidth(180)
        self.status_progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.status_progress)

    def _build_log_dock(self) -> None:
        """Dock inferior com o log ao vivo (verbose opcional)."""
        self.log_dock = QDockWidget(tr("log_dock"), self)
        self.log_dock.setObjectName("logDock")
        self.log_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        controls = QHBoxLayout()
        self.chk_verbose = QCheckBox(tr("log_verbose"))
        self.chk_verbose.setToolTip(tr("log_verbose_tip"))
        self.chk_verbose.toggled.connect(self._toggle_verbose)
        controls.addWidget(self.chk_verbose)
        btn_clear = QPushButton(tr("log_clear"))
        btn_clear.clicked.connect(lambda: self.log_view.clear())
        controls.addWidget(btn_clear)
        btn_open_log = QPushButton(tr("log_open_file"))
        btn_open_log.setToolTip(str(LOG_PATH))
        btn_open_log.clicked.connect(self._open_log_file)
        controls.addWidget(btn_open_log)
        controls.addWidget(QLabel(f" {LOG_PATH} "))
        controls.addStretch(1)
        layout.addLayout(controls)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        layout.addWidget(self.log_view)

        self.log_dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.log_dock.visibilityChanged.connect(
            lambda vis: self.act_log.setChecked(vis)
        )

        # Liga o handler ao logger raiz: captura ipod_manager, pygpod,
        # yt_dlp, ytmusicapi etc.
        self._qt_log_handler = QtLogHandler()
        self._qt_log_handler.record.connect(self.log_view.appendPlainText)
        logging.getLogger().addHandler(self._qt_log_handler)
        logger.info("iPod Manager iniciado — log em %s", LOG_PATH)

    @Slot(bool)
    def _toggle_log(self, checked: bool) -> None:
        self.log_dock.setVisible(checked)

    # -- Opções: idioma / apoiar / sobre --------------------------------

    def _set_language(self, code: str) -> None:
        if code == self._config.get("lang", "pt"):
            return
        self._config["lang"] = code
        save_config(self._config)
        for c, act in self._lang_actions.items():
            act.setChecked(c == code)
        QMessageBox.information(
            self, tr("options"), tr("lang_restart")
        )

    def _open_donate(self) -> None:
        QDesktopServices.openUrl(QUrl(DONATE_URL))

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            tr("about"),
            f"<b>{APP_TITLE}</b><br><br>"
            + tr("about_text")
            + "<br><br>"
            + '<a href="' + DONATE_URL + '">' + tr("support") + "</a>",
        )

    def _maybe_show_donate(self) -> None:
        """Convite de apoio amigável — só na primeira abertura."""
        if self._config.get("donate_shown"):
            return
        self._config["donate_shown"] = True
        save_config(self._config)
        box = QMessageBox(self)
        box.setWindowTitle(tr("donate_title"))
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(tr("donate_text"))
        btn_yes = box.addButton(
            tr("donate_btn"), QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(
            tr("donate_later"), QMessageBox.ButtonRole.RejectRole
        )
        chk = QCheckBox(tr("donate_hide"))
        box.setCheckBox(chk)
        box.exec()
        if box.clickedButton() is btn_yes:
            self._open_donate()
        if not chk.isChecked():
            # Sem marcar "não mostrar": volta a exibir na próxima vez.
            self._config["donate_shown"] = False
            save_config(self._config)

    @Slot(bool)
    def _toggle_verbose(self, checked: bool) -> None:
        logging.getLogger().setLevel(
            logging.DEBUG if checked else logging.INFO
        )

    def _open_log_file(self) -> None:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.touch(exist_ok=True)
        os.startfile(str(LOG_PATH))  # noqa: S606 — abrir arquivo local

    # ------------------------------------------------------------------
    # Gerenciamento de workers/threads
    # ------------------------------------------------------------------

    def _run_worker(self, worker, *, mutating: bool = False) -> None:
        """Move ``worker`` para uma QThread nova e o executa."""
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        # Manter referência Python ao worker até a thread terminar — sem ela,
        # o GC destrói o QObject e os signals nunca chegam à GUI. A liberação
        # é feita na thread da GUI via _release_thread_worker: thread.finished
        # é emitido pela thread que está morrendo, e criar timers/postar
        # eventos nesse contexto é inseguro (event dispatcher já saindo).
        self._threads.add(thread)
        self._workers.add(worker)
        thread.finished.connect(
            lambda: self._release_thread_worker.emit(thread, worker)
        )

        if mutating:
            self._busy += 1
            worker.finished.connect(self._on_mutating_worker_done)
            self._update_actions()

        thread.start()

    @Slot()
    def _on_mutating_worker_done(self) -> None:
        self._busy = max(0, self._busy - 1)
        self._update_actions()

    @Slot(object, object)
    def _on_release_thread_worker(self, thread: object, worker: object) -> None:
        """Solta as referências Python — sempre executado na thread da GUI."""
        try:
            self._threads.discard(thread)
        except Exception:  # noqa: BLE001 — wrapper pode estar dangling
            self._threads = {t for t in self._threads if t is not thread}
        try:
            self._workers.discard(worker)
        except Exception:  # noqa: BLE001
            self._workers = {w for w in self._workers if w is not worker}

    def _set_status(self, msg: str, *, busy: bool = False) -> None:
        self.status_label.setText(msg)
        if busy:
            self.status_progress.setRange(0, 0)  # indeterminado
            self.status_progress.setVisible(True)
        else:
            self.status_progress.setRange(0, 100)
            self.status_progress.setVisible(False)

    def _set_global_progress(self, done: int, total: int) -> None:
        self.status_progress.setRange(0, max(1, total))
        self.status_progress.setVisible(True)
        if done >= total or done <= 0:
            self.status_progress.setValue(done)
            return
        anim = animate_progress(self.status_progress, done)
        self._anims.add(anim)
        anim.finished.connect(lambda: self._anims.discard(anim))

    def _warn(self, title: str, msg: str) -> None:
        logger.warning("%s: %s", title, msg.replace("\n", " | "))
        QMessageBox.warning(self, title, msg)

    def _service_errors(self) -> list[str]:
        """Falhas individuais do último lote do service, se houver."""
        if self._service is None:
            return []
        return list(getattr(self._service, "last_errors", []) or [])

    def _ffmpeg_path(self) -> str | None:
        """Binário ffmpeg do imageio-ffmpeg; None se indisponível."""
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:  # noqa: BLE001 — sem ffmpeg, conversão é pulada
            return None

    # ------------------------------------------------------------------
    # Drag-and-drop na janela (fora da tabela/playlists)
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _audio_paths_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = _audio_paths_from_mime(event.mimeData())
        if paths:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.acceptProposedAction()
            self._add_files_to_ipod(paths)
        else:
            event.ignore()

    # ------------------------------------------------------------------
    # Estado dos controles
    # ------------------------------------------------------------------

    def _update_actions(self) -> None:
        busy = self._busy > 0
        has_ipod = self._service is not None and not busy
        dirty = bool(has_ipod and getattr(self._service, "dirty", False))

        # UX: "*" no título + botão Salvar em negrito indicam mudanças.
        self.setWindowTitle(APP_TITLE + (" *" if dirty else ""))
        font = self.act_save.font()
        font.setBold(dirty)
        self.act_save.setFont(font)

        # UX: cursor de espera enquanto há operação em andamento.
        if busy and not self._wait_cursor:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._wait_cursor = True
        elif not busy and self._wait_cursor:
            QApplication.restoreOverrideCursor()
            self._wait_cursor = False

        self.act_save.setEnabled(dirty)
        self.act_add.setEnabled(has_ipod)
        self.act_remove.setEnabled(has_ipod)
        self.act_export.setEnabled(has_ipod)
        self.act_eject.setEnabled(has_ipod)
        self.act_detect.setEnabled(not busy)
        self.drive_combo.setEnabled(not busy)
        self.btn_new_playlist.setEnabled(has_ipod)
        self.playlist_list.setEnabled(has_ipod)
        self.table.setEnabled(has_ipod)

        # Downloads que tocam o iPod exigem service livre; staging-only não.
        has_queue = (
            self.search_results.count() > 0
            or self.playlist_tracks_list.count() > 0
        )
        dl_free = not busy and not self._dl_active
        self.btn_dl_selected.setEnabled(has_queue and dl_free)
        self.btn_dl_all.setEnabled(has_queue and dl_free)
        self.btn_dl_playlist.setEnabled(
            has_ipod and dl_free and self.playlist_tracks_list.count() > 0
        )
        self.btn_retry.setEnabled(
            bool(self._dl_failed) and dl_free and (not busy)
        )
        self.btn_retry.setVisible(bool(self._dl_failed))
        self.btn_cancel_dl.setVisible(self._dl_active)
        self.chk_to_ipod.setEnabled(not busy)
        if not has_ipod:
            self.chk_to_ipod.setToolTip(
                "Disponível após carregar um iPod; sem iPod, os arquivos "
                "vão apenas para a pasta de staging."
            )
        else:
            self.chk_to_ipod.setToolTip("")

    def _mark_dirty(self) -> None:
        self._update_actions()

    # ------------------------------------------------------------------
    # Detecção e carga do iPod
    # ------------------------------------------------------------------

    @Slot()
    def _detect_ipods(self) -> None:
        self._set_status("Detectando iPods…", busy=True)
        worker = LoadWorker(service_cls=IPodService, detect_only=True)
        worker.detected.connect(self._on_detected)
        worker.error.connect(self._on_detect_error)
        worker.finished.connect(self._on_worker_finished_idle)
        self._run_worker(worker)

    @Slot(str)
    def _on_detect_error(self, err: str) -> None:
        self._warn("Detecção", f"Falha ao detectar iPods:\n{err}")

    @Slot()
    def _on_worker_finished_idle(self) -> None:
        self._set_status("Pronto")

    @Slot(list)
    def _on_detected(self, mounts: list) -> None:
        self.drive_combo.blockSignals(True)
        self.drive_combo.clear()
        self.drive_combo.addItems([str(m) for m in mounts])
        self.drive_combo.blockSignals(False)

        last = self._config.get("last_mount", "")
        target = last if last in mounts else (mounts[0] if len(mounts) == 1 else "")
        if target:
            idx = self.drive_combo.findText(target)
            if idx >= 0:
                self.drive_combo.setCurrentIndex(idx)
            self._load_mount(target)
        elif not mounts:
            self._set_status("Nenhum iPod detectado")

    @Slot()
    def _on_drive_activated(self, _index: int) -> None:
        mount = self.drive_combo.currentText().strip()
        if mount:
            self._load_mount(mount)

    def _load_mount(self, mount: str) -> None:
        self._set_status(f"Carregando iPod em {mount}…", busy=True)
        worker = LoadWorker(mountpoint=mount, service_cls=IPodService)
        worker.service_ready.connect(self._on_service_ready)
        worker.loaded.connect(self._on_loaded)
        worker.error.connect(self._on_load_error)
        self._run_worker(worker, mutating=True)

    @Slot(object)
    def _on_service_ready(self, service: object) -> None:
        self._service = service

    @Slot(object, list, list)
    def _on_loaded(self, info: object, tracks: list, playlists: list) -> None:
        self._device_info = info
        self._tracks = {t.track_id: t for t in tracks}
        self._playlists = list(playlists)
        self._current_playlist_id = None

        mount = getattr(info, "mountpoint", "") or self.drive_combo.currentText()
        if mount:
            self._config["last_mount"] = mount
            save_config(self._config)

        free = getattr(info, "free_bytes", 0)
        cap = getattr(info, "capacity_bytes", 0)
        name = getattr(info, "name", "iPod")
        count = getattr(info, "track_count", len(tracks))
        self.space_label.setText(f" Livre: {fmt_bytes(free)} / {fmt_bytes(cap)} ")

        self._refresh_playlist_list()
        self._show_current_view()
        self._set_status(f"{name}: {count} faixas carregadas")
        self._update_actions()
        self._scan_orphans()

    def _scan_orphans(self) -> None:
        """Detecta arquivos órfãos após a carga (em thread)."""
        if self._service is None:
            return
        worker = OrphanScanWorker(self._service)
        worker.found.connect(self._on_orphans_found)
        self._run_worker(worker)

    @Slot(list, int)
    def _on_orphans_found(self, paths: list, total: int) -> None:
        if not paths or self._closing or self._service is None:
            return
        answer = QMessageBox.question(
            self,
            "Arquivos órfãos",
            f"Foram encontrados {len(paths)} arquivo(s) órfãos no iPod "
            f"({fmt_bytes(total)}): músicas copiadas que não foram "
            "gravadas no banco de dados e só ocupam espaço.\n\n"
            "Remover agora para liberar espaço?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            freed = self._service.remove_orphans()
        except Exception as exc:  # noqa: BLE001
            self._warn("Órfãos", f"Falha ao remover órfãos:\n{exc}")
            return
        try:
            usage_free = self._service.device_info().free_bytes
            cap = self._device_info.capacity_bytes if self._device_info else 0
            self.space_label.setText(
                f" Livre: {fmt_bytes(usage_free)} / {fmt_bytes(cap)} "
            )
        except Exception:  # noqa: BLE001
            pass
        self._set_status(
            f"Espaço liberado: {fmt_bytes(freed)} "
            f"({len(paths)} arquivo(s) órfãos removidos)"
        )

    @Slot(str)
    def _on_load_error(self, err: str) -> None:
        self._service = None
        self._set_status("Falha ao carregar iPod")
        self._update_actions()
        self._warn(
            "iPod",
            f"Não foi possível abrir o iPod:\n{err}\n\n"
            "Verifique se a unidade está correta e o iPod está montado.",
        )

    # ------------------------------------------------------------------
    # Tabela de músicas
    # ------------------------------------------------------------------

    def _populate_table(self, tracks: list) -> None:
        self._suspend_table_events = True
        # Mapa track_id → playlists da faixa (coluna "Playlists").
        try:
            pl_map = (
                self._service.playlists_by_track()
                if self._service is not None else {}
            )
        except Exception:  # noqa: BLE001
            pl_map = {}
        try:
            self.table.setSortingEnabled(False)
            self.table.setRowCount(0)
            self.table.setRowCount(len(tracks))
            editable = (
                Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsEditable
                | Qt.ItemFlag.ItemIsDragEnabled
            )
            readonly = (
                Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsDragEnabled
            )
            for row, t in enumerate(tracks):
                items: list[QTableWidgetItem] = [
                    QTableWidgetItem(str(t.title)),
                    QTableWidgetItem(str(t.artist)),
                    QTableWidgetItem(str(t.album)),
                    QTableWidgetItem(str(t.genre)),
                    _NumericItem(str(t.year or ""), float(t.year or 0)),
                    _NumericItem(
                        str(t.track_number or ""),
                        float(t.track_number or 0),
                    ),
                    _NumericItem(
                        fmt_duration_ms(t.duration_ms),
                        float(t.duration_ms or 0),
                    ),
                    _NumericItem(
                        rating_to_stars(t.rating), float(t.rating or 0)
                    ),
                    _NumericItem(
                        fmt_bytes(t.size_bytes), float(t.size_bytes or 0)
                    ),
                    _NumericItem(
                        fmt_added(t.added_ts), float(t.added_ts or 0)
                    ),
                    QTableWidgetItem(
                        ", ".join(pl_map.get(t.track_id, []))
                    ),
                ]
                for col, item in enumerate(items):
                    item.setFlags(
                        editable if col in EDITABLE_FIELDS else readonly
                    )
                    # Guarda o TrackInfo inteiro (não o id): ids do pygpod
                    # podem exceder int64 e estourar a conversão do QVariant.
                    item.setData(Qt.ItemDataRole.UserRole, t)
                    self.table.setItem(row, col, item)
        finally:
            self._suspend_table_events = False
            self.table.setSortingEnabled(True)
            self._apply_filter(self.filter_edit.text())
        self._flash_pending_rows()

    def _flash_pending_rows(self) -> None:
        """Flash verde que desbota nas linhas recém-adicionadas."""
        ids = self._flash_ids
        self._flash_ids = None
        if not ids:
            return
        rows = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            track = item.data(Qt.ItemDataRole.UserRole) if item else None
            if getattr(track, "track_id", None) in ids:
                rows.append(r)
        if not rows:
            return
        steps = flash_color_steps()

        def apply(color: QColor | None) -> None:
            for r in rows:
                for c in range(self.table.columnCount()):
                    cell = self.table.item(r, c)
                    if cell is not None:
                        cell.setBackground(color or QBrush())

        apply(steps[0])
        QTimer.singleShot(350, lambda: apply(steps[1]))
        QTimer.singleShot(700, lambda: apply(steps[2]))
        QTimer.singleShot(1050, lambda: apply(None))
        first = self.table.item(rows[0], 0)
        if first is not None:
            self.table.scrollToItem(first)

    def _selected_track_ids(self) -> list[int]:
        ids: list[int] = []
        seen: set[int] = set()
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item is None:
                continue
            track = item.data(Qt.ItemDataRole.UserRole)
            tid = getattr(track, "track_id", None)
            if tid is not None and tid not in seen:
                seen.add(tid)
                ids.append(tid)
        return ids

    @Slot(QTableWidgetItem)
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suspend_table_events or self._service is None:
            return
        col = item.column()
        field = EDITABLE_FIELDS.get(col)
        if field is None:
            return
        track = item.data(Qt.ItemDataRole.UserRole)
        tid = getattr(track, "track_id", None)
        if tid is None:
            return

        old_value = getattr(track, field)
        text = item.text()

        if field in ("year", "track_number"):
            try:
                value = int(text.strip() or "0")
            except ValueError:
                self._revert_cell(item, old_value)
                self._set_status(
                    f"Valor inválido para {table_headers()[col]}"
                )
                return
        elif field == "rating":
            value = parse_rating(text)
            if value is None:
                self._revert_cell(item, old_value)
                self._set_status(
                    "Avaliação inválida — use ★ (0–5) ou 0–100"
                )
                return
            # Normaliza a exibição para estrelas.
            self._suspend_table_events = True
            item.setText(rating_to_stars(value))
            if isinstance(item, _NumericItem):
                item._sort_value = float(value)
            self._suspend_table_events = False
        else:
            value = text

        try:
            self._service.update_track(tid, **{field: value})
        except Exception as exc:  # noqa: BLE001
            self._revert_cell(item, old_value)
            self._warn("Edição", f"Falha ao atualizar a faixa:\n{exc}")
            return
        setattr(track, field, value)
        self._mark_dirty()

    def _revert_cell(self, item: QTableWidgetItem, old_value: Any) -> None:
        self._suspend_table_events = True
        if item.column() == COL_STAR:
            item.setText(rating_to_stars(old_value))
        elif isinstance(old_value, int):
            item.setText(str(old_value or ""))
        else:
            item.setText(str(old_value or ""))
        self._suspend_table_events = False

    @Slot(str)
    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for row in range(self.table.rowCount()):
            visible = not needle
            if not visible:
                for col in range(self.table.columnCount()):
                    it = self.table.item(row, col)
                    if it and needle in it.text().lower():
                        visible = True
                        break
            self.table.setRowHidden(row, not visible)

    # ------------------------------------------------------------------
    # Ações sobre músicas
    # ------------------------------------------------------------------

    @Slot()
    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Adicionar arquivos ao iPod", "", AUDIO_FILTER
        )
        if paths:
            self._add_files_to_ipod(paths)

    @Slot(list)
    def _add_files_to_ipod(
        self, paths: list, playlist_id: Any = _CURRENT
    ) -> None:
        """Adiciona arquivos ao iPod.

        ``playlist_id=_CURRENT`` (padrão) adiciona também à playlist
        atualmente aberta; ``None`` adiciona só à biblioteca.
        """
        if self._service is None:
            self._warn("iPod", "Conecte e carregue um iPod primeiro.")
            return
        if playlist_id is _CURRENT:
            playlist_id = self._current_playlist_id
        logger.info(
            "add_files: %d arquivo(s), playlist_id=%s",
            len(paths), playlist_id,
        )
        self._set_status(
            f"Adicionando {len(paths)} arquivo(s)…", busy=True
        )
        worker = AddFilesWorker(
            self._service,
            [str(p) for p in paths],
            ffmpeg_path=self._ffmpeg_path(),
        )
        worker.target_playlist_id = playlist_id  # lido via sender()
        worker.progress.connect(self._on_op_progress)
        worker.added.connect(self._on_files_added)
        worker.error.connect(self._on_add_files_error)
        worker.verb = "Adicionando"
        self._run_worker(worker, mutating=True)

    @Slot(str)
    def _on_add_files_error(self, err: str) -> None:
        self._warn(
            "Adicionar arquivos",
            f"Falha ao adicionar arquivos ao iPod:\n{err}",
        )

    @Slot(list)
    def _on_files_added(self, track_ids: list) -> None:
        worker = self.sender()
        pid = getattr(worker, "target_playlist_id", None)
        if pid is not None and track_ids:
            try:
                self._service.add_to_playlist(pid, track_ids)
            except Exception as exc:  # noqa: BLE001
                self._warn(
                    "Playlist",
                    f"Faixas adicionadas, mas falhou ao incluir na "
                    f"playlist:\n{exc}",
                )
        self._flash_ids = set(track_ids)   # flash verde nas linhas novas
        self._refresh_tracks()
        errs = self._service_errors()
        msg = f"{len(track_ids)} faixa(s) adicionada(s) ao iPod"
        if errs:
            msg += f"; {len(errs)} falha(s)"
            self._warn(
                "Adicionar arquivos",
                f"{msg}.\n\nMotivos:\n" + "\n".join(errs[:15]),
            )
        self._set_status(msg)
        self._mark_dirty()

    @Slot()
    def _remove_selected_tracks(self) -> None:
        if self._service is None:
            return
        ids = self._selected_track_ids()
        if not ids:
            self._set_status("Selecione faixas para remover")
            return
        answer = QMessageBox.question(
            self,
            "Remover músicas",
            f"Remover {len(ids)} música(s) do iPod?\n\n"
            "Os arquivos serão apagados do dispositivo.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._set_status(f"Removendo {len(ids)} faixa(s)…", busy=True)
        worker = RemoveTracksWorker(self._service, ids)
        worker.progress.connect(self._on_op_progress)
        worker.removed.connect(self._on_tracks_removed)
        worker.error.connect(self._on_remove_error)
        worker.verb = "Removendo"
        self._run_worker(worker, mutating=True)

    @Slot(str)
    def _on_remove_error(self, err: str) -> None:
        self._warn("Remover", f"Falha ao remover:\n{err}")

    @Slot(int, int, str)
    def _on_op_progress(self, done: int, total: int, name: str) -> None:
        """Progresso por item em add/remover/exportar ("7/25 — nome")."""
        verb = getattr(self.sender(), "verb", "Processando")
        self._set_global_progress(done, total)
        if name:
            self.status_label.setText(
                f"{verb} {done + 1}/{total} — {name}"
            )

    @Slot()
    def _on_selection_changed(self) -> None:
        n = len(self._selected_track_ids())
        self.sel_label.setText(
            f"{n} {tr('selected_count')}" if n else ""
        )

    @Slot()
    def _cancel_downloads(self) -> None:
        if self._dl_worker is not None:
            self._dl_worker.cancel()
            self.btn_cancel_dl.setEnabled(False)
            self._set_status(
                "Cancelando após a faixa atual…", busy=True
            )

    @Slot(list)
    def _on_tracks_removed(self, _ids: list) -> None:
        self._refresh_tracks()
        self._refresh_playlist_list()
        errs = self._service_errors()
        if errs:
            self._warn(
                "Remover",
                "Algumas faixas não foram removidas:\n"
                + "\n".join(errs[:15]),
            )
            self._set_status(f"Remoção concluída com {len(errs)} falha(s)")
        else:
            self._set_status("Faixas removidas")
        self._mark_dirty()

    @Slot()
    def _export_selected_tracks(self) -> None:
        if self._service is None:
            return
        ids = self._selected_track_ids()
        if not ids:
            self._set_status("Selecione faixas para exportar")
            return
        dest = QFileDialog.getExistingDirectory(
            self, "Exportar músicas para…"
        )
        if not dest:
            return
        self._set_status(f"Exportando {len(ids)} faixa(s)…", busy=True)
        worker = ExportWorker(self._service, ids, dest)
        worker.progress.connect(self._on_op_progress)
        worker.exported.connect(self._on_exported)
        worker.error.connect(self._on_export_error)
        worker.verb = "Exportando"
        self._run_worker(worker)  # leitura/cópia — não muta o service

    @Slot(list)
    def _on_exported(self, paths: list) -> None:
        dest = getattr(self.sender(), "_dest_dir", "")
        errs = self._service_errors()
        msg = f"{len(paths)} arquivo(s) exportado(s) para {dest}"
        if errs:
            msg += f"; {len(errs)} falha(s)"
            self._warn(
                "Exportar", f"{msg}.\n\nMotivos:\n" + "\n".join(errs[:15])
            )
        self._set_status(msg)

    @Slot(str)
    def _on_export_error(self, err: str) -> None:
        self._warn("Exportar", f"Falha ao exportar:\n{err}")

    # ------------------------------------------------------------------
    # Playlists
    # ------------------------------------------------------------------

    def _refresh_playlist_list(self) -> None:
        self.playlist_list.blockSignals(True)
        self.playlist_list.clear()
        lib = QListWidgetItem(tr("library"))
        lib.setData(Qt.ItemDataRole.UserRole, None)
        self.playlist_list.addItem(lib)
        for pl in self._playlists:
            if getattr(pl, "is_master", False) or getattr(pl, "is_podcast", False):
                continue
            item = QListWidgetItem(f"{pl.name} ({pl.track_count})")
            # Guarda o PlaylistInfo inteiro (id pode exceder int64).
            item.setData(Qt.ItemDataRole.UserRole, pl)
            self.playlist_list.addItem(item)
        # Reseleciona a playlist corrente, se ainda existir.
        row = 0
        if self._current_playlist_id is not None:
            for i in range(self.playlist_list.count()):
                it = self.playlist_list.item(i)
                pl = it.data(Qt.ItemDataRole.UserRole)
                if (
                    pl is not None
                    and pl.playlist_id == self._current_playlist_id
                ):
                    row = i
                    break
            else:
                self._current_playlist_id = None
        self.playlist_list.setCurrentRow(row)
        self.playlist_list.blockSignals(False)

    @Slot()
    def _on_playlist_selected(self) -> None:
        item = self.playlist_list.currentItem()
        if item is None or self._service is None:
            return
        pl = item.data(Qt.ItemDataRole.UserRole)
        self._current_playlist_id = pl.playlist_id if pl is not None else None
        self._show_current_view()

    def _show_current_view(self) -> None:
        if self._service is None:
            self._populate_table([])
            return
        pid = self._current_playlist_id
        try:
            if pid is None:
                tracks = list(self._tracks.values())
            else:
                tracks = self._service.playlist_tracks(pid)
                for t in tracks:
                    self._tracks[t.track_id] = t
        except Exception as exc:  # noqa: BLE001
            self._warn("Playlists", f"Falha ao listar a playlist:\n{exc}")
            return
        self._populate_table(tracks)

    def _refresh_tracks(self) -> None:
        """Relê faixas do service após mutações em worker (já terminado)."""
        if self._service is None:
            return
        try:
            tracks = self._service.list_tracks()
            self._tracks = {t.track_id: t for t in tracks}
            self._playlists = self._service.list_playlists()
            self._refresh_playlist_list()
        except Exception as exc:  # noqa: BLE001
            self._warn("iPod", f"Falha ao atualizar a lista:\n{exc}")
            return
        self._show_current_view()

    @Slot()
    def _create_playlist(self) -> None:
        if self._service is None:
            return
        name, ok = QInputDialog.getText(
            self, tr("new_playlist_menu"), tr("playlist_name_prompt")
        )
        name = (name or "").strip()
        if not ok or not name:
            return
        try:
            self._service.create_playlist(name)
        except Exception as exc:  # noqa: BLE001
            self._warn("Playlist", f"Falha ao criar a playlist:\n{exc}")
            return
        self._playlists = self._service.list_playlists()
        self._refresh_playlist_list()
        self._mark_dirty()
        self._set_status(f"Playlist '{name}' criada")

    def _rename_playlist(self, playlist_id: int) -> None:
        if self._service is None:
            return
        item_text = ""
        for pl in self._playlists:
            if pl.playlist_id == playlist_id:
                item_text = pl.name
        name, ok = QInputDialog.getText(
            self, "Renomear playlist", "Novo nome:", text=item_text
        )
        name = (name or "").strip()
        if not ok or not name:
            return
        try:
            self._service.rename_playlist(playlist_id, name)
            self._playlists = self._service.list_playlists()
            self._refresh_playlist_list()
        except Exception as exc:  # noqa: BLE001
            self._warn("Playlist", f"Falha ao renomear:\n{exc}")
            return
        self._mark_dirty()

    def _delete_playlist(self, playlist_id: int, name: str) -> None:
        if self._service is None:
            return
        # Músicas exclusivas desta playlist (não estão em nenhuma outra).
        try:
            member_ids = {
                t.track_id
                for t in self._service.playlist_tracks(playlist_id)
            }
            pl_map = self._service.playlists_by_track()
        except Exception:  # noqa: BLE001
            member_ids, pl_map = set(), {}
        exclusive = [
            tid for tid in member_ids
            if pl_map.get(tid, []) == [name]
        ]

        box = QMessageBox(self)
        box.setWindowTitle("Excluir playlist")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Excluir a playlist '{name}'?")
        box.setInformativeText(
            f"Ela contém {len(member_ids)} música(s).\n"
            "Sem marcar a opção abaixo, as músicas ficam no iPod, "
            "apenas sem playlist."
        )
        chk = QCheckBox(
            f"Excluir também as músicas do iPod — {len(exclusive)} "
            "exclusiva(s) desta playlist (as presentes em outras "
            "playlists são mantidas)"
        )
        chk.setChecked(False)
        chk.setEnabled(bool(member_ids))
        box.setCheckBox(chk)
        btn_del = box.addButton(
            "Excluir", QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not btn_del:
            return

        delete_tracks = chk.isChecked() and exclusive
        try:
            self._service.delete_playlist(playlist_id)
            self._playlists = self._service.list_playlists()
            if self._current_playlist_id == playlist_id:
                self._current_playlist_id = None
                self._show_current_view()
            self._refresh_playlist_list()
        except Exception as exc:  # noqa: BLE001
            self._warn("Playlist", f"Falha ao excluir:\n{exc}")
            return
        self._mark_dirty()
        self._set_status(f"Playlist '{name}' excluída")

        if delete_tracks:
            self._set_status(
                f"Removendo {len(exclusive)} música(s) exclusivas…",
                busy=True,
            )
            worker = RemoveTracksWorker(self._service, exclusive)
            worker.progress.connect(self._on_op_progress)
            worker.removed.connect(self._on_tracks_removed)
            worker.error.connect(self._on_remove_error)
            worker.verb = "Removendo"
            self._run_worker(worker, mutating=True)

    @Slot()
    def _playlist_context_menu(self, pos) -> None:  # noqa: ANN001
        if self._service is None:
            return
        item = self.playlist_list.itemAt(pos)
        menu = QMenu(self)
        act_new = menu.addAction(tr("new_playlist_menu"))
        act_rename = act_delete = None
        pid = None
        if item is not None:
            pl = item.data(Qt.ItemDataRole.UserRole)
            if pl is not None:
                pid = pl.playlist_id
            if pid is not None:
                act_rename = menu.addAction(tr("rename_playlist"))
                act_delete = menu.addAction(tr("delete_playlist"))
        chosen = menu.exec(self.playlist_list.mapToGlobal(pos))
        if chosen is act_new:
            self._create_playlist()
        elif act_rename is not None and chosen is act_rename:
            self._rename_playlist(pid)
        elif act_delete is not None and chosen is act_delete:
            self._delete_playlist(pid, item.text().rsplit(" (", 1)[0])

    @Slot()
    def _table_context_menu(self, pos) -> None:  # noqa: ANN001
        if self._service is None:
            return
        ids = self._selected_track_ids()
        menu = QMenu(self)

        submenu = menu.addMenu(tr("add_to_playlist"))
        pl_actions: list[tuple[QAction, int]] = []
        for pl in self._playlists:
            if getattr(pl, "is_master", False) or getattr(pl, "is_podcast", False):
                continue
            act = submenu.addAction(pl.name)
            pl_actions.append((act, pl.playlist_id))
        submenu.setEnabled(bool(ids and pl_actions))

        act_bulk = menu.addAction(tr("bulk_edit_menu"))
        act_bulk.setEnabled(bool(ids))

        act_remove_pl = None
        if self._current_playlist_id is not None:
            act_remove_pl = menu.addAction(tr("remove_from_playlist"))
            act_remove_pl.setEnabled(bool(ids))
            menu.addSeparator()

        act_remove = menu.addAction(tr("remove_from_ipod"))
        act_remove.setEnabled(bool(ids))
        act_export = menu.addAction(tr("export_tracks"))
        act_export.setEnabled(bool(ids))

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        for act, pid in pl_actions:
            if chosen is act:
                self._add_selection_to_playlist(pid)
                return
        if chosen is act_bulk:
            self._bulk_edit()
        elif act_remove_pl is not None and chosen is act_remove_pl:
            self._remove_selection_from_playlist()
        elif chosen is act_remove:
            self._remove_selected_tracks()
        elif chosen is act_export:
            self._export_selected_tracks()

    @Slot()
    def _bulk_edit(self) -> None:
        """Aplica os campos marcados do diálogo a todas as selecionadas."""
        if self._service is None:
            return
        ids = self._selected_track_ids()
        if not ids:
            self._set_status("Selecione faixas para editar em massa")
            return
        dlg = BulkEditDialog(len(ids), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        fields = dlg.selected_fields()
        if not fields:
            self._set_status("Nenhum campo marcado — nada a aplicar")
            return
        falhas = 0
        for tid in ids:
            try:
                self._service.update_track(tid, **fields)
            except Exception:  # noqa: BLE001
                falhas += 1
        self._refresh_tracks()
        self._mark_dirty()
        aplicadas = len(ids) - falhas
        nomes = ", ".join(sorted(fields))
        msg = f"{aplicadas} música(s) atualizadas ({nomes})"
        if falhas:
            msg += f"; {falhas} falha(s)"
        self._set_status(msg)
        logger.info("Edição em massa: %s em %d faixas", fields, aplicadas)

    def _add_selection_to_playlist(self, playlist_id: int) -> None:
        ids = self._selected_track_ids()
        if not ids or self._service is None:
            return
        try:
            self._service.add_to_playlist(playlist_id, ids)
            self._playlists = self._service.list_playlists()
            self._refresh_playlist_list()
        except Exception as exc:  # noqa: BLE001
            self._warn("Playlist", f"Falha ao adicionar à playlist:\n{exc}")
            return
        self._mark_dirty()
        self._set_status(
            f"{len(ids)} faixa(s) adicionada(s) à playlist"
        )

    def _remove_selection_from_playlist(self) -> None:
        ids = self._selected_track_ids()
        pid = self._current_playlist_id
        if not ids or pid is None or self._service is None:
            return
        try:
            self._service.remove_from_playlist(pid, ids)
            self._playlists = self._service.list_playlists()
            self._refresh_playlist_list()
            self._show_current_view()
        except Exception as exc:  # noqa: BLE001
            self._warn("Playlist", f"Falha ao remover da playlist:\n{exc}")
            return
        self._mark_dirty()

    # -- drops sobre a lista de playlists --------------------------------

    @Slot(object, list)
    def _on_tracks_dropped_on_playlist(self, pl: object, ids: list) -> None:
        """Faixas da tabela arrastadas para uma playlist."""
        if self._service is None:
            return
        pid = getattr(pl, "playlist_id", None)
        if pid is None:
            return  # soltou sobre "Biblioteca" — já estão na biblioteca
        try:
            self._service.add_to_playlist(pid, ids)
            self._playlists = self._service.list_playlists()
            self._refresh_playlist_list()
        except Exception as exc:  # noqa: BLE001
            self._warn("Playlist", f"Falha ao adicionar à playlist:\n{exc}")
            return
        self._mark_dirty()
        self._set_status(
            f"{len(ids)} faixa(s) adicionada(s) a "
            f"'{getattr(pl, 'name', '?')}'"
        )

    @Slot(object, list)
    def _on_files_dropped_on_playlist(self, pl: object, paths: list) -> None:
        """Arquivos do Explorer arrastados para uma playlist."""
        # pl=None = item "Biblioteca" ou área vazia → só a biblioteca.
        pid = getattr(pl, "playlist_id", None)
        self._add_files_to_ipod(paths, playlist_id=pid)

    # ------------------------------------------------------------------
    # YouTube Music
    # ------------------------------------------------------------------

    def _ensure_downloader(self) -> Any:
        if self._downloader is None:
            try:
                import imageio_ffmpeg

                ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "ffmpeg não encontrado (instale imageio-ffmpeg): "
                    f"{exc}"
                ) from exc
            staging = Path(self._config["staging_dir"])
            staging.mkdir(parents=True, exist_ok=True)
            self._downloader = Downloader(ffmpeg_path, str(staging))
        return self._downloader

    @Slot()
    def _start_search(self) -> None:
        query = self.search_edit.text().strip()
        if not query:
            return
        self._set_status(f"Buscando '{query}' no YouTube Music…", busy=True)
        worker = SearchWorker(
            query, client=self._yt_client, client_cls=YTMusicClient
        )
        worker.client_ready.connect(self._on_yt_client_ready)
        worker.results.connect(self._on_search_results)
        worker.error.connect(self._on_yt_error)
        worker.finished.connect(self._on_worker_finished_idle)
        self._run_worker(worker)

    @Slot(object)
    def _on_yt_client_ready(self, client: object) -> None:
        self._yt_client = client

    @Slot(list)
    def _on_search_results(self, tracks: list) -> None:
        self.search_results.clear()
        for t in tracks:
            item = QListWidgetItem(yt_track_label(t))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, t)
            self.search_results.addItem(item)
        self._set_status(f"{len(tracks)} resultado(s) encontrado(s)")
        self._update_actions()

    @Slot()
    def _fetch_playlist(self) -> None:
        url = self.playlist_url_edit.text().strip()
        if not url:
            return
        self._set_status("Carregando playlist do YouTube Music…", busy=True)
        worker = PlaylistFetchWorker(
            url, client=self._yt_client, client_cls=YTMusicClient
        )
        worker.client_ready.connect(self._on_yt_client_ready)
        worker.loaded.connect(self._on_playlist_loaded)
        worker.error.connect(self._on_yt_error)
        worker.finished.connect(self._on_worker_finished_idle)
        self._run_worker(worker)

    @Slot(str, list)
    def _on_playlist_loaded(self, name: str, tracks: list) -> None:
        self._loaded_playlist_name = name
        self.playlist_name_label.setText(f"Playlist: {name} ({len(tracks)})")
        self.playlist_tracks_list.clear()
        for t in tracks:
            item = QListWidgetItem(yt_track_label(t))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, t)
            self.playlist_tracks_list.addItem(item)
        self._set_status(
            f"Playlist '{name}': {len(tracks)} faixas carregadas"
        )
        self._update_actions()

    @Slot(str)
    def _on_yt_error(self, err: str) -> None:
        self._warn("YouTube Music", f"Falha na operação:\n{err}")

    def _checked_tracks(self, listw: QListWidget) -> list[Any]:
        out = []
        for i in range(listw.count()):
            item = listw.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                t = item.data(Qt.ItemDataRole.UserRole)
                if t is not None:
                    out.append(t)
        return out

    def _all_tracks(self, listw: QListWidget) -> list[Any]:
        out = []
        for i in range(listw.count()):
            t = listw.item(i).data(Qt.ItemDataRole.UserRole)
            if t is not None:
                out.append(t)
        return out

    @Slot()
    def _download_selected(self) -> None:
        sel_search = self._checked_tracks(self.search_results)
        sel_pl = self._checked_tracks(self.playlist_tracks_list)
        tracks = sel_search + sel_pl
        if not tracks:
            self._set_status("Marque faixas para baixar")
            return
        # Se tudo veio da playlist carregada, o iPod ganha playlist homônima.
        pl_name = (
            self._loaded_playlist_name
            if (sel_pl and not sel_search) else None
        )
        self._start_download(tracks, playlist_name=pl_name)

    @Slot()
    def _download_all(self) -> None:
        t_search = self._all_tracks(self.search_results)
        t_pl = self._all_tracks(self.playlist_tracks_list)
        tracks = t_search + t_pl
        if not tracks:
            self._set_status("Nada para baixar")
            return
        pl_name = (
            self._loaded_playlist_name
            if (t_pl and not t_search) else None
        )
        self._start_download(tracks, playlist_name=pl_name)

    @Slot()
    def _download_playlist_to_ipod(self) -> None:
        tracks = self._all_tracks(self.playlist_tracks_list)
        if not tracks:
            self._set_status("Carregue uma playlist primeiro")
            return
        if self._service is None:
            self._warn(
                "iPod",
                "Conecte e carregue um iPod para usar "
                "'Baixar playlist p/ iPod'.",
            )
            return
        name = self._loaded_playlist_name or "YouTube Music"
        self._start_download(tracks, playlist_name=name, force_ipod=True)

    def _start_download(
        self,
        tracks: list,
        playlist_name: str | None = None,
        force_ipod: bool = False,
    ) -> None:
        try:
            downloader = self._ensure_downloader()
        except RuntimeError as exc:
            self._warn("Downloads", str(exc))
            return

        to_ipod = force_ipod or (
            self.chk_to_ipod.isChecked() and self._service is not None
        )
        if (
            self.chk_to_ipod.isChecked()
            and self._service is None
            and not force_ipod
        ):
            self._set_status(
                "Sem iPod carregado — baixando apenas para a pasta de staging"
            )
        service = self._service if to_ipod else None
        if playlist_name and service is None:
            # Playlist nomeada só faz sentido indo ao iPod; sem ele, baixa
            # apenas para a pasta de downloads (sem bloquear o usuário).
            playlist_name = None

        # Fila visual: uma linha por faixa.
        self.download_queue.clear()
        self._dl_rows = []
        for t in tracks:
            item = QListWidgetItem()
            row = _QueueRow(yt_track_label(t))
            item.setSizeHint(row.sizeHint())
            self.download_queue.addItem(item)
            self.download_queue.setItemWidget(item, row)
            self._dl_rows.append(row)

        # Contexto do lote para o botão "Repetir falhadas".
        self._dl_tracks = list(tracks)
        self._dl_failed = {}
        self._dl_to_ipod = service is not None
        self._dl_playlist_name_ctx = playlist_name
        self._dl_total = len(tracks)
        self._dl_finished_count = 0
        self._dl_active = True
        self._update_actions()
        self._set_global_progress(0, self._dl_total)
        self.status_label.setText(
            f"Baixando 0/{self._dl_total} faixas…"
        )

        worker = DownloadWorker(
            downloader, tracks,
            service=service, playlist_name=playlist_name,
        )
        # Contexto extra lido no slot via sender() (lambdas NÃO podem ser
        # conectadas a signals de worker — rodariam na thread do worker).
        worker.dl_total = len(tracks)
        worker.dl_to_ipod = service is not None
        self._dl_worker = worker
        worker.progress.connect(self._on_dl_progress)
        worker.item_done.connect(self._on_dl_item_done)
        worker.item_failed.connect(self._on_dl_item_failed)
        worker.all_done.connect(self._on_dl_all_done)
        worker.error.connect(self._on_dl_error)
        worker.finished.connect(self._on_dl_finished)
        self._run_worker(worker, mutating=service is not None)

    @Slot(int, int)
    def _on_dl_progress(self, idx: int, pct: int) -> None:
        if 0 <= idx < len(self._dl_rows):
            self._dl_rows[idx].set_progress(pct)

    def _bump_dl_count(self) -> None:
        self._dl_finished_count += 1
        self._set_global_progress(self._dl_finished_count, self._dl_total)
        self.status_label.setText(
            f"Baixando {self._dl_finished_count}/{self._dl_total} faixas…"
        )

    @Slot(int, str)
    def _on_dl_item_done(self, idx: int, path: str) -> None:
        if 0 <= idx < len(self._dl_rows):
            self._dl_rows[idx].set_done(path)
        self._bump_dl_count()

    @Slot(int, str)
    def _on_dl_item_failed(self, idx: int, err: str) -> None:
        if 0 <= idx < len(self._dl_rows):
            self._dl_rows[idx].set_failed(err)
        if 0 <= idx < len(self._dl_tracks):
            self._dl_failed[idx] = self._dl_tracks[idx]
        self._bump_dl_count()

    @Slot(list)
    def _on_dl_all_done(self, paths: list) -> None:
        self._dl_active = False
        self._dl_worker = None
        worker = self.sender()
        total = getattr(worker, "dl_total", len(paths))
        to_ipod = getattr(worker, "dl_to_ipod", False)
        ok, failed = len(paths), total - len(paths)
        msg = f"Downloads concluídos: {ok} ok"
        if failed:
            msg += f", {failed} com falha — ver motivos na fila"
        if to_ipod:
            msg += " — enviados ao iPod (salve para gravar)"
            self._refresh_tracks()
            self._mark_dirty()
        self._set_status(msg)
        self._update_actions()
        if to_ipod and ok > 0:
            answer = QMessageBox.question(
                self,
                "Salvar no iPod",
                f"{ok} música(s) copiadas para o iPod.\n\n"
                "Salvar agora para que apareçam no aparelho?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._save_ipod()

    @Slot()
    def _retry_failed_downloads(self) -> None:
        """Re-baixa apenas as faixas que falharam no último lote."""
        if self._dl_active or not self._dl_failed:
            return
        tracks = [
            self._dl_tracks[i]
            for i in sorted(self._dl_failed)
            if 0 <= i < len(self._dl_tracks)
        ]
        if not tracks:
            return
        self._start_download(
            tracks,
            playlist_name=self._dl_playlist_name_ctx,
            force_ipod=self._dl_to_ipod,
        )

    @Slot()
    def _on_dl_finished(self) -> None:
        # Garantia caso o lote termine sem all_done (erro fatal no worker).
        self._dl_worker = None
        if self._dl_active:
            self._dl_active = False
            self._set_status("Downloads interrompidos")
            self._update_actions()

    @Slot(str)
    def _on_dl_error(self, err: str) -> None:
        self._warn("Downloads", err)

    # ------------------------------------------------------------------
    # Salvar / Ejetar
    # ------------------------------------------------------------------

    @Slot()
    def _save_ipod(self) -> None:
        if self._service is None:
            return
        self._set_status("Gravando iTunesDB no iPod…", busy=True)
        worker = SaveWorker(self._service)
        worker.saved.connect(self._on_saved)
        worker.error.connect(self._on_save_error)
        self._run_worker(worker, mutating=True)

    @Slot(str)
    def _on_save_error(self, err: str) -> None:
        self._warn("Salvar", f"Falha ao salvar no iPod:\n{err}")

    @Slot()
    def _on_saved(self) -> None:
        self._set_status("Alterações salvas no iPod")
        self._update_actions()
        if self._closing:
            self.close()

    @Slot()
    def _eject_ipod(self) -> None:
        if self._service is None:
            return
        do_save = True
        if getattr(self._service, "dirty", False):
            answer = QMessageBox.question(
                self,
                "Ejetar iPod",
                "Há alterações não salvas.\nSalvar antes de ejetar?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return
            do_save = answer == QMessageBox.StandardButton.Save

        if do_save:
            self._set_status("Salvando e ejetando o iPod…", busy=True)
            worker = SaveWorker(self._service, eject=True)
            worker.saved.connect(self._on_ejected)
            worker.error.connect(self._on_eject_error)
            self._run_worker(worker, mutating=True)
        else:
            # Descarta as mudanças em memória; nada foi gravado no iPod.
            self._clear_session()
            self._set_status(
                "iPod ejetado (alterações descartadas). "
                "Pode remover o dispositivo com segurança."
            )

    @Slot(str)
    def _on_eject_error(self, err: str) -> None:
        self._warn("Ejetar", f"Falha ao ejetar o iPod:\n{err}")

    @Slot()
    def _on_ejected(self) -> None:
        self._clear_session()
        QMessageBox.information(
            self,
            "Ejetar",
            "iPod ejetado com sucesso.\n"
            "Agora você pode remover o dispositivo com segurança.",
        )

    def _clear_session(self) -> None:
        self._service = None
        self._device_info = None
        self._tracks = {}
        self._playlists = []
        self._current_playlist_id = None
        self._populate_table([])
        self._refresh_playlist_list()
        self.space_label.setText(" Sem iPod ")
        self._set_status("iPod desconectado")
        self._update_actions()

    # ------------------------------------------------------------------
    # Fechamento
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closing:
            self._persist_table_state()
            event.accept()
            return

        if self._threads or self._busy:
            QMessageBox.information(
                self,
                APP_TITLE,
                tr("close_busy"),
            )
            event.ignore()
            return

        if self._service is not None and getattr(self._service, "dirty", False):
            # Sem opção de descartar: só sai salvando ou cancela o fechamento.
            answer = QMessageBox.question(
                self,
                APP_TITLE,
                tr("close_unsaved"),
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            self._closing = True
            event.ignore()
            self._save_ipod()
            return

        self._persist_table_state()
        event.accept()


def main() -> int:
    """Entry point da aplicação Qt."""
    # Log persistente em %APPDATA%\iPodManager\ipodmanager.log (rotativo).
    from logging.handlers import RotatingFileHandler

    root = logging.getLogger()
    if not any(
        isinstance(h, RotatingFileHandler) for h in root.handlers
    ):
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(
                LOG_PATH, maxBytes=1_000_000, backupCount=3,
                encoding="utf-8",
            )
            fh.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
            ))
            root.addHandler(fh)
        except OSError:
            pass
        root.setLevel(logging.INFO)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName("iPodManager")
    app.setStyleSheet(APP_STYLESHEET)
    win = MainWindow()
    win.show()
    fade_in(win)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
