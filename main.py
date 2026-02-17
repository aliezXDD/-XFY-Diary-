import html
import mimetypes
import os
import shutil
import sqlite3
import sys
import threading
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, List, Optional
from uuid import uuid4

from PyQt5.QtCore import (
    QDate,
    QFileInfo,
    QPoint,
    QSize,
    Qt,
    QTimer,
    QUrl,
    QtMsgType,
    qInstallMessageHandler,
)
from PyQt5.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCalendarWidget,
    QColorDialog,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFileIconProvider,
    QFontComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QShortcut,
    QSizePolicy,
    QSpinBox,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QTableView,
    QToolButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

SUPPRESSED_QT_LOG_PREFIXES = ("libpng warning: iCCP:",)
_qt_message_handler_ref: Optional[Callable[[QtMsgType, object, str], None]] = None
_stderr_filter_installed = False

SUPPRESSED_STDERR_SUBSTRINGS = (
    "libpng warning: iCCP:",
)


def _qt_message_handler(message_type: QtMsgType, context, message: str) -> None:
    if any(message.startswith(prefix) for prefix in SUPPRESSED_QT_LOG_PREFIXES):
        return

    level = {
        QtMsgType.QtDebugMsg: "DEBUG",
        QtMsgType.QtInfoMsg: "INFO",
        QtMsgType.QtWarningMsg: "WARNING",
        QtMsgType.QtCriticalMsg: "CRITICAL",
        QtMsgType.QtFatalMsg: "FATAL",
    }.get(message_type, "LOG")
    location = ""
    if context is not None and getattr(context, "file", None):
        location = f" ({context.file}:{context.line})"
    print(f"{level}: {message}{location}", file=sys.stderr)


def install_stderr_filter() -> None:
    global _stderr_filter_installed
    if _stderr_filter_installed:
        return

    try:
        stderr_fd = sys.stderr.fileno()
    except (AttributeError, OSError, ValueError):
        return

    try:
        original_stderr_fd = os.dup(stderr_fd)
        read_fd, write_fd = os.pipe()
        os.dup2(write_fd, stderr_fd)
        os.close(write_fd)
    except OSError:
        return

    _stderr_filter_installed = True

    def _forward_filtered_stderr() -> None:
        buffer = b""
        try:
            while True:
                chunk = os.read(read_fd, 4096)
                if not chunk:
                    break

                buffer += chunk
                while b"\n" in buffer:
                    raw_line, buffer = buffer.split(b"\n", 1)
                    line = raw_line.decode("utf-8", errors="replace")
                    if any(token in line for token in SUPPRESSED_STDERR_SUBSTRINGS):
                        continue
                    os.write(original_stderr_fd, raw_line + b"\n")

            if buffer:
                line = buffer.decode("utf-8", errors="replace")
                if not any(token in line for token in SUPPRESSED_STDERR_SUBSTRINGS):
                    os.write(original_stderr_fd, buffer)
        except OSError:
            return
        finally:
            for fd in (read_fd, original_stderr_fd):
                try:
                    os.close(fd)
                except OSError:
                    pass

    thread = threading.Thread(
        target=_forward_filtered_stderr,
        name="stderr-filter",
        daemon=True,
    )
    thread.start()


def install_qt_message_filter() -> None:
    global _qt_message_handler_ref
    if _qt_message_handler_ref is not None:
        return
    _qt_message_handler_ref = _qt_message_handler
    qInstallMessageHandler(_qt_message_handler_ref)


install_stderr_filter()
install_qt_message_filter()

from qfluentwidgets import (
    BodyLabel,
    FluentWindow,
    NavigationItemPosition,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    SubtitleLabel,
    Theme,
    setFontFamilies,
    setTheme,
    themeColor,
)


APP_NAME = "XFY diary"
WINDOW_TITLE = "XFY 日记"
DB_NAME = "diary.db"
ICON_NAME = "logo_done.png"
ATTACHMENTS_DIR = "attachments"
OVERVIEW_NAV_TEXT = "概览"
DIARY_NAV_TEXT = "日记"
OVERVIEW_NAV_ICON_TEXT = "S"
DIARY_NAV_ICON_TEXT = "D"
ON_THIS_DAY_POPUP_META_KEY = "on_this_day_popup_last_checked_date"
UNTITLED_ENTRY_TITLE = "未命名日记"
DATA_DIR_ENV_VARS = ("XFY_DIARY_DATA_DIR",)
IMAGE_FILE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
}
VIDEO_FILE_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".m4v"}
AUDIO_FILE_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma"}
WORD_FILE_EXTENSIONS = {".doc", ".docx", ".wps", ".rtf", ".odt"}
TEXT_FILE_EXTENSIONS = {".txt", ".md", ".log", ".csv"}
ATTACHMENT_FILE_FILTER = (
    "常用附件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff *.heic *.heif "
    "*.mp4 *.mov *.avi *.mkv *.wmv *.webm *.m4v "
    "*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.wma "
    "*.pdf *.doc *.docx *.wps *.rtf *.odt "
    "*.txt *.md *.log *.csv);;"
    "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff *.heic *.heif);;"
    "视频文件 (*.mp4 *.mov *.avi *.mkv *.wmv *.webm *.m4v);;"
    "音频文件 (*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.wma);;"
    "文档文件 (*.pdf *.doc *.docx *.wps *.rtf *.odt *.txt *.md *.log *.csv);;"
    "所有文件 (*.*)"
)


ICON_TINT_COLOR = QColor("#C8B5FF")
STYLE_ICON_FILES = (
    "icons/chevron-up-light.svg",
    "icons/chevron-up-dark.svg",
    "icons/chevron-down-light.svg",
    "icons/chevron-down-dark.svg",
)
PREFERRED_UI_FONTS = (
    "汉仪中黑",
    "汉仪中黑 197",
    "HYZhongHei",
)
FALLBACK_CJK_UI_FONTS = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
)
PREFERRED_EDITOR_FONTS = (
    "宋体",
    "SimSun",
)
DEFAULT_EDITOR_FONT_SIZE = 14
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_ROOT = get_app_root()


def get_data_root() -> Path:
    for env_name in DATA_DIR_ENV_VARS:
        custom_dir = os.getenv(env_name, "").strip()
        if custom_dir:
            return Path(custom_dir).expanduser().resolve()

    if sys.platform.startswith("win"):
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg_data_home = os.getenv("XDG_DATA_HOME", "").strip()
        base = Path(xdg_data_home).expanduser() if xdg_data_home else Path.home() / ".local" / "share"
    return (base / APP_NAME).resolve()


def is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    probe_path = path / f".xfy_write_test_{uuid4().hex}"
    try:
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink()
    except OSError:
        return False
    return True


def copy_missing_tree(source_dir: Path, target_dir: Path) -> None:
    if not source_dir.exists():
        return
    for path in source_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source_dir)
        destination = target_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            continue
        shutil.copy2(path, destination)


def normalize_attachment_paths(db_path: Path, legacy_root: Path, data_root: Path) -> None:
    if not db_path.exists():
        return

    legacy_attachments_root = legacy_root / ATTACHMENTS_DIR
    data_attachments_root = data_root / ATTACHMENTS_DIR

    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error:
        return

    updates: list[tuple[str, int]] = []
    try:
        rows = conn.execute("SELECT id, file_path FROM attachments").fetchall()
    except sqlite3.Error:
        conn.close()
        return

    for attachment_id, raw_path in rows:
        if not raw_path:
            continue
        original = str(raw_path)
        stored_path = Path(original)
        normalized: Optional[str] = None

        if stored_path.is_absolute():
            relative: Optional[Path] = None
            for root in (data_attachments_root, legacy_attachments_root):
                try:
                    relative = stored_path.resolve().relative_to(root.resolve())
                except (OSError, ValueError):
                    continue
                break

            if relative is None:
                by_name = data_attachments_root / stored_path.name
                if by_name.exists():
                    relative = Path(stored_path.name)

            if relative is not None:
                normalized = (Path(ATTACHMENTS_DIR) / relative).as_posix()
        else:
            as_relative = Path(original)
            if as_relative.parts and as_relative.parts[0] == ATTACHMENTS_DIR:
                normalized = as_relative.as_posix()
            elif (data_attachments_root / as_relative).exists():
                normalized = (Path(ATTACHMENTS_DIR) / as_relative).as_posix()
            else:
                normalized = as_relative.as_posix()

        if normalized and normalized != original:
            updates.append((normalized, int(attachment_id)))

    if updates:
        conn.executemany("UPDATE attachments SET file_path = ? WHERE id = ?", updates)
        conn.commit()
    conn.close()


def prepare_data_root() -> Path:
    preferred_root = get_data_root()
    emergency_root = (Path.home() / ".xfy_diary").resolve()
    candidates = [preferred_root]
    if preferred_root != APP_ROOT:
        candidates.append(APP_ROOT)
    if emergency_root not in candidates:
        candidates.append(emergency_root)

    for data_root in candidates:
        if not is_writable_directory(data_root):
            continue

        try:
            same_root = data_root.resolve() == APP_ROOT.resolve()
        except OSError:
            same_root = False

        if not same_root:
            legacy_db_path = APP_ROOT / DB_NAME
            target_db_path = data_root / DB_NAME
            if legacy_db_path.exists() and not target_db_path.exists():
                shutil.copy2(legacy_db_path, target_db_path)

            copy_missing_tree(APP_ROOT / ATTACHMENTS_DIR, data_root / ATTACHMENTS_DIR)
            normalize_attachment_paths(target_db_path, APP_ROOT, data_root)

        return data_root

    return APP_ROOT


DATA_ROOT = prepare_data_root()


def resolve_resource_path(relative_path: str) -> Optional[Path]:
    search_roots = [APP_ROOT]
    if hasattr(sys, "_MEIPASS"):
        search_roots.append(Path(getattr(sys, "_MEIPASS")))

    seen: set[Path] = set()
    for root in search_roots:
        try:
            normalized_root = root.resolve()
        except OSError:
            continue
        if normalized_root in seen:
            continue
        seen.add(normalized_root)
        candidate = normalized_root / relative_path
        if candidate.exists():
            return candidate
    return None


def resolve_qss_icons(style: str) -> str:
    resolved_style = style
    for relative_path in STYLE_ICON_FILES:
        resolved_icon_path = resolve_resource_path(relative_path)
        if resolved_icon_path is None:
            continue
        # QSS + SVG loader on Windows can treat "file:/D:/..." as a relative path.
        # Use an absolute filesystem path directly to avoid malformed "cwd/file:/..." lookups.
        icon_path = resolved_icon_path.as_posix()
        resolved_style = resolved_style.replace(f"url({relative_path})", f'url("{icon_path}")')
    return resolved_style


def resolve_ui_font_family() -> str:
    return resolve_ui_font_families()[0]


def resolve_editor_font_family() -> str:
    families = QFontDatabase().families()
    lowered = {name.casefold(): name for name in families}
    for preferred in PREFERRED_EDITOR_FONTS:
        matched = lowered.get(preferred.casefold())
        if matched:
            return matched
    return resolve_ui_font_family()


def resolve_ui_font_families() -> List[str]:
    families = QFontDatabase().families()
    lowered = {name.casefold(): name for name in families}
    resolved: List[str] = []
    seen: set[str] = set()

    def add_family(name: str) -> None:
        key = name.casefold()
        if key in seen:
            return
        seen.add(key)
        resolved.append(name)

    for preferred in PREFERRED_UI_FONTS:
        matched = lowered.get(preferred.casefold())
        if matched:
            add_family(matched)

    for name in families:
        if "汉仪中黑" in name:
            add_family(name)

    for fallback in FALLBACK_CJK_UI_FONTS:
        matched = lowered.get(fallback.casefold())
        if matched:
            add_family(matched)

    add_family("Segoe UI")
    return resolved


def strip_problematic_png_profile(image_bytes: bytes) -> bytes:
    if not image_bytes.startswith(PNG_SIGNATURE):
        return image_bytes

    cursor = len(PNG_SIGNATURE)
    sanitized_chunks = [PNG_SIGNATURE]
    removed_profile = False

    while cursor + 8 <= len(image_bytes):
        length = int.from_bytes(image_bytes[cursor : cursor + 4], "big")
        chunk_end = cursor + 12 + length
        if chunk_end > len(image_bytes):
            return image_bytes

        chunk_type = image_bytes[cursor + 4 : cursor + 8]
        if chunk_type != b"iCCP":
            sanitized_chunks.append(image_bytes[cursor:chunk_end])
        else:
            removed_profile = True

        cursor = chunk_end
        if chunk_type == b"IEND":
            break

    if not removed_profile:
        return image_bytes
    return b"".join(sanitized_chunks)


def load_image_bytes(path: Path) -> Optional[bytes]:
    try:
        raw = path.read_bytes()
    except OSError:
        return None

    if path.suffix.lower() == ".png":
        return strip_problematic_png_profile(raw)
    return raw


def load_qimage(path: Path) -> QImage:
    image_bytes = load_image_bytes(path)
    if image_bytes is not None:
        image = QImage()
        if image.loadFromData(image_bytes):
            return image
    return QImage(str(path))


def load_qpixmap(path: Path) -> QPixmap:
    image_bytes = load_image_bytes(path)
    if image_bytes is not None:
        pixmap = QPixmap()
        if pixmap.loadFromData(image_bytes):
            return pixmap
    return QPixmap(str(path))


LIGHT_APP_STYLE = """
QWidget {
    background-color: #F5F6F8;
    color: #1E2430;
    font-family: "汉仪中黑", "汉仪中黑 197", "HYZhongHei", "Segoe UI", "SF Pro Text", "Inter";
    font-size: 14px;
}
QLabel#heading {
    font-size: 25px;
    font-weight: 600;
    color: #1A1E27;
}
QLabel#subheading {
    color: #6A7282;
}
QFrame#leftPanel, QFrame#editorPanel, QFrame#dashboardCard, QFrame#memoryCard {
    background: #FFFFFF;
    border: 1px solid #E7EBF1;
    border-radius: 16px;
}
QFrame#filteredEntriesCard, QFrame#entryEditorCard, QFrame#attachedFilesCard {
    background: #FDFEFF;
    border: 1px solid #E4E8EF;
    border-radius: 14px;
}
QLineEdit, QDateEdit, QFontComboBox, QSpinBox, QTextEdit, QListWidget {
    background: #FFFFFF;
    border: 1px solid #E4E8EF;
    border-radius: 10px;
    padding: 6px 8px;
}
QSpinBox#fontSizeSpin {
    min-width: 82px;
    padding-right: 30px;
}
QSpinBox#fontSizeSpin::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid #E4E8EF;
    border-top-right-radius: 10px;
    background: #F7F9FC;
}
QSpinBox#fontSizeSpin::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 22px;
    border-left: 1px solid #E4E8EF;
    border-top: 1px solid #E4E8EF;
    border-bottom-right-radius: 10px;
    background: #F7F9FC;
}
QSpinBox#fontSizeSpin::up-button:hover, QSpinBox#fontSizeSpin::down-button:hover {
    background: #EDF3FF;
}
QSpinBox#fontSizeSpin::up-button:pressed, QSpinBox#fontSizeSpin::down-button:pressed {
    background: #E4ECFA;
}
QSpinBox#fontSizeSpin::up-arrow {
    image: url(icons/chevron-up-light.svg);
    width: 10px;
    height: 6px;
}
QSpinBox#fontSizeSpin::down-arrow {
    image: url(icons/chevron-down-light.svg);
    width: 10px;
    height: 6px;
}
QTextEdit#entryEditor, QListWidget#filteredEntriesList, QListWidget#attachmentFilesList {
    background: transparent;
    border: none;
}
QComboBox, QDateEdit, QFontComboBox {
    padding-right: 28px;
}
QComboBox::drop-down, QDateEdit::drop-down, QFontComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border: none;
    border-left: 1px solid #E4E8EF;
    border-top-right-radius: 10px;
    border-bottom-right-radius: 10px;
    background: #F7F9FC;
}
QComboBox::down-arrow, QDateEdit::down-arrow, QFontComboBox::down-arrow {
    image: url(icons/chevron-down-light.svg);
    width: 12px;
    height: 8px;
}
QComboBox::down-arrow:on, QDateEdit::down-arrow:on, QFontComboBox::down-arrow:on {
    top: 1px;
}
QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {
    background: #FFFFFF;
    border: 1px solid #E4E8EF;
    border-radius: 10px;
    padding: 4px;
    selection-background-color: #E9EEFA;
    selection-color: #203B74;
    outline: 0px;
}
QComboBox QAbstractItemView::item, QFontComboBox QAbstractItemView::item {
    padding: 7px 10px;
    margin: 1px 0px;
    border-radius: 7px;
}
QMenu {
    background: #FFFFFF;
    border: 1px solid #E4E8EF;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 12px;
    margin: 1px 4px;
    border-radius: 7px;
}
QMenu::item:selected {
    background: #E9EEFA;
    color: #203B74;
}
QMenu::separator {
    height: 1px;
    margin: 6px 10px;
    background: #E4E8EF;
}
QTextEdit {
    padding: 10px;
}
QListWidget::item {
    border-radius: 9px;
    margin: 2px 0px;
    padding: 8px 10px;
}
QListWidget::item:selected {
    background: #E9EEFA;
    color: #203B74;
}
QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 6px 3px 6px 3px;
}
QScrollBar::handle:vertical {
    background: #C9D2E2;
    border-radius: 6px;
    min-height: 42px;
}
QScrollBar::handle:vertical:hover {
    background: #B3C0D8;
}
QScrollBar::handle:vertical:pressed {
    background: #9FAECC;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
    width: 0px;
    background: transparent;
    border: none;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 12px;
    margin: 3px 6px 3px 6px;
}
QScrollBar::handle:horizontal {
    background: #C9D2E2;
    border-radius: 6px;
    min-width: 42px;
}
QScrollBar::handle:horizontal:hover {
    background: #B3C0D8;
}
QScrollBar::handle:horizontal:pressed {
    background: #9FAECC;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
    height: 0px;
    background: transparent;
    border: none;
}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
}
AcrylicWindow {
    background: transparent;
}
"""


DARK_APP_STYLE = """
QWidget {
    background-color: #121722;
    color: #E8ECF5;
    font-family: "汉仪中黑", "汉仪中黑 197", "HYZhongHei", "Segoe UI", "SF Pro Text", "Inter";
    font-size: 14px;
}
QLabel#heading {
    font-size: 25px;
    font-weight: 600;
    color: #F2F5FF;
}
QLabel#subheading {
    color: #A7B1C6;
}
QFrame#leftPanel, QFrame#editorPanel, QFrame#dashboardCard, QFrame#memoryCard {
    background: #1A2230;
    border: 1px solid #343E53;
    border-radius: 16px;
}
QFrame#filteredEntriesCard, QFrame#entryEditorCard, QFrame#attachedFilesCard {
    background: #161E2C;
    border: 1px solid #3A465C;
    border-radius: 14px;
}
QLineEdit, QDateEdit, QFontComboBox, QSpinBox, QTextEdit, QListWidget {
    background: #141B27;
    border: 1px solid #3A465C;
    border-radius: 10px;
    padding: 6px 8px;
    color: #E8ECF5;
}
QSpinBox#fontSizeSpin {
    min-width: 82px;
    padding-right: 30px;
}
QSpinBox#fontSizeSpin::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid #3A465C;
    border-top-right-radius: 10px;
    background: #1B2432;
}
QSpinBox#fontSizeSpin::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 22px;
    border-left: 1px solid #3A465C;
    border-top: 1px solid #3A465C;
    border-bottom-right-radius: 10px;
    background: #1B2432;
}
QSpinBox#fontSizeSpin::up-button:hover, QSpinBox#fontSizeSpin::down-button:hover {
    background: #2D3D55;
}
QSpinBox#fontSizeSpin::up-button:pressed, QSpinBox#fontSizeSpin::down-button:pressed {
    background: #354766;
}
QSpinBox#fontSizeSpin::up-arrow {
    image: url(icons/chevron-up-dark.svg);
    width: 10px;
    height: 6px;
}
QSpinBox#fontSizeSpin::down-arrow {
    image: url(icons/chevron-down-dark.svg);
    width: 10px;
    height: 6px;
}
QTextEdit#entryEditor, QListWidget#filteredEntriesList, QListWidget#attachmentFilesList {
    background: transparent;
    border: none;
}
QComboBox, QDateEdit, QFontComboBox {
    padding-right: 28px;
}
QComboBox::drop-down, QDateEdit::drop-down, QFontComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border: none;
    border-left: 1px solid #3A465C;
    border-top-right-radius: 10px;
    border-bottom-right-radius: 10px;
    background: #1B2432;
}
QComboBox::down-arrow, QDateEdit::down-arrow, QFontComboBox::down-arrow {
    image: url(icons/chevron-down-dark.svg);
    width: 12px;
    height: 8px;
}
QComboBox::down-arrow:on, QDateEdit::down-arrow:on, QFontComboBox::down-arrow:on {
    top: 1px;
}
QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {
    background: #182130;
    border: 1px solid #3A465C;
    border-radius: 10px;
    padding: 4px;
    selection-background-color: #41537B;
    selection-color: #F4F7FF;
    outline: 0px;
}
QComboBox QAbstractItemView::item, QFontComboBox QAbstractItemView::item {
    padding: 7px 10px;
    margin: 1px 0px;
    border-radius: 7px;
}
QMenu {
    background: #182130;
    border: 1px solid #3A465C;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 12px;
    margin: 1px 4px;
    border-radius: 7px;
    color: #E8ECF5;
}
QMenu::item:selected {
    background: #41537B;
    color: #F4F7FF;
}
QMenu::separator {
    height: 1px;
    margin: 6px 10px;
    background: #3A465C;
}
QTextEdit {
    padding: 10px;
}
QListWidget::item {
    border-radius: 9px;
    margin: 2px 0px;
    padding: 8px 10px;
}
QListWidget::item:selected {
    background: #3A476D;
    color: #EFF3FF;
}
QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 6px 3px 6px 3px;
}
QScrollBar::handle:vertical {
    background: #4C5D7D;
    border-radius: 6px;
    min-height: 42px;
}
QScrollBar::handle:vertical:hover {
    background: #61749A;
}
QScrollBar::handle:vertical:pressed {
    background: #6E82A8;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
    width: 0px;
    background: transparent;
    border: none;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 12px;
    margin: 3px 6px 3px 6px;
}
QScrollBar::handle:horizontal {
    background: #4C5D7D;
    border-radius: 6px;
    min-width: 42px;
}
QScrollBar::handle:horizontal:hover {
    background: #61749A;
}
QScrollBar::handle:horizontal:pressed {
    background: #6E82A8;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
    height: 0px;
    background: transparent;
    border: none;
}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
}
AcrylicWindow {
    background: transparent;
}
"""


MEMORY_BROWSER_LIGHT_STYLE = (
    "QTextBrowser { border: 1px solid #E4E8EF; border-radius: 10px; "
    "padding: 8px; background: #FFFFFF; }"
)
MEMORY_BROWSER_DARK_STYLE = (
    "QTextBrowser { border: 1px solid #3A465C; border-radius: 10px; "
    "padding: 8px; background: #141B27; color: #E8ECF5; }"
)
ELEGANT_DIALOG_LIGHT_STYLE = """
QDialog#elegantMessageDialog {
    background: transparent;
}
QFrame#dialogCard {
    background: #FFFFFF;
    border: 1px solid #E7EBF1;
    border-radius: 16px;
}
QFrame#dialogHeader {
    background: transparent;
    border: none;
}
QLabel#dialogTitle {
    background: transparent;
    color: #1A1E27;
    font-size: 20px;
    font-weight: 600;
}
QLabel#dialogMessage {
    background: transparent;
    color: #5E6678;
}
QToolButton#dialogCloseButton {
    background: transparent;
    border: none;
    border-radius: 12px;
    min-width: 24px;
    min-height: 24px;
    color: #6A7282;
    font-size: 14px;
    font-weight: 600;
}
QToolButton#dialogCloseButton:hover {
    background: #EEF3FC;
    color: #2B3446;
}
QToolButton#dialogCloseButton:pressed {
    background: #E3EAF7;
}
"""
ELEGANT_DIALOG_DARK_STYLE = """
QDialog#elegantMessageDialog {
    background: transparent;
}
QFrame#dialogCard {
    background: #1A2230;
    border: 1px solid #3A465C;
    border-radius: 16px;
}
QFrame#dialogHeader {
    background: transparent;
    border: none;
}
QLabel#dialogTitle {
    background: transparent;
    color: #F2F5FF;
    font-size: 20px;
    font-weight: 600;
}
QLabel#dialogMessage {
    background: transparent;
    color: #A7B1C6;
}
QToolButton#dialogCloseButton {
    background: transparent;
    border: none;
    border-radius: 12px;
    min-width: 24px;
    min-height: 24px;
    color: #A7B1C6;
    font-size: 14px;
    font-weight: 600;
}
QToolButton#dialogCloseButton:hover {
    background: #2B3548;
    color: #E8ECF5;
}
QToolButton#dialogCloseButton:pressed {
    background: #35425A;
}
"""

CALENDAR_LIGHT_STYLE = """
QCalendarWidget#entryCalendar {
    background: #FFFFFF;
    border: 1px solid #E4E8EF;
    border-radius: 12px;
}
QCalendarWidget#entryCalendar QWidget#qt_calendar_navigationbar {
    background: #F4F7FE;
    border-bottom: 1px solid #E4E8EF;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}
QCalendarWidget#entryCalendar QToolButton {
    color: #2A3445;
    border: none;
    background: transparent;
    padding: 4px 6px;
    margin: 2px;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_monthbutton,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_yearbutton {
    min-width: 86px;
    border: 1px solid #D8E2F2;
    border-radius: 8px;
    background: #FFFFFF;
    color: #2A3445;
    font-weight: 600;
    padding: 2px 20px 2px 10px;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_monthbutton::menu-indicator,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_yearbutton::menu-indicator {
    image: url(icons/chevron-down-light.svg);
    subcontrol-origin: padding;
    subcontrol-position: center right;
    right: 8px;
    width: 10px;
    height: 6px;
}
QCalendarWidget#entryCalendar QToolButton:hover {
    background: #E7EEFC;
    border-radius: 6px;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_monthbutton:hover,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_yearbutton:hover {
    border: 1px solid #C8D8F2;
    background: #EDF3FF;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_monthbutton:pressed,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_yearbutton:pressed {
    background: #E4ECFA;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_prevmonth,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_nextmonth {
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    padding: 0px;
    margin: 4px;
    border-radius: 12px;
    border: 1px solid #D8E2F2;
    background: #FFFFFF;
    color: #50617D;
    font-size: 14px;
    font-weight: 600;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_nextmonth:hover {
    background: #EDF3FF;
    border: 1px solid #C8D8F2;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_prevmonth:pressed,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_nextmonth:pressed {
    background: #E4ECFA;
}
QCalendarWidget#entryCalendar QSpinBox {
    border: none;
    background: transparent;
    color: #2A3445;
}
QCalendarWidget#entryCalendar QAbstractItemView:enabled {
    background: #FFFFFF;
    color: #1E2430;
    selection-background-color: #DCE8FF;
    selection-color: #1E3A78;
    border: none;
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
}
"""

CALENDAR_DARK_STYLE = """
QCalendarWidget#entryCalendar {
    background: #141B27;
    border: 1px solid #3A465C;
    border-radius: 12px;
}
QCalendarWidget#entryCalendar QWidget#qt_calendar_navigationbar {
    background: #1B2432;
    border-bottom: 1px solid #3A465C;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}
QCalendarWidget#entryCalendar QToolButton {
    color: #EAF0FF;
    border: none;
    background: transparent;
    padding: 4px 6px;
    margin: 2px;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_monthbutton,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_yearbutton {
    min-width: 86px;
    border: 1px solid #495772;
    border-radius: 8px;
    background: #243246;
    color: #EAF0FF;
    font-weight: 600;
    padding: 2px 20px 2px 10px;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_monthbutton::menu-indicator,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_yearbutton::menu-indicator {
    image: url(icons/chevron-down-dark.svg);
    subcontrol-origin: padding;
    subcontrol-position: center right;
    right: 8px;
    width: 10px;
    height: 6px;
}
QCalendarWidget#entryCalendar QToolButton:hover {
    background: #36415A;
    border-radius: 6px;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_monthbutton:hover,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_yearbutton:hover {
    border: 1px solid #5A6C8A;
    background: #2D3D55;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_monthbutton:pressed,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_yearbutton:pressed {
    background: #354766;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_prevmonth,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_nextmonth {
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    padding: 0px;
    margin: 4px;
    border-radius: 12px;
    border: 1px solid #495772;
    background: #243246;
    color: #EAF0FF;
    font-size: 14px;
    font-weight: 600;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_nextmonth:hover {
    background: #2D3D55;
    border: 1px solid #5A6C8A;
}
QCalendarWidget#entryCalendar QToolButton#qt_calendar_prevmonth:pressed,
QCalendarWidget#entryCalendar QToolButton#qt_calendar_nextmonth:pressed {
    background: #354766;
}
QCalendarWidget#entryCalendar QSpinBox {
    border: none;
    background: transparent;
    color: #EAF0FF;
}
QCalendarWidget#entryCalendar QAbstractItemView:enabled {
    background: #141B27;
    color: #E8ECF5;
    selection-background-color: #41537B;
    selection-color: #F4F7FF;
    border: none;
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
}
QCalendarWidget#entryCalendar QTableView QHeaderView::section {
    background: #141B27;
    color: #E8ECF5;
    border: none;
    padding: 4px 0px;
}
"""


DATE_POPUP_LIGHT_STYLE = """
QCalendarWidget#datePopupCalendar {
    background: #FFFFFF;
    border: 1px solid #DDE4F2;
    border-radius: 12px;
}
QCalendarWidget#datePopupCalendar QWidget#qt_calendar_navigationbar {
    background: #F6F8FD;
    border-bottom: 1px solid #E6ECF7;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}
QCalendarWidget#datePopupCalendar QToolButton {
    color: #324156;
    border: none;
    background: transparent;
    padding: 4px 6px;
}
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_monthbutton,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_yearbutton {
    border: 1px solid #D6E0F0;
    border-radius: 8px;
    background: #FFFFFF;
    color: #2A3445;
    font-weight: 600;
    padding: 2px 18px 2px 10px;
}
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_monthbutton::menu-indicator,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_yearbutton::menu-indicator {
    image: url(icons/chevron-down-light.svg);
    subcontrol-origin: padding;
    subcontrol-position: center right;
    right: 7px;
    width: 10px;
    height: 6px;
}
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_prevmonth,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_nextmonth {
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
    border-radius: 11px;
    border: 1px solid #D6E0F0;
    background: #FFFFFF;
    color: #5A6E8E;
    font-size: 13px;
    font-weight: 600;
}
QCalendarWidget#datePopupCalendar QToolButton:hover {
    background: #ECF3FF;
}
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_monthbutton:hover,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_yearbutton:hover,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_nextmonth:hover {
    border: 1px solid #C8D7F0;
}
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_monthbutton:pressed,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_yearbutton:pressed,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_prevmonth:pressed,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_nextmonth:pressed {
    background: #E5EEFF;
}
QCalendarWidget#datePopupCalendar QAbstractItemView:enabled {
    background: #FFFFFF;
    color: #1E2430;
    selection-background-color: #DCE8FF;
    selection-color: #1E3A78;
    border: none;
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
}
"""

DATE_POPUP_DARK_STYLE = """
QCalendarWidget#datePopupCalendar {
    background: #151D2A;
    border: 1px solid #3A4760;
    border-radius: 12px;
}
QCalendarWidget#datePopupCalendar QWidget#qt_calendar_navigationbar {
    background: #1C2636;
    border-bottom: 1px solid #3A4760;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}
QCalendarWidget#datePopupCalendar QToolButton {
    color: #E6ECFA;
    border: none;
    background: transparent;
    padding: 4px 6px;
}
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_monthbutton,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_yearbutton {
    border: 1px solid #4C5C78;
    border-radius: 8px;
    background: #233146;
    color: #ECF2FF;
    font-weight: 600;
    padding: 2px 18px 2px 10px;
}
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_monthbutton::menu-indicator,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_yearbutton::menu-indicator {
    image: url(icons/chevron-down-dark.svg);
    subcontrol-origin: padding;
    subcontrol-position: center right;
    right: 7px;
    width: 10px;
    height: 6px;
}
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_prevmonth,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_nextmonth {
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
    border-radius: 11px;
    border: 1px solid #4C5C78;
    background: #233146;
    color: #DCE6FA;
    font-size: 13px;
    font-weight: 600;
}
QCalendarWidget#datePopupCalendar QToolButton:hover {
    background: #2F3E57;
}
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_monthbutton:hover,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_yearbutton:hover,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_nextmonth:hover {
    border: 1px solid #62759A;
}
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_monthbutton:pressed,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_yearbutton:pressed,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_prevmonth:pressed,
QCalendarWidget#datePopupCalendar QToolButton#qt_calendar_nextmonth:pressed {
    background: #384A68;
}
QCalendarWidget#datePopupCalendar QAbstractItemView:enabled {
    background: #151D2A;
    color: #E8ECF5;
    selection-background-color: #41537B;
    selection-color: #F4F7FF;
    border: none;
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
}
QCalendarWidget#datePopupCalendar QTableView QHeaderView::section {
    background: #151D2A;
    color: #E8ECF5;
    border: none;
    padding: 4px 0px;
}
"""

LIGHT_APP_STYLE = resolve_qss_icons(LIGHT_APP_STYLE)
DARK_APP_STYLE = resolve_qss_icons(DARK_APP_STYLE)
CALENDAR_LIGHT_STYLE = resolve_qss_icons(CALENDAR_LIGHT_STYLE)
CALENDAR_DARK_STYLE = resolve_qss_icons(CALENDAR_DARK_STYLE)
DATE_POPUP_LIGHT_STYLE = resolve_qss_icons(DATE_POPUP_LIGHT_STYLE)
DATE_POPUP_DARK_STYLE = resolve_qss_icons(DATE_POPUP_DARK_STYLE)


def add_soft_shadow(widget: QWidget) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(30)
    effect.setOffset(0, 8)
    effect.setColor(QColor(24, 31, 45, 30))
    widget.setGraphicsEffect(effect)


class ElegantMessageDialog(QDialog):
    def __init__(
        self,
        parent: Optional[QWidget],
        title: str,
        message: str,
        is_dark: bool,
        confirm_text: str = "知道了",
        cancel_text: Optional[str] = None,
        close_result: int = QDialog.Rejected,
        bind_enter_to_confirm: bool = False,
    ):
        super().__init__(parent)
        self._drag_offset: Optional[QPoint] = None
        self.setObjectName("elegantMessageDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        card = QFrame()
        card.setObjectName("dialogCard")
        add_soft_shadow(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("dialogHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("dialogTitle")
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)

        close_button = QToolButton()
        close_button.setObjectName("dialogCloseButton")
        close_button.setText("×")
        close_button.setCursor(Qt.PointingHandCursor)
        close_button.setToolTip("关闭")
        close_button.clicked.connect(lambda: self.done(close_result))
        header_layout.addWidget(close_button)
        card_layout.addWidget(header)

        message_label = QLabel(message)
        message_label.setObjectName("dialogMessage")
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card_layout.addWidget(message_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        if cancel_text:
            cancel_button = PushButton(cancel_text)
            cancel_button.clicked.connect(self.reject)
            button_row.addWidget(cancel_button)

        confirm_button = PrimaryPushButton(confirm_text)
        confirm_button.clicked.connect(self.accept)
        if bind_enter_to_confirm:
            confirm_button.setAutoDefault(True)
            confirm_button.setDefault(True)
            self._return_shortcut = QShortcut(QKeySequence("Return"), self)
            self._return_shortcut.setContext(Qt.WindowShortcut)
            self._return_shortcut.activated.connect(self.accept)
            self._enter_shortcut = QShortcut(QKeySequence("Enter"), self)
            self._enter_shortcut.setContext(Qt.WindowShortcut)
            self._enter_shortcut.activated.connect(self.accept)
        confirm_button.setFocus()
        button_row.addWidget(confirm_button)
        card_layout.addLayout(button_row)

        root.addWidget(card)
        self.setStyleSheet(ELEGANT_DIALOG_DARK_STYLE if is_dark else ELEGANT_DIALOG_LIGHT_STYLE)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        center_dialog_on_parent(self, self.parentWidget())

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPos() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._drag_offset = None
        super().mouseReleaseEvent(event)


def _resolve_dark_mode(parent: Optional[QWidget]) -> bool:
    node = parent
    while node is not None:
        is_dark = getattr(node, "is_dark", None)
        if isinstance(is_dark, bool):
            return is_dark
        node = node.parentWidget()
    return False


def center_dialog_on_parent(dialog: QDialog, parent: Optional[QWidget]) -> None:
    if parent is None:
        return
    anchor = parent.window() or parent
    if not anchor.isVisible():
        return
    dialog.adjustSize()
    dialog.move(anchor.frameGeometry().center() - dialog.rect().center())


def show_info_popup(parent: Optional[QWidget], title: str, message: str) -> None:
    dialog = ElegantMessageDialog(
        parent=parent,
        title=title,
        message=message,
        is_dark=_resolve_dark_mode(parent),
        confirm_text="知道了",
    )
    dialog.exec()


def show_warning_popup(parent: Optional[QWidget], title: str, message: str) -> None:
    dialog = ElegantMessageDialog(
        parent=parent,
        title=title,
        message=message,
        is_dark=_resolve_dark_mode(parent),
        confirm_text="明白了",
    )
    dialog.exec()


def ask_confirmation_popup(
    parent: Optional[QWidget],
    title: str,
    message: str,
    confirm_text: str = "确定",
    cancel_text: str = "取消",
    bind_enter_to_confirm: bool = False,
) -> bool:
    dialog = ElegantMessageDialog(
        parent=parent,
        title=title,
        message=message,
        is_dark=_resolve_dark_mode(parent),
        confirm_text=confirm_text,
        cancel_text=cancel_text,
        bind_enter_to_confirm=bind_enter_to_confirm,
    )
    return dialog.exec() == QDialog.Accepted


def ask_confirmation_popup_with_result(
    parent: Optional[QWidget],
    title: str,
    message: str,
    confirm_text: str = "确定",
    cancel_text: str = "取消",
    close_result: int = QDialog.Rejected,
    bind_enter_to_confirm: bool = False,
) -> int:
    dialog = ElegantMessageDialog(
        parent=parent,
        title=title,
        message=message,
        is_dark=_resolve_dark_mode(parent),
        confirm_text=confirm_text,
        cancel_text=cancel_text,
        close_result=close_result,
        bind_enter_to_confirm=bind_enter_to_confirm,
    )
    return dialog.exec()


def is_image_file(path: Path) -> bool:
    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.startswith("image/"):
        return True
    return path.suffix.lower() in IMAGE_FILE_EXTENSIONS


def normalize_path_for_compare(path: Path) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    return os.path.normcase(str(resolved))


@dataclass
class AttachmentDraft:
    file_name: str
    file_path: str
    is_image: int


class DiaryDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL,
                title TEXT NOT NULL,
                content_html TEXT NOT NULL,
                content_text TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                is_image INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(entry_date);
            CREATE INDEX IF NOT EXISTS idx_entries_updated ON entries(updated_at);
            """
        )
        self.conn.commit()

    def list_entries(self, search_text: str = "") -> list[sqlite3.Row]:
        query = search_text.strip()
        like = f"%{query}%"
        cur = self.conn.execute(
            """
            SELECT id, entry_date, title, updated_at
            FROM entries
            WHERE (? = '' OR entry_date LIKE ? OR title LIKE ? OR content_text LIKE ?)
            ORDER BY entry_date DESC, updated_at DESC
            """,
            (query, like, like, like),
        )
        return cur.fetchall()

    def list_entry_dates(self) -> list[str]:
        cur = self.conn.execute(
            """
            SELECT DISTINCT entry_date
            FROM entries
            ORDER BY entry_date
            """
        )
        return [str(row["entry_date"]) for row in cur.fetchall()]

    def get_entry(self, entry_id: int) -> Optional[sqlite3.Row]:
        cur = self.conn.execute(
            """
            SELECT id, entry_date, title, content_html, content_text, updated_at
            FROM entries
            WHERE id = ?
            """,
            (entry_id,),
        )
        return cur.fetchone()

    def title_exists(self, title: str) -> bool:
        cur = self.conn.execute(
            """
            SELECT 1
            FROM entries
            WHERE title = ?
            LIMIT 1
            """,
            (title,),
        )
        return cur.fetchone() is not None

    def save_entry(
        self,
        entry_id: Optional[int],
        entry_date: str,
        title: str,
        content_html: str,
        content_text: str,
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        if entry_id is None:
            cur = self.conn.execute(
                """
                INSERT INTO entries(entry_date, title, content_html, content_text, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (entry_date, title, content_html, content_text, now),
            )
            self.conn.commit()
            return int(cur.lastrowid)

        self.conn.execute(
            """
            UPDATE entries
            SET entry_date = ?, title = ?, content_html = ?, content_text = ?, updated_at = ?
            WHERE id = ?
            """,
            (entry_date, title, content_html, content_text, now, entry_id),
        )
        self.conn.commit()
        return entry_id

    def delete_entry(self, entry_id: int) -> list[str]:
        cur = self.conn.execute(
            """
            SELECT file_path
            FROM attachments
            WHERE entry_id = ?
            """,
            (entry_id,),
        )
        attachment_paths = [str(row["file_path"]) for row in cur.fetchall()]
        self.conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        self.conn.commit()
        return attachment_paths

    def add_attachment(self, entry_id: int, file_name: str, file_path: str, is_image: int) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            INSERT INTO attachments(entry_id, file_name, file_path, is_image, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entry_id, file_name, file_path, is_image, now),
        )
        self.conn.commit()

    def list_attachments(self, entry_id: int) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            """
            SELECT id, file_name, file_path, is_image
            FROM attachments
            WHERE entry_id = ?
            ORDER BY id DESC
            """,
            (entry_id,),
        )
        return cur.fetchall()

    def delete_attachment(self, attachment_id: int) -> Optional[str]:
        cur = self.conn.execute(
            """
            SELECT file_path
            FROM attachments
            WHERE id = ?
            """,
            (attachment_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        self.conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        self.conn.commit()
        return str(row["file_path"])

    def has_attachment_path(self, file_path: str) -> bool:
        cur = self.conn.execute(
            """
            SELECT 1
            FROM attachments
            WHERE file_path = ?
            LIMIT 1
            """,
            (file_path,),
        )
        return cur.fetchone() is not None

    def total_entries(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) AS count FROM entries")
        row = cur.fetchone()
        return int(row["count"]) if row else 0

    def get_meta(self, key: str) -> Optional[str]:
        cur = self.conn.execute(
            """
            SELECT value
            FROM app_meta
            WHERE key = ?
            """,
            (key,),
        )
        row = cur.fetchone()
        return str(row["value"]) if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO app_meta(key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.conn.commit()

    def get_on_this_day_memories(self, today: date) -> list[sqlite3.Row]:
        month_day = today.strftime("%m-%d")
        cur = self.conn.execute(
            """
            SELECT id, entry_date, title, content_text
            FROM entries
            WHERE strftime('%m-%d', entry_date) = ?
              AND CAST(strftime('%Y', entry_date) AS INTEGER) < ?
            ORDER BY entry_date DESC
            """,
            (month_day, today.year),
        )
        return cur.fetchall()

    def close(self) -> None:
        self.conn.close()


class DashboardPage(QWidget):
    def __init__(self, on_entry_open_requested: Optional[Callable[[int], None]] = None):
        super().__init__()
        self.setObjectName("dashboardPage")
        self.is_dark = False
        self.on_entry_open_requested = on_entry_open_requested

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        self.title = QLabel("概览")
        self.title.setObjectName("heading")
        root.addWidget(self.title)

        self.subtitle = QLabel("一个安静、简洁、数据仅保存在本地的日记空间。")
        self.subtitle.setObjectName("subheading")
        root.addWidget(self.subtitle)

        self.stats_card = QFrame()
        self.stats_card.setObjectName("dashboardCard")
        add_soft_shadow(self.stats_card)
        stats_layout = QVBoxLayout(self.stats_card)
        stats_layout.setContentsMargins(18, 16, 18, 16)
        stats_layout.setSpacing(6)
        stats_title = SubtitleLabel("记录统计")
        self.stats_value = BodyLabel("本地 SQLite 已保存 0 条记录。")
        stats_layout.addWidget(stats_title)
        stats_layout.addWidget(self.stats_value)
        root.addWidget(self.stats_card)

        self.memory_card = QFrame()
        self.memory_card.setObjectName("memoryCard")
        add_soft_shadow(self.memory_card)
        memory_layout = QVBoxLayout(self.memory_card)
        memory_layout.setContentsMargins(18, 16, 18, 16)
        memory_layout.setSpacing(10)
        memory_title = SubtitleLabel("今日回忆")
        self.memory_browser = QTextBrowser()
        self.memory_browser.setReadOnly(True)
        self.memory_browser.setOpenExternalLinks(False)
        self.memory_browser.setOpenLinks(False)
        self.memory_browser.anchorClicked.connect(self.handle_memory_link_clicked)
        self.memory_browser.setMinimumHeight(280)
        self.memory_browser.setStyleSheet(MEMORY_BROWSER_LIGHT_STYLE)
        memory_layout.addWidget(memory_title)
        memory_layout.addWidget(self.memory_browser)
        root.addWidget(self.memory_card, 1)

    def apply_theme(self, is_dark: bool) -> None:
        self.is_dark = is_dark
        self.memory_browser.setStyleSheet(
            MEMORY_BROWSER_DARK_STYLE if is_dark else MEMORY_BROWSER_LIGHT_STYLE
        )

    def update_content(self, total_entries: int, memories: list[sqlite3.Row]) -> None:
        self.stats_value.setText(f"本地 SQLite（{DB_NAME}）已保存 {total_entries} 条记录。")
        empty_color = "#AAB4C8" if self.is_dark else "#5F6778"
        heading_color = "#EEF2FF" if self.is_dark else "#1D2534"
        snippet_color = "#C4CDE0" if self.is_dark else "#5D6575"
        border_color = "#3B4660" if self.is_dark else "#E8ECF3"
        link_color = "#8CB8FF" if self.is_dark else "#2457C5"

        if not memories:
            self.memory_browser.setHtml(
                f"<p style='color:{empty_color};'>这一天还没有往年回忆。</p>"
            )
            return

        chunks: List[str] = [
            f"<h3 style='margin-top:0px; color:{heading_color};'>这一天的往年回忆</h3>"
        ]
        for row in memories:
            snippet = html.escape((row["content_text"] or "").strip())
            if len(snippet) > 180:
                snippet = snippet[:180] + "..."
            entry_id = int(row["id"])
            chunks.append(
                (
                    f"<div style='margin-bottom:12px; padding:10px; border:1px solid {border_color}; "
                    "border-radius:10px;'>"
                    f"<a href='entry:{entry_id}' style='color:{link_color};'>"
                    f"{html.escape(row['entry_date'])} - {html.escape(row['title'])}</a><br/>"
                    f"<span style='color:{snippet_color};'>{snippet or '暂无文字预览。'}</span>"
                    "</div>"
                )
            )
        self.memory_browser.setHtml("".join(chunks))

    def handle_memory_link_clicked(self, link: QUrl) -> None:
        if link.scheme() != "entry":
            return
        try:
            entry_id = int(link.path().lstrip("/"))
        except ValueError:
            return
        if self.on_entry_open_requested:
            self.on_entry_open_requested(entry_id)


class CalendarWeekendHeaderDelegate(QStyledItemDelegate):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.is_dark = False

    def set_dark_mode(self, is_dark: bool) -> None:
        self.is_dark = is_dark

    @staticmethod
    def _is_weekend_column(index) -> bool:
        header_text = str(index.model().index(0, index.column()).data(Qt.DisplayRole) or "")
        return header_text in {"周六", "周日", "Sat", "Sun", "Saturday", "Sunday"}

    def paint(self, painter, option, index) -> None:
        styled_option = QStyleOptionViewItem(option)
        if self.is_dark and index.row() == 0 and self._is_weekend_column(index):
            painter.save()
            painter.fillRect(styled_option.rect, QColor("#29F1FF"))
            painter.setPen(QColor("#000000"))
            painter.setFont(styled_option.font)
            painter.drawText(
                styled_option.rect,
                int(Qt.AlignCenter),
                str(index.data(Qt.DisplayRole) or ""),
            )
            painter.restore()
            return

        super().paint(painter, styled_option, index)


class DiaryPage(QWidget):
    def __init__(
        self,
        db: DiaryDatabase,
        data_root: Path,
        attachments_dir: Path,
        on_saved: Optional[Callable[[], None]] = None,
        on_toggle_theme: Optional[Callable[[], None]] = None,
    ):
        super().__init__()
        self.setObjectName("diaryPage")
        self.db = db
        self.data_root = data_root.resolve()
        self.attachments_dir = attachments_dir
        self.file_icon_provider = QFileIconProvider()
        self.on_saved = on_saved
        self.on_toggle_theme = on_toggle_theme
        self.current_entry_id: Optional[int] = None
        self.pending_attachments: list[AttachmentDraft] = []
        self._saved_entry_date = QDate.currentDate().toString("yyyy-MM-dd")
        self._saved_title = ""
        self._saved_content_html = ""
        self.is_dark = False
        self.marked_date_strings: set[str] = set()
        self.default_editor_font_family = resolve_editor_font_family()
        self.default_editor_font_size = DEFAULT_EDITOR_FONT_SIZE
        self.weekend_header_delegates: dict[str, CalendarWeekendHeaderDelegate] = {}
        self.weekend_header_delegate_view_ids: dict[str, int] = {}
        self._build_ui()
        self.refresh_entry_list()
        self.ensure_unsaved_draft_if_no_entries()

    def to_stored_attachment_path(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self.data_root)
        except ValueError:
            return str(resolved)
        return relative.as_posix()

    def resolve_attachment_path(self, stored_path: str) -> Path:
        path = Path(stored_path)
        if path.is_absolute():
            absolute = path.resolve()
            if absolute.exists():
                return absolute
            remapped = self._remap_legacy_attachment_path(absolute)
            return remapped if remapped.exists() else absolute

        normalized = Path(stored_path)
        if normalized.parts and normalized.parts[0] == ATTACHMENTS_DIR:
            return (self.data_root / normalized).resolve()
        return (self.attachments_dir / normalized).resolve()

    def _remap_legacy_attachment_path(self, legacy_path: Path) -> Path:
        lower_parts = [part.lower() for part in legacy_path.parts]
        if ATTACHMENTS_DIR.lower() in lower_parts:
            index = len(lower_parts) - 1 - lower_parts[::-1].index(ATTACHMENTS_DIR.lower())
            trailing = legacy_path.parts[index + 1 :]
            if trailing:
                remapped = (self.attachments_dir / Path(*trailing)).resolve()
                if remapped.exists():
                    return remapped

        by_name = (self.attachments_dir / legacy_path.name).resolve()
        return by_name

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        left_panel = QFrame()
        left_panel.setObjectName("leftPanel")
        left_panel.setFixedWidth(390)
        add_soft_shadow(left_panel)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(10)

        panel_title = SubtitleLabel("记录")
        self.search_bar = SearchLineEdit()
        self.search_bar.setPlaceholderText("按日期或关键词搜索")
        self.search_bar.textChanged.connect(self.on_search_changed)

        self.new_button = PrimaryPushButton("新建")
        self.new_button.clicked.connect(
            lambda _checked=False: self.new_entry(auto_save_unsaved=True, auto_create_entry=True)
        )

        calendar_header = QHBoxLayout()
        calendar_header.setContentsMargins(0, 0, 0, 0)
        calendar_header.setSpacing(8)

        calendar_label = BodyLabel("日历")
        calendar_label.setObjectName("subheading")
        self.clear_date_filter_button = PushButton("清除")
        self.clear_date_filter_button.setFixedSize(64, 28)
        self.clear_date_filter_button.clicked.connect(self.clear_date_filter)

        calendar_header.addWidget(calendar_label)
        calendar_header.addStretch(1)
        calendar_header.addWidget(self.clear_date_filter_button)

        self.calendar_widget = QCalendarWidget()
        self.calendar_widget.setObjectName("entryCalendar")
        self.calendar_widget.setAttribute(Qt.WA_StyledBackground, True)
        self.calendar_widget.setGridVisible(True)
        self.calendar_widget.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar_widget.setMaximumHeight(260)
        self.calendar_widget.clicked.connect(self.show_entries_for_calendar_date)

        self.calendar_tip = QLabel("点击日期可快速筛选当天记录。")
        self.calendar_tip.setObjectName("subheading")
        self.calendar_tip.setWordWrap(True)

        self.entry_list = QListWidget()
        self.entry_list.setObjectName("filteredEntriesList")
        self.entry_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.entry_list.setSelectionRectVisible(True)
        self.entry_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.entry_list.itemSelectionChanged.connect(self.load_selected_entry)
        filtered_entries_card = QFrame()
        filtered_entries_card.setObjectName("filteredEntriesCard")
        filtered_entries_layout = QVBoxLayout(filtered_entries_card)
        filtered_entries_layout.setContentsMargins(10, 10, 10, 10)
        filtered_entries_layout.setSpacing(0)
        filtered_entries_layout.addWidget(self.entry_list)

        left_layout.addWidget(panel_title)
        left_layout.addWidget(self.search_bar)
        left_layout.addWidget(self.new_button)
        left_layout.addLayout(calendar_header)
        left_layout.addWidget(self.calendar_widget)
        left_layout.addWidget(self.calendar_tip)
        left_layout.addWidget(filtered_entries_card, 1)

        editor_panel = QFrame()
        editor_panel.setObjectName("editorPanel")
        add_soft_shadow(editor_panel)
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(18, 18, 18, 18)
        editor_layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.date_popup_calendar = QCalendarWidget()
        self.date_popup_calendar.setObjectName("datePopupCalendar")
        self.date_popup_calendar.setAttribute(Qt.WA_StyledBackground, True)
        self.date_popup_calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.date_popup_calendar.setGridVisible(False)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setCalendarWidget(self.date_popup_calendar)
        self.date_edit.setFixedWidth(150)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("标题（可留空）")
        self.title_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.attach_button = PushButton("添加附件")
        self.attach_button.clicked.connect(self.attach_file)
        self.save_button = PrimaryPushButton("保存")
        self.save_button.clicked.connect(self.save_current_entry)
        self.delete_button = PushButton("删除")
        self.delete_button.clicked.connect(self.delete_current_entry)
        self.theme_button = PushButton("深色模式")
        self.theme_button.clicked.connect(self.handle_theme_toggle)

        top_row.addWidget(self.date_edit)
        top_row.addWidget(self.title_edit, 1)
        top_row.addWidget(self.attach_button)
        top_row.addWidget(self.save_button)
        top_row.addWidget(self.delete_button)
        top_row.addWidget(self.theme_button)
        editor_layout.addLayout(top_row)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.font_combo = QFontComboBox()
        self.font_combo.currentFontChanged.connect(
            lambda font: self.apply_font_family(font.family())
        )

        self.size_spin = QSpinBox()
        self.size_spin.setObjectName("fontSizeSpin")
        self.size_spin.setRange(8, 72)
        self.size_spin.setValue(self.default_editor_font_size)
        self.size_spin.setAlignment(Qt.AlignCenter)
        self.size_spin.valueChanged.connect(self.apply_font_size)

        self.color_button = PushButton("文字颜色")
        self.color_button.clicked.connect(self.pick_text_color)

        toolbar.addWidget(self.font_combo)
        toolbar.addWidget(self.size_spin)
        toolbar.addWidget(self.color_button)
        toolbar.addStretch(1)
        editor_layout.addLayout(toolbar)

        self.editor = QTextEdit()
        self.editor.setObjectName("entryEditor")
        self.editor.setPlaceholderText("写下今天的心情与故事...")
        self.configure_editor_shortcuts()
        self.editor.currentCharFormatChanged.connect(self.sync_format_controls)
        self.apply_editor_defaults()
        editor_text_card = QFrame()
        editor_text_card.setObjectName("entryEditorCard")
        editor_text_layout = QVBoxLayout(editor_text_card)
        editor_text_layout.setContentsMargins(10, 10, 10, 10)
        editor_text_layout.setSpacing(0)
        editor_text_layout.addWidget(self.editor)
        editor_layout.addWidget(editor_text_card, 1)

        attachment_heading = QLabel("附件")
        attachment_heading.setObjectName("subheading")
        self.delete_attachment_button = PushButton("删除所选附件")
        self.delete_attachment_button.clicked.connect(self.delete_selected_attachment)

        attachment_row = QHBoxLayout()
        attachment_row.addWidget(attachment_heading)
        attachment_row.addStretch(1)
        attachment_row.addWidget(self.delete_attachment_button)

        self.attachment_list = QListWidget()
        self.attachment_list.setObjectName("attachmentFilesList")
        self.attachment_list.setViewMode(QListWidget.IconMode)
        self.attachment_list.setMovement(QListWidget.Static)
        self.attachment_list.setIconSize(QSize(120, 120))
        self.attachment_list.setGridSize(QSize(170, 175))
        self.attachment_list.setResizeMode(QListWidget.Adjust)
        self.attachment_list.setWordWrap(True)
        self.attachment_list.setSpacing(8)
        self.attachment_list.setMaximumHeight(280)
        self.attachment_list.itemDoubleClicked.connect(self.open_attachment)
        attachments_card = QFrame()
        attachments_card.setObjectName("attachedFilesCard")
        attachments_layout = QVBoxLayout(attachments_card)
        attachments_layout.setContentsMargins(10, 10, 10, 10)
        attachments_layout.setSpacing(8)
        attachments_layout.addLayout(attachment_row)
        attachments_layout.addWidget(self.attachment_list)
        editor_layout.addWidget(attachments_card)

        root.addWidget(left_panel)
        root.addWidget(editor_panel, 1)
        self.configure_action_shortcuts()
        self.apply_calendar_style()
        self.update_calendar_filter_state()

    def apply_editor_defaults(self) -> None:
        default_font = QFont(self.default_editor_font_family, self.default_editor_font_size)
        self.editor.document().setDefaultFont(default_font)

        default_format = QTextCharFormat()
        default_format.setFontFamily(self.default_editor_font_family)
        default_format.setFontPointSize(float(self.default_editor_font_size))
        self.editor.setCurrentCharFormat(default_format)

        self.font_combo.blockSignals(True)
        self.font_combo.setCurrentFont(default_font)
        self.font_combo.blockSignals(False)

        self.size_spin.blockSignals(True)
        self.size_spin.setValue(self.default_editor_font_size)
        self.size_spin.blockSignals(False)

    def configure_editor_shortcuts(self) -> None:
        shortcut_bindings = (
            ("Ctrl+B", self.toggle_bold, "bold_shortcut"),
            ("Ctrl+I", self.toggle_italic, "italic_shortcut"),
            ("Ctrl+U", self.toggle_underline, "underline_shortcut"),
        )
        for sequence, handler, attribute_name in shortcut_bindings:
            shortcut = QShortcut(QKeySequence(sequence), self.editor)
            shortcut.setContext(Qt.WidgetShortcut)
            shortcut.activated.connect(handler)
            setattr(self, attribute_name, shortcut)

    def configure_action_shortcuts(self) -> None:
        self.save_shortcut = QShortcut(QKeySequence.Save, self)
        self.save_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.save_shortcut.activated.connect(self.save_button.click)

        self.delete_entry_shortcut = QShortcut(QKeySequence("Delete"), self.entry_list)
        self.delete_entry_shortcut.setContext(Qt.WidgetShortcut)
        self.delete_entry_shortcut.activated.connect(self.delete_button.click)

    def handle_theme_toggle(self) -> None:
        if self.on_toggle_theme:
            self.on_toggle_theme()

    def set_theme_state(self, is_dark: bool) -> None:
        self.is_dark = is_dark
        self.theme_button.setText("浅色模式" if is_dark else "深色模式")
        self.apply_calendar_style()
        self.update_calendar_filter_state()
        self.refresh_calendar_marks()

    def on_search_changed(self, _text: str) -> None:
        self.refresh_entry_list()
        self.update_calendar_filter_state()

    def clear_date_filter(self) -> None:
        self.search_bar.clear()
        self.calendar_widget.setSelectedDate(self.date_edit.date())

    def show_entries_for_calendar_date(self, selected_date: QDate) -> None:
        self.date_edit.setDate(selected_date)
        self.search_bar.setText(selected_date.toString("yyyy-MM-dd"))
        if self.entry_list.count() > 0:
            self.entry_list.setCurrentRow(0)

    def apply_calendar_style(self) -> None:
        self.calendar_widget.setStyleSheet(CALENDAR_DARK_STYLE if self.is_dark else CALENDAR_LIGHT_STYLE)
        self.date_popup_calendar.setStyleSheet(
            DATE_POPUP_DARK_STYLE if self.is_dark else DATE_POPUP_LIGHT_STYLE
        )
        header_format = QTextCharFormat()
        if self.is_dark:
            header_format.setForeground(QColor("#0F1E3D"))
            header_format.setBackground(QColor("#29F1FF"))
        self.calendar_widget.setHeaderTextFormat(header_format)
        self.date_popup_calendar.setHeaderTextFormat(header_format)
        weekend_format = QTextCharFormat()
        if self.is_dark:
            weekend_format.setForeground(QColor("#E8ECF5"))
        for calendar in (self.calendar_widget, self.date_popup_calendar):
            calendar.setWeekdayTextFormat(Qt.Saturday, weekend_format)
            calendar.setWeekdayTextFormat(Qt.Sunday, weekend_format)
            self.apply_weekend_header_delegate(calendar)
            QTimer.singleShot(
                0, lambda cal=calendar: self.apply_weekend_header_delegate(cal, retry_count=4)
            )
        self.configure_calendar_navigation_buttons(self.calendar_widget)
        self.configure_calendar_navigation_buttons(self.date_popup_calendar)

    def apply_weekend_header_delegate(
        self, calendar: QCalendarWidget, retry_count: int = 0
    ) -> None:
        calendar_view = calendar.findChild(QTableView, "qt_calendar_calendarview")
        if not calendar_view:
            if retry_count > 0:
                QTimer.singleShot(
                    0,
                    lambda cal=calendar, retries=retry_count - 1: self.apply_weekend_header_delegate(
                        cal, retry_count=retries
                    ),
                )
            return

        calendar_key = calendar.objectName() or str(id(calendar))
        delegate = self.weekend_header_delegates.get(calendar_key)
        current_view_id = id(calendar_view)

        if (
            delegate is None
            or self.weekend_header_delegate_view_ids.get(calendar_key) != current_view_id
        ):
            delegate = CalendarWeekendHeaderDelegate(calendar_view)
            self.weekend_header_delegates[calendar_key] = delegate
            self.weekend_header_delegate_view_ids[calendar_key] = current_view_id

        if calendar_view.itemDelegate() is not delegate:
            calendar_view.setItemDelegate(delegate)

        delegate.set_dark_mode(self.is_dark)
        calendar_view.viewport().update()

    def configure_calendar_navigation_buttons(self, calendar: QCalendarWidget) -> None:
        for object_name, symbol in (("qt_calendar_prevmonth", "‹"), ("qt_calendar_nextmonth", "›")):
            button = calendar.findChild(QToolButton, object_name)
            if not button:
                continue
            button.setArrowType(Qt.NoArrow)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setIcon(QIcon())
            button.setText(symbol)
            button.setCursor(Qt.PointingHandCursor)

        for object_name in ("qt_calendar_monthbutton", "qt_calendar_yearbutton"):
            button = calendar.findChild(QToolButton, object_name)
            if button:
                button.setCursor(Qt.PointingHandCursor)

    def update_calendar_filter_state(self) -> None:
        filter_text = self.search_bar.text().strip()
        filter_date = QDate.fromString(filter_text, "yyyy-MM-dd")
        has_date_filter = filter_date.isValid() and filter_date.toString("yyyy-MM-dd") == filter_text

        self.clear_date_filter_button.setEnabled(has_date_filter)
        if has_date_filter:
            self.calendar_tip.setText(f"正在筛选 {filter_text} 的记录。")
            return
        self.calendar_tip.setText("点击日期可快速筛选当天记录。")

    def calendar_mark_format(self) -> QTextCharFormat:
        fmt = QTextCharFormat()
        if self.is_dark:
            fmt.setBackground(QColor("#43557E"))
            fmt.setForeground(QColor("#F2F5FF"))
        else:
            fmt.setBackground(QColor("#D9E6FF"))
            fmt.setForeground(QColor("#1E3A78"))
        fmt.setFontWeight(600)
        return fmt

    def refresh_calendar_marks(self) -> None:
        for date_text in self.marked_date_strings:
            marked_date = QDate.fromString(date_text, "yyyy-MM-dd")
            if marked_date.isValid():
                self.calendar_widget.setDateTextFormat(marked_date, QTextCharFormat())

        self.marked_date_strings.clear()
        marked_format = self.calendar_mark_format()
        for date_text in self.db.list_entry_dates():
            marked_date = QDate.fromString(date_text, "yyyy-MM-dd")
            if not marked_date.isValid():
                continue
            self.calendar_widget.setDateTextFormat(marked_date, marked_format)
            self.marked_date_strings.add(date_text)

    def refresh_entry_list(self) -> None:
        rows = self.db.list_entries(self.search_bar.text())
        self.entry_list.blockSignals(True)
        self.entry_list.clear()
        selected_item: Optional[QListWidgetItem] = None
        for row in rows:
            title = str(row["title"]).strip() or UNTITLED_ENTRY_TITLE
            item = QListWidgetItem(f"{row['entry_date']}  |  {title}")
            item.setData(Qt.UserRole, row["id"])
            self.entry_list.addItem(item)
            if row["id"] == self.current_entry_id:
                selected_item = item
        if selected_item:
            self.entry_list.setCurrentItem(selected_item)
        self.entry_list.blockSignals(False)
        self.refresh_calendar_marks()

    def ensure_unsaved_draft_if_no_entries(self) -> None:
        if self.db.total_entries() > 0:
            return
        self.new_entry(auto_save_unsaved=False)

    def select_first_entry_if_available(self) -> bool:
        if self.entry_list.count() <= 0:
            return False
        self.entry_list.blockSignals(True)
        self.entry_list.setCurrentRow(0)
        self.entry_list.blockSignals(False)
        self.load_selected_entry()
        return True

    def _reset_change_tracking(self) -> None:
        self._saved_entry_date = self.date_edit.date().toString("yyyy-MM-dd")
        self._saved_title = self.title_edit.text().strip()
        self._saved_content_html = self.editor.toHtml().strip()
        self.editor.document().setModified(False)

    def _has_meaningful_draft(self) -> bool:
        if self.pending_attachments:
            return True
        if self.title_edit.text().strip():
            return True
        if self.editor.toPlainText().strip():
            return True
        return self.date_edit.date().toString("yyyy-MM-dd") != self._saved_entry_date

    def has_unsaved_changes(self) -> bool:
        if self.current_entry_id is None:
            return self._has_meaningful_draft()
        if self.pending_attachments:
            return True
        if self.editor.document().isModified():
            return True
        if self.date_edit.date().toString("yyyy-MM-dd") != self._saved_entry_date:
            return True
        return self.title_edit.text().strip() != self._saved_title

    def _save_unsaved_changes_if_needed(self) -> None:
        if self.has_unsaved_changes():
            self.save_current_entry(show_notice=False)

    def _select_entry_item_by_id(self, entry_id: int) -> bool:
        for index in range(self.entry_list.count()):
            item = self.entry_list.item(index)
            if int(item.data(Qt.UserRole)) != entry_id:
                continue
            self.entry_list.blockSignals(True)
            self.entry_list.setCurrentItem(item)
            self.entry_list.blockSignals(False)
            return True
        return False

    def is_managed_attachment_path(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to(self.attachments_dir.resolve())
        except OSError:
            return False

    def open_entry_by_id(self, entry_id: int) -> bool:
        row = self.db.get_entry(entry_id)
        if not row:
            return False

        self.search_bar.blockSignals(True)
        self.search_bar.clear()
        self.search_bar.blockSignals(False)
        self.update_calendar_filter_state()

        self._save_unsaved_changes_if_needed()
        self.refresh_entry_list()
        if not self._select_entry_item_by_id(entry_id):
            return False
        self.load_selected_entry()
        return True

    def new_entry(self, auto_save_unsaved: bool = True, auto_create_entry: bool = False) -> None:
        if auto_save_unsaved:
            self._save_unsaved_changes_if_needed()
        if auto_create_entry:
            self.search_bar.blockSignals(True)
            self.search_bar.clear()
            self.search_bar.blockSignals(False)
            self.update_calendar_filter_state()
            self.create_blank_entry(keep_editor_unchanged=True)
            return

        self.current_entry_id = None
        self.pending_attachments.clear()
        today = QDate.currentDate()
        self.date_edit.setDate(today)
        self.calendar_widget.setSelectedDate(today)
        self.title_edit.clear()
        self.editor.clear()
        self.apply_editor_defaults()
        self.entry_list.clearSelection()
        self.refresh_attachment_list()
        self._reset_change_tracking()

    def create_blank_entry(self, keep_editor_unchanged: bool = False) -> None:
        entry_date = QDate.currentDate().toString("yyyy-MM-dd")
        saved_id = self.db.save_entry(
            None,
            entry_date,
            "",
            "",
            "",
        )
        if keep_editor_unchanged:
            self.refresh_entry_list()
            if self.on_saved:
                self.on_saved()
            return

        self.current_entry_id = saved_id
        self.title_edit.clear()
        self.refresh_entry_list()
        self._select_entry_item_by_id(saved_id)
        self.refresh_attachment_list()
        self._reset_change_tracking()

        if self.on_saved:
            self.on_saved()

    def load_selected_entry(self) -> None:
        if len(self.entry_list.selectedItems()) > 1:
            return
        item = self.entry_list.currentItem()
        if not item:
            return
        entry_id = item.data(Qt.UserRole)
        if entry_id is None:
            return
        target_entry_id = int(entry_id)

        if target_entry_id != self.current_entry_id and self.has_unsaved_changes():
            if self.current_entry_id is not None:
                self.save_current_entry(show_notice=False)
                self.refresh_entry_list()
                if not self._select_entry_item_by_id(target_entry_id):
                    return
            else:
                # Avoid creating a new entry when switching from an unsaved draft.
                self.pending_attachments.clear()

        row = self.db.get_entry(target_entry_id)
        if not row:
            return

        self.current_entry_id = int(row["id"])
        loaded_date = QDate.fromString(row["entry_date"], "yyyy-MM-dd")
        self.date_edit.setDate(loaded_date if loaded_date.isValid() else QDate.currentDate())
        if loaded_date.isValid():
            self.calendar_widget.setSelectedDate(loaded_date)
        self.title_edit.setText(row["title"])
        self.editor.setHtml(row["content_html"])
        self.sync_format_controls()
        self.pending_attachments.clear()
        self.refresh_attachment_list()
        self._reset_change_tracking()

    def save_current_entry(self, show_notice: bool = True, force_new: bool = False) -> None:
        if self.current_entry_id is None and not force_new:
            selected_items = self.entry_list.selectedItems()
            if len(selected_items) == 1:
                selected_id = selected_items[0].data(Qt.UserRole)
                if selected_id is not None and self.db.get_entry(int(selected_id)):
                    self.current_entry_id = int(selected_id)
            elif len(selected_items) > 1:
                show_warning_popup(self, "保存失败", "当前选中了多条记录，请先只选择一条再保存。")
                return

        content_html = self.editor.toHtml().strip()
        content_text = self.editor.toPlainText().strip()
        title = self.title_edit.text().strip()

        if self.current_entry_id is None and not force_new:
            if not title and not content_text and not self.pending_attachments:
                show_info_popup(self, "无需保存", "当前没有可保存内容。")
                return

        if not title:
            fallback = content_text[:40].strip()
            title = f"{fallback}..." if len(content_text) > 40 else fallback
            title = title or UNTITLED_ENTRY_TITLE

        entry_date = self.date_edit.date().toString("yyyy-MM-dd")
        saved_id = self.db.save_entry(
            None if force_new else self.current_entry_id,
            entry_date,
            title,
            content_html,
            content_text,
        )

        for attachment in self.pending_attachments:
            stored_path = self.to_stored_attachment_path(Path(attachment.file_path))
            self.db.add_attachment(
                saved_id,
                attachment.file_name,
                stored_path,
                attachment.is_image,
            )

        self.pending_attachments.clear()
        self.current_entry_id = saved_id
        self.title_edit.setText(title)
        self.refresh_entry_list()
        self.refresh_attachment_list()
        self._reset_change_tracking()

        if self.on_saved:
            self.on_saved()

        if show_notice:
            show_info_popup(self, "已保存", "日记已保存。")

    def delete_current_entry(self) -> None:
        selected_entry_ids: list[int] = []
        seen_entry_ids: set[int] = set()
        for item in self.entry_list.selectedItems():
            raw_entry_id = item.data(Qt.UserRole)
            if raw_entry_id is None:
                continue
            entry_id = int(raw_entry_id)
            if entry_id in seen_entry_ids:
                continue
            seen_entry_ids.add(entry_id)
            selected_entry_ids.append(entry_id)

        if not selected_entry_ids:
            entry_id = self.current_entry_id
            if entry_id is None:
                item = self.entry_list.currentItem()
                if item is not None and item.data(Qt.UserRole) is not None:
                    entry_id = int(item.data(Qt.UserRole))
            if entry_id is not None:
                selected_entry_ids.append(entry_id)

        if not selected_entry_ids:
            show_info_popup(self, "未选择记录", "请先选择一条要删除的记录。")
            return

        rows_to_delete: list[sqlite3.Row] = []
        for entry_id in selected_entry_ids:
            row = self.db.get_entry(entry_id)
            if row:
                rows_to_delete.append(row)

        if not rows_to_delete:
            show_warning_popup(self, "记录不存在", "这条记录已经不存在。")
            self.current_entry_id = None
            self.refresh_entry_list()
            if not self.select_first_entry_if_available():
                self.ensure_unsaved_draft_if_no_entries()
            return

        if len(rows_to_delete) == 1:
            row = rows_to_delete[0]
            title = row["title"] or UNTITLED_ENTRY_TITLE
            if not ask_confirmation_popup(
                self,
                "删除记录",
                f"确定删除“{title}”（{row['entry_date']}）吗？\n此操作不可撤销。",
                confirm_text="删除",
                bind_enter_to_confirm=True,
            ):
                return
        else:
            preview_lines = [
                f"- {row['entry_date']} | {(row['title'] or UNTITLED_ENTRY_TITLE)}"
                for row in rows_to_delete[:3]
            ]
            if len(rows_to_delete) > 3:
                preview_lines.append(f"... 还有 {len(rows_to_delete) - 3} 条")
            message = (
                f"确定删除已选择的 {len(rows_to_delete)} 条记录吗？\n此操作不可撤销。\n\n"
                + "\n".join(preview_lines)
            )
            if not ask_confirmation_popup(
                self,
                "批量删除记录",
                message,
                confirm_text="全部删除",
                bind_enter_to_confirm=True,
            ):
                return

        deleted_entry_ids = {int(row["id"]) for row in rows_to_delete}
        attachment_paths: list[str] = []
        for row in rows_to_delete:
            attachment_paths.extend(self.db.delete_entry(int(row["id"])))

        for file_path in set(attachment_paths):
            if self.db.has_attachment_path(file_path):
                continue
            path = self.resolve_attachment_path(file_path)
            if not self.is_managed_attachment_path(path):
                continue
            self.delete_file_safely(path)

        current_deleted = self.current_entry_id is not None and self.current_entry_id in deleted_entry_ids
        if current_deleted:
            self.current_entry_id = None
        self.refresh_entry_list()
        if current_deleted and not self.select_first_entry_if_available():
            self.ensure_unsaved_draft_if_no_entries()
        if self.on_saved:
            self.on_saved()
        if len(rows_to_delete) == 1:
            show_info_popup(self, "已删除", "记录已删除。")
        else:
            show_info_popup(self, "已删除", f"已删除 {len(rows_to_delete)} 条记录。")

    def refresh_attachment_list(self) -> None:
        self.attachment_list.clear()

        if self.current_entry_id is not None:
            for row in self.db.list_attachments(self.current_entry_id):
                resolved_path = str(self.resolve_attachment_path(str(row["file_path"])))
                metadata = {
                    "pending": False,
                    "attachment_id": int(row["id"]),
                    "file_name": row["file_name"],
                    "file_path": resolved_path,
                    "is_image": int(row["is_image"]),
                }
                item = self.create_attachment_item(
                    row["file_name"],
                    resolved_path,
                    int(row["is_image"]),
                    metadata,
                )
                self.attachment_list.addItem(item)

        for attachment in self.pending_attachments:
            metadata = {
                "pending": True,
                "attachment_id": None,
                "file_name": attachment.file_name,
                "file_path": attachment.file_path,
                "is_image": int(attachment.is_image),
            }
            item = self.create_attachment_item(
                f"{attachment.file_name}（待保存）",
                attachment.file_path,
                int(attachment.is_image),
                metadata,
            )
            self.attachment_list.addItem(item)

    def create_attachment_item(
        self,
        display_name: str,
        file_path: str,
        is_image: int,
        metadata: dict,
    ) -> QListWidgetItem:
        item = QListWidgetItem(display_name)
        item.setIcon(self.create_attachment_icon(file_path, bool(is_image)))
        item.setData(Qt.UserRole, metadata)
        item.setTextAlignment(Qt.AlignHCenter)
        item.setToolTip(file_path)
        return item

    def create_attachment_icon(self, file_path: str, is_image: bool) -> QIcon:
        path = Path(file_path)
        if is_image and path.exists():
            pixmap = load_qpixmap(path)
            if not pixmap.isNull():
                thumbnail = pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                return QIcon(thumbnail)

        if path.exists():
            icon = self.file_icon_provider.icon(QFileInfo(str(path)))
        else:
            icon = self.file_icon_provider.icon(QFileIconProvider.File)
        if icon.isNull():
            icon = QApplication.style().standardIcon(QStyle.SP_FileIcon)
        return icon

    def attach_file(self) -> None:
        file_dialog = QFileDialog(self, "选择附件")
        file_dialog.setFileMode(QFileDialog.ExistingFiles)
        file_dialog.setNameFilter(ATTACHMENT_FILE_FILTER)
        file_dialog.selectNameFilter(ATTACHMENT_FILE_FILTER.split(";;")[0])
        file_dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        center_dialog_on_parent(file_dialog, self)
        if file_dialog.exec() != QDialog.Accepted:
            return
        selected_paths = file_dialog.selectedFiles()
        if not selected_paths:
            return

        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        failed_files: list[str] = []
        added_any = False

        for selected_path in selected_paths:
            source = Path(selected_path)
            if not source.is_file():
                failed_files.append(source.name or selected_path)
                continue

            unique_name = (
                f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}{source.suffix.lower()}"
            )
            destination = self.attachments_dir / unique_name
            try:
                shutil.copy2(source, destination)
            except OSError:
                failed_files.append(source.name)
                continue

            resolved_destination = destination.resolve()
            is_image = 1 if is_image_file(resolved_destination) else 0
            self.pending_attachments.append(
                AttachmentDraft(
                    file_name=source.name,
                    file_path=str(resolved_destination),
                    is_image=is_image,
                )
            )
            added_any = True

        if added_any:
            self.save_current_entry(show_notice=False)
        else:
            self.refresh_attachment_list()

        if failed_files:
            show_warning_popup(
                self,
                "部分附件未添加",
                "以下文件未能成功添加：\n" + "\n".join(failed_files),
            )

    def open_attachment(self, item: QListWidgetItem) -> None:
        metadata = item.data(Qt.UserRole) or {}
        file_path = metadata if isinstance(metadata, str) else metadata.get("file_path")
        if not file_path:
            return
        path = Path(file_path)
        if not path.exists():
            show_warning_popup(self, "文件不存在", f"找不到附件：\n{file_path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def delete_selected_attachment(self) -> None:
        item = self.attachment_list.currentItem()
        if not item:
            show_info_popup(self, "未选择附件", "请先选择一个附件。")
            return

        metadata = item.data(Qt.UserRole) or {}
        file_path = metadata if isinstance(metadata, str) else metadata.get("file_path")
        if not file_path:
            return

        path = Path(file_path)
        file_name = (
            metadata.get("file_name") if isinstance(metadata, dict) else None
        ) or path.name
        if not ask_confirmation_popup(
            self,
            "删除附件",
            f"确定删除附件“{file_name}”吗？\n如果正文中有此附件的历史链接，也会同步移除。",
            confirm_text="删除",
        ):
            return

        if isinstance(metadata, dict) and metadata.get("pending"):
            normalized_path = normalize_path_for_compare(path)
            self.pending_attachments = [
                draft
                for draft in self.pending_attachments
                if normalize_path_for_compare(Path(draft.file_path)) != normalized_path
            ]
        else:
            attachment_id = metadata.get("attachment_id") if isinstance(metadata, dict) else None
            if attachment_id is not None:
                self.db.delete_attachment(int(attachment_id))

        self.remove_attachment_from_editor(str(path.resolve()))
        self.delete_file_safely(path)
        self.refresh_attachment_list()

    def delete_file_safely(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            path.unlink()
        except OSError:
            pass

    def attachment_reference_matches(
        self, reference: str, target_path: str, target_url: str
    ) -> bool:
        if not reference:
            return False

        if reference == target_url:
            return True

        parsed = QUrl(reference)
        if parsed.isLocalFile():
            return normalize_path_for_compare(Path(parsed.toLocalFile())) == target_path

        if "://" not in reference:
            raw_reference_path = Path(reference)
            if raw_reference_path.is_absolute():
                return normalize_path_for_compare(raw_reference_path) == target_path
        return False

    def remove_attachment_from_editor(self, file_path: str) -> bool:
        normalized_target_path = normalize_path_for_compare(Path(file_path))
        file_url = QUrl.fromLocalFile(file_path).toString()
        document = self.editor.document()
        ranges_to_remove: list[tuple[int, int]] = []

        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    remove_fragment = False
                    if fmt.isImageFormat():
                        if self.attachment_reference_matches(
                            fmt.toImageFormat().name(),
                            normalized_target_path,
                            file_url,
                        ):
                            remove_fragment = True
                    elif fmt.isAnchor() and self.attachment_reference_matches(
                        fmt.anchorHref(),
                        normalized_target_path,
                        file_url,
                    ):
                        remove_fragment = True

                    if remove_fragment:
                        ranges_to_remove.append((fragment.position(), fragment.length()))
                iterator += 1
            block = block.next()

        if not ranges_to_remove:
            return False

        for position, length in reversed(ranges_to_remove):
            cursor = QTextCursor(document)
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        return True

    def persist_current_editor_content(self) -> None:
        if self.current_entry_id is None:
            return

        content_html = self.editor.toHtml().strip()
        content_text = self.editor.toPlainText().strip()
        title = self.title_edit.text().strip()
        if not title:
            fallback = content_text[:40].strip()
            title = f"{fallback}..." if len(content_text) > 40 else fallback
            title = title or UNTITLED_ENTRY_TITLE
            self.title_edit.setText(title)

        entry_date = self.date_edit.date().toString("yyyy-MM-dd")
        self.current_entry_id = self.db.save_entry(
            self.current_entry_id,
            entry_date,
            title,
            content_html,
            content_text,
        )
        self.refresh_entry_list()
        self._reset_change_tracking()

    def pick_text_color(self) -> None:
        color_dialog = QColorDialog(self)
        color_dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        center_dialog_on_parent(color_dialog, self)
        if color_dialog.exec() != QDialog.Accepted:
            return
        color = color_dialog.selectedColor()
        if not color.isValid():
            return
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        self.merge_format(fmt)

    def apply_font_family(self, family: str) -> None:
        fmt = QTextCharFormat()
        fmt.setFontFamily(family)
        self.merge_format(fmt)

    def apply_font_size(self, size: int) -> None:
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(size))
        self.merge_format(fmt)

    def toggle_bold(self) -> None:
        current_weight = self.editor.currentCharFormat().fontWeight()
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Normal if current_weight > QFont.Normal else QFont.Bold)
        self.merge_format(fmt, expand_to_word=False)

    def toggle_italic(self) -> None:
        current_italic = self.editor.currentCharFormat().fontItalic()
        fmt = QTextCharFormat()
        fmt.setFontItalic(not current_italic)
        self.merge_format(fmt, expand_to_word=False)

    def toggle_underline(self) -> None:
        current_underline = self.editor.currentCharFormat().fontUnderline()
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not current_underline)
        self.merge_format(fmt, expand_to_word=False)

    def merge_format(self, fmt: QTextCharFormat, expand_to_word: bool = True) -> None:
        cursor = self.editor.textCursor()
        if expand_to_word and not cursor.hasSelection():
            cursor.select(QTextCursor.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self.editor.mergeCurrentCharFormat(fmt)

    def sync_format_controls(self, _format: Optional[QTextCharFormat] = None) -> None:
        fmt = self.editor.currentCharFormat()
        family = fmt.fontFamily().strip() if fmt.fontFamily() else ""
        if family:
            self.font_combo.blockSignals(True)
            self.font_combo.setCurrentFont(QFont(family))
            self.font_combo.blockSignals(False)

        font_size = fmt.fontPointSize()
        if font_size <= 0:
            font_size = float(self.default_editor_font_size)
        self.size_spin.blockSignals(True)
        self.size_spin.setValue(int(round(font_size)))
        self.size_spin.blockSignals(False)


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.db = DiaryDatabase(DATA_ROOT / DB_NAME)
        self.attachments_dir = DATA_ROOT / ATTACHMENTS_DIR
        self.is_dark = False
        self._theme_synced_after_show = False
        self._on_this_day_popup_checked_after_show = False

        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1320, 820)

        self.dashboard_page = DashboardPage(
            on_entry_open_requested=self.open_entry_from_memory,
        )
        self.diary_page = DiaryPage(
            self.db,
            DATA_ROOT,
            self.attachments_dir,
            on_saved=self.refresh_dashboard,
            on_toggle_theme=self.toggle_theme,
        )

        self.dashboard_page.setObjectName("dashboardPage")
        self.diary_page.setObjectName("diaryPage")

        self.dashboard_navigation_item = self.addSubInterface(
            self.dashboard_page,
            QIcon(),
            OVERVIEW_NAV_TEXT,
            NavigationItemPosition.TOP,
        )
        self.diary_navigation_item = self.addSubInterface(
            self.diary_page,
            QIcon(),
            DIARY_NAV_TEXT,
            NavigationItemPosition.TOP,
        )
        self._update_navigation_icons()

        self._apply_window_icon()
        self.apply_theme(False)
        self.switchTo(self.diary_page)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if not self._theme_synced_after_show:
            self._theme_synced_after_show = True
            QTimer.singleShot(0, self._sync_theme_after_show)
        if not self._on_this_day_popup_checked_after_show:
            self._on_this_day_popup_checked_after_show = True
            QTimer.singleShot(0, self.show_on_this_day_popup_if_needed)

    @staticmethod
    def _create_tinted_icon(icon_path: Path, tint: QColor) -> Optional[QIcon]:
        image = load_qimage(icon_path)
        if image.isNull():
            return None
        image = image.convertToFormat(QImage.Format_ARGB32)

        hue = tint.hslHueF()
        saturation = tint.hslSaturationF()
        for y in range(image.height()):
            for x in range(image.width()):
                original = image.pixelColor(x, y)
                alpha = original.alpha()
                if alpha == 0:
                    continue
                recolored = QColor.fromHslF(hue, saturation, original.lightnessF())
                recolored.setAlpha(alpha)
                image.setPixelColor(x, y, recolored)

        return QIcon(QPixmap.fromImage(image))

    def _apply_window_icon(self) -> None:
        icon_path = resolve_resource_path(ICON_NAME)
        if icon_path is not None:
            tinted_icon = self._create_tinted_icon(icon_path, ICON_TINT_COLOR)
            if tinted_icon is not None:
                self.setWindowIcon(tinted_icon)
                return
            pixmap_icon = load_qpixmap(icon_path)
            if not pixmap_icon.isNull():
                self.setWindowIcon(QIcon(pixmap_icon))
                return
            self.setWindowIcon(QIcon(str(icon_path)))
            return

        fallback_icon = QApplication.style().standardIcon(QStyle.SP_FileIcon)
        self.setWindowIcon(fallback_icon)

    @staticmethod
    def _create_navigation_text_icon(text: str, dark: bool) -> QIcon:
        size = 24
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        bg_color = themeColor()
        text_color = QColor("#000000") if dark else QColor("#FFFFFF")

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        painter.drawEllipse(1, 1, size - 2, size - 2)

        text_font = QFont(QApplication.font())
        text_font.setPointSize(8)
        text_font.setBold(True)
        painter.setFont(text_font)
        painter.setPen(text_color)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()

        return QIcon(pixmap)

    def _update_navigation_icons(self) -> None:
        self.dashboard_navigation_item.setIcon(
            self._create_navigation_text_icon(OVERVIEW_NAV_ICON_TEXT, self.is_dark)
        )
        self.diary_navigation_item.setIcon(
            self._create_navigation_text_icon(DIARY_NAV_ICON_TEXT, self.is_dark)
        )

    def apply_theme(self, dark: bool) -> None:
        self.is_dark = dark
        setTheme(Theme.DARK if dark else Theme.LIGHT)
        self._update_navigation_icons()
        self.setStyleSheet(DARK_APP_STYLE if dark else LIGHT_APP_STYLE)
        self.dashboard_page.apply_theme(dark)
        self.diary_page.set_theme_state(dark)
        self.refresh_dashboard()

    def toggle_theme(self) -> None:
        self.apply_theme(not self.is_dark)

    def _sync_theme_after_show(self) -> None:
        self.apply_theme(self.is_dark)

    def refresh_dashboard(self) -> None:
        memories = self.db.get_on_this_day_memories(date.today())
        self.dashboard_page.update_content(self.db.total_entries(), memories)

    def open_entry_from_memory(self, entry_id: int) -> None:
        if not self.diary_page.open_entry_by_id(entry_id):
            show_warning_popup(self, "跳转失败", "找不到对应的日记，可能已被删除。")
            self.refresh_dashboard()
            return
        self.switchTo(self.diary_page)

    def show_on_this_day_popup_if_needed(self) -> None:
        today_text = date.today().isoformat()
        last_checked_date = self.db.get_meta(ON_THIS_DAY_POPUP_META_KEY)
        if last_checked_date == today_text:
            return
        self.db.set_meta(ON_THIS_DAY_POPUP_META_KEY, today_text)
        self.show_on_this_day_popup()

    def show_on_this_day_popup(self) -> None:
        memories = self.db.get_on_this_day_memories(date.today())
        if not memories:
            return

        lines = [f"{row['entry_date']}: {row['title']}" for row in memories[:3]]
        more = "" if len(memories) <= 3 else f"\n...还有 {len(memories) - 3} 条"
        message = (
            f"今天是 {date.today().strftime('%m月%d日')}，你有 {len(memories)} 条往年回忆：\n\n"
            + "\n".join(lines)
            + more
        )
        show_info_popup(self, "今日回忆", message)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.diary_page.has_unsaved_changes():
            close_only_result = int(QDialog.Accepted) + 1
            close_action = ask_confirmation_popup_with_result(
                self,
                "未保存内容",
                "检测到你有未保存的新内容，是否保存后再退出？",
                confirm_text="是",
                cancel_text="否",
                close_result=close_only_result,
                bind_enter_to_confirm=True,
            )
            if close_action == QDialog.Accepted:
                self.diary_page.save_current_entry(show_notice=False)
            elif close_action == close_only_result:
                event.ignore()
                return
        self.db.close()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    resolved_ui_font = resolve_ui_font_family()
    ui_font_families: List[str] = []
    seen: set[str] = set()
    for family in ("汉仪中黑", resolved_ui_font, *resolve_ui_font_families()):
        key = family.casefold()
        if key in seen:
            continue
        seen.add(key)
        ui_font_families.append(family)
    setFontFamilies(ui_font_families)
    app.setFont(QFont(resolved_ui_font, 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
