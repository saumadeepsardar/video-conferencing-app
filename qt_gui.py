import os
import cv2
import pyaudio
import mss
import numpy as np
import sys
from PyQt6.QtCore import Qt, QThread, QTimer, QSize, QRunnable, pyqtSlot, QPropertyAnimation, QEasingCurve, QEvent
from PyQt6.QtGui import QImage, QPixmap, QActionGroup, QIcon, QFont, QAction
from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout, QDockWidget \
    , QLabel, QWidget, QListWidget, QListWidgetItem, QMessageBox \
    , QComboBox, QTextEdit, QLineEdit, QPushButton, QFileDialog \
    , QDialog, QMenu, QWidgetAction, QCheckBox, QStyleFactory, QGraphicsDropShadowEffect \
    , QSpacerItem, QSizePolicy, QProgressBar, QMenuBar, QToolButton,QInputDialog

from constants import *

# Screen capture integration from qijungu/screenshare
ver = sys.version_info.major
if ver == 2:
    import StringIO as io
elif ver == 3:
    import io

if sys.platform in ["win32", "darwin"]:
    from PIL import ImageGrab as ig
else:
    import pyscreenshot as ig
    bkend = "pygdk3"  # or other backend if needed

# Camera
CAMERA_RES = '240p'
LAYOUT_RES = '900p'
frame_size = {
    '240p': (352, 240),
    '360p': (480, 360),
    '480p': (640, 480),
    '560p': (800, 560),
    '720p': (1080, 720),
    '900p': (1400, 900),
}
FRAME_WIDTH = frame_size[CAMERA_RES][0]
FRAME_HEIGHT = frame_size[CAMERA_RES][1]

# Image Encoding
ENABLE_ENCODE = True
ENCODE_PARAM = [int(cv2.IMWRITE_JPEG_QUALITY), 90]

# frame for no camera
NOCAM_FRAME = cv2.imread("img/nocam.jpeg")
# crop center part of the nocam frame
nocam_h, nocam_w = NOCAM_FRAME.shape[:2]
x, y = (nocam_w - FRAME_WIDTH)//2, (nocam_h - FRAME_HEIGHT)//2
NOCAM_FRAME = NOCAM_FRAME[y:y+FRAME_HEIGHT, x:x+FRAME_WIDTH]
# frame for no microphone
NOMIC_FRAME = cv2.imread("img/nomic.jpeg")

# Audio
ENABLE_AUDIO = True
SAMPLE_RATE = 48000
BLOCK_SIZE = 2048
pa = pyaudio.PyAudio()

# Modern Stylesheet
MODERN_STYLESHEET = """
QMainWindow {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 12px;
}
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border: none;
}
QLabel {
    color: #cdd6f4;
    background-color: transparent;
    border: none;
    padding: 5px;
}
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #74c7ec;
}
QPushButton:pressed {
    background-color: #5e9bd5;
}
QLineEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 2px solid #45475a;
    border-radius: 8px;
    padding: 8px;
    font-size: 12px;
}
QLineEdit:focus {
    border-color: #89b4fa;
    background-color: #313244;
}
QTextEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 2px solid #45475a;
    border-radius: 8px;
    padding: 8px;
    font-size: 11px;
}
QListWidget {
    background-color: #313244;
    color: #cdd6f4;
    border: 2px solid #45475a;
    border-radius: 8px;
    alternate-background-color: #45475a;
}
QListWidget::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}
QCheckBox {
    color: #cdd6f4;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 2px solid #45475a;
    background-color: #313244;
}
QCheckBox::indicator:checked {
    background-color: #a6e3a1;
    border: 2px solid #a6e3a1;
}
QDockWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}
QDockWidget::title {
    background-color: #313244;
    padding: 8px;
    border-bottom: 1px solid #45475a;
    font-weight: bold;
}
QMenu {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 8px;
}
QMenu::item {
    padding: 8px 16px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}
QDialog {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
QMessageBox {
    background-color: #1e1e2e;
    color: #cdd6f4;
}
"""


class PersistentMenu(QMenu):
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            action = self.actionAt(event.pos())
            if action and isinstance(action, QWidgetAction):
                widget = action.defaultWidget()
                if isinstance(widget, QCheckBox):
                    widget.setChecked(not widget.isChecked())
                event.ignore()
                return
        super().mouseReleaseEvent(event)


class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    @pyqtSlot()
    def run(self):
        self.fn(*self.args, **self.kwargs)


class Microphone:
    def __init__(self):
        try:
            self.stream = pa.open(
                rate=SAMPLE_RATE,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=BLOCK_SIZE
            )
        except Exception as e:
            print(f"[ERROR] Microphone initialization failed: {e}")
            self.stream = None

    def get_data(self):
        if self.stream is None:
            return None
        try:
            return self.stream.read(BLOCK_SIZE)
        except Exception as e:
            print(f"[ERROR] Microphone read failed: {e}")
            return None


class AudioThread(QThread):
    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        try:
            self.stream = pa.open(
                rate=SAMPLE_RATE,
                channels=1,
                format=pyaudio.paInt16,
                output=True,
                frames_per_buffer=BLOCK_SIZE
            )
        except Exception as e:
            print(f"[ERROR] Audio output initialization failed: {e}")
            self.stream = None
        self.connected = True

    def run(self):
        if self.client.microphone is not None:
            return
        while self.connected:
            self.update_audio()

    def update_audio(self):
        data = self.client.get_audio()
        if data is not None and self.stream is not None:
            try:
                self.stream.write(data)
            except Exception as e:
                print(f"[ERROR] Audio playback failed: {e}")


class Camera:
    def __init__(self):
        self.cap = None
        for index in range(3):
            cap = cv2.VideoCapture(index)
            if cap.isOpened():
                self.cap = cap
                print(f"[INFO] Camera found at index {index}")
                break
        if self.cap is None:
            print("[ERROR] No camera found at indices 0-2")

    def get_frame(self):
        if self.cap is None:
            return None
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, frame_size[CAMERA_RES], interpolation=cv2.INTER_AREA)
            if ENABLE_ENCODE:
                _, frame = cv2.imencode('.jpg', frame, ENCODE_PARAM)
            return frame
        return None


class ScreenCapturer:
    def __init__(self):
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]  # main monitor
        print("[INFO] ScreenCapturer initialized with MSS backend")

    def capture(self):
        try:
            frame = np.array(self.sct.grab(self.monitor))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            _, img_encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            return img_encoded.tobytes()
        except Exception as e:
            print(f"[ERROR] MSS screen capture failed: {e}")
            return None



class VideoWidget(QWidget):
    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_video)
        self.init_video()

    def init_ui(self):
        self.setStyleSheet("border-radius: 12px; background-color: #313244;")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setColor(Qt.GlobalColor.black)
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

        self.video_viewer = QLabel()
        if self.client.current_device:
            self.name_label = QLabel(f"You - {self.client.name}")
            self.name_label.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        else:
            self.name_label = QLabel(self.client.name)
            self.name_label.setStyleSheet("color: #89b4fa;")
        self.video_viewer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout = QVBoxLayout()
        self.layout.setSpacing(5)
        self.layout.addWidget(self.video_viewer)
        self.layout.addWidget(self.name_label)
        self.setLayout(self.layout)
    
    def init_video(self):
        self.timer.start(30)
    
    def update_video(self):
        frame = self.client.get_video()
        if frame is None:
            frame = NOCAM_FRAME.copy()
        elif ENABLE_ENCODE:
            frame = cv2.imdecode(frame, cv2.IMREAD_COLOR)
        
        frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT), interpolation=cv2.INTER_AREA)
        
        if self.client.audio_data is None:
            nomic_h, nomic_w, _ = NOMIC_FRAME.shape
            x, y = FRAME_WIDTH//2 - nomic_w//2, FRAME_HEIGHT - 50
            frame[y:y+nomic_h, x:x+nomic_w] = NOMIC_FRAME.copy()

        h, w, ch = frame.shape
        bytes_per_line = ch * w
        q_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self.video_viewer.setPixmap(QPixmap.fromImage(q_img))


class ScreenShareWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.presenter_name = ""
        self.maximized = False
        self.original_parent = None
        self.original_layout = None
        self.video_list_widget = None
        self.default_height = 300
        self.last_image_bytes = None
        self.setMinimumHeight(self.default_height)
        self.setMaximumHeight(self.default_height)

        self.presenter_label = QLabel("Screen Share by: None")
        self.presenter_label.setStyleSheet("color: #f9e2af; font-weight: bold;")
        self.presenter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.screen_viewer = QLabel()
        self.screen_viewer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_viewer.setStyleSheet("border: none; background-color: #000; border-radius: 12px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.presenter_label)
        layout.addWidget(self.screen_viewer, 1)

        # Floating maximize button
        self.max_btn = QPushButton(self)
        self.max_btn.setIcon(QIcon("img/maximise.png"))
        self.max_btn.setIconSize(QSize(20, 20))
        self.max_btn.setFixedSize(32, 32)
        self.max_btn.setToolTip("Maximize screen share")
        self.max_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255,255,255,0.2);
                border-radius: 10px;
                border: none;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.4); }
        """)
        self.max_btn.setFlat(True)
        self.max_btn.clicked.connect(self.toggle_maximize)

        # Position button at top-right corner
        self.max_btn.raise_()
        self.max_btn.move(self.width() - 45, 10)

    def resizeEvent(self, event):
        # Reposition floating button on resize
        self.max_btn.move(self.width() - 45, 10)
        super().resizeEvent(event)

    def toggle_maximize(self):
        """Toggle maximize/restore for screen share panel"""
        main_window = self.window()
        central_widget = main_window.centralWidget()
        central_layout = central_widget.layout()

        if not self.maximized:
            # Save references
            self.original_parent = self.parent()
            self.original_layout = self.original_parent.layout() if self.original_parent else None
            if self.original_layout:
                self.original_layout.removeWidget(self)

            # Hide sidebar to cover its area
            self.sidebar = next((d for d in main_window.findChildren(QDockWidget) if d.windowTitle() == "Chat"), None)
            if self.sidebar:
                self.sidebar.hide()

            # Remove video_list from layout to free space
            video_item = central_layout.takeAt(0)
            if video_item:
                self.video_list_widget = video_item.widget()

            # Remove size constraints to allow full expansion
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)

            # Re-add to central layout at the end to keep "bottom" positioning
            central_layout.addWidget(self)
            self.show()

            # Hide label for full coverage
            self.presenter_label.hide()

            # Update button
            self.max_btn.setIcon(QIcon("img/restore.png"))
            self.max_btn.setToolTip("Restore screen share")

            self.maximized = True
            self.update()

            # Refresh the image if available
            if self.last_image_bytes:
                self.show_share(self.presenter_name, self.last_image_bytes, is_presenter=False)
        else:
            # Restore: re-add video_list and show sidebar
            central_layout.removeWidget(self)

            if self.video_list_widget:
                central_layout.insertWidget(0, self.video_list_widget)
                self.video_list_widget = None

            if self.sidebar:
                self.sidebar.show()
                self.sidebar = None

            # Restore size constraints
            self.setMinimumHeight(self.default_height)
            self.setMaximumHeight(self.default_height)

            # Show label
            self.presenter_label.show()

            # Re-add to original layout if exists
            if self.original_layout:
                self.original_layout.addWidget(self)

            # Update button
            self.max_btn.setIcon(QIcon("img/maximise.png"))
            self.max_btn.setToolTip("Maximize screen share")

            self.maximized = False
            self.show()
            self.update()

    def show_share(self, presenter_name, image_bytes, is_presenter=False):
        self.presenter_name = presenter_name

        if is_presenter:
            self.presenter_label.setText("You are now presenting your screen")
            self.screen_viewer.setText("Your screen is being shared...")
            self.screen_viewer.setStyleSheet("color: #a6e3a1; background-color: #000; border-radius: 12px;")
            self.max_btn.hide()
            return

        self.max_btn.show()
        self.presenter_label.setText(f"Screen shared by: {presenter_name}")

        if image_bytes:
            try:
                image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
                if image is not None:
                    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                    h, w, ch = image.shape
                    bytes_per_line = ch * w
                    q_img = QImage(image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(q_img)

                    # Scale to screen viewer size
                    target_size = self.screen_viewer.size()
                    pixmap = pixmap.scaled(
                        target_size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.screen_viewer.setPixmap(pixmap)
                    self.last_image_bytes = image_bytes
                    return
            except Exception as e:
                print(f"[ERROR] Failed to render screen share image: {e}")

        self.screen_viewer.setText("Waiting for screen data...")
        self.last_image_bytes = None

class VideoListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_items = {}
        self.screen_share_item = None
        self.screen_share_widget = None
        self.init_ui()

    def init_ui(self):
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setSpacing(10)
        self.setStyleSheet("QListWidget { border: none; background: transparent; }")

    def add_client(self, client):
        video_widget = VideoWidget(client)
        item = QListWidgetItem()
        item.setFlags(item.flags() & ~(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled))
        if client.current_device:
            insert_index = 1 if self.screen_share_item else 0
            self.insertItem(insert_index, item)
        else:
            self.addItem(item)
        item.setSizeHint(QSize(FRAME_WIDTH, FRAME_HEIGHT))
        self.setItemWidget(item, video_widget)
        self.all_items[client.name] = item
        self.resize_widgets()

    
    def add_screen_share(self, presenter_name, image_bytes, is_presenter=False):
        if not self.screen_share_widget:
            self.screen_share_widget = ScreenShareWidget()
            self.parentWidget().layout().addWidget(self.screen_share_widget)
        self.screen_share_widget.show_share(presenter_name, image_bytes, is_presenter)

    def remove_screen_share(self):
        if self.screen_share_widget:
            self.screen_share_widget.setParent(None)
            self.screen_share_widget.deleteLater()
            self.screen_share_widget = None

    def resize_widgets(self, res: str = None):
        global FRAME_WIDTH, FRAME_HEIGHT, LAYOUT_RES
        n = self.count()
        if res is None:
            if n <= 1:
                res = "900p"
            elif n <= 4:
                res = "480p"
            elif n <= 6:
                res = "360p"
            else:
                res = "240p"
        new_size = frame_size[res]
        
        if new_size == (FRAME_WIDTH, FRAME_HEIGHT):
            return
        else:
            FRAME_WIDTH, FRAME_HEIGHT = new_size
            LAYOUT_RES = res
        
        for i in range(n):
            if self.item(i) == self.screen_share_item:
                self.item(i).setSizeHint(QSize(1200, 800))
            else:
                self.item(i).setSizeHint(QSize(FRAME_WIDTH, FRAME_HEIGHT))

    def remove_client(self, name: str):
        self.takeItem(self.row(self.all_items[name]))
        self.all_items.pop(name)
        self.resize_widgets()

class FileTransferItem(QWidget):
    def __init__(self, filename: str, total: int, parent=None):
        super().__init__(parent)
        self.total = total
        self.received = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        self.label = QLabel(f"{filename} (0 / {self._human(total)})")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setStyleSheet("""
            QProgressBar { border: none; background: #313244; border-radius: 3px; }
            QProgressBar::chunk { background: #a6e3a1; border-radius: 3px; }
        """)

        self.save_btn = QPushButton("Save…")
        self.save_btn.setMinimumWidth(100)
        self.save_btn.setFixedHeight(28)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                border-radius: 6px;
                padding: 4px 10px;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #a6adc8;
                color: #1e1e2e;
            }
        """)
        self.save_btn.clicked.connect(self._save_file)
        self.save_btn.setEnabled(False)


        layout.addWidget(self.label, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.save_btn)

        self._buffer = bytearray()

    def _human(self, bytes_: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_ < 1024:
                return f"{bytes_:.1f}{unit}"
            bytes_ /= 1024
        return f"{bytes_:.1f}TB"

    def append_data(self, chunk: bytes):
        self._buffer.extend(chunk)
        self.received = len(self._buffer)
        percent = int(self.received * 100 / self.total)
        self.progress.setValue(percent)
        self.label.setText(f"{os.path.basename(self.label.text().split(' (')[0])} "
                           f"({self._human(self.received)} / {self._human(self.total)})")

        if self.received >= self.total:
            self.save_btn.setEnabled(True)

    def _save_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save file", os.path.basename(self.label.text().split(' (')[0]))
        if path:
            with open(path, "wb") as f:
                f.write(self._buffer)
            QMessageBox.information(self, "Saved", f"File saved to:\n{path}")
            self.save_btn.setEnabled(False)
            self.save_btn.setText("Saved")
            
            
class ChatWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.clients_checkboxes = {}
        self.clients_menu_actions = {}
        self.transfer_widgets: dict[str, FileTransferItem] = {}
        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout()
        self.layout.setSpacing(10)
        self.setLayout(self.layout)

        self.central_widget = QTextEdit(self)
        self.central_widget.setReadOnly(True)
        self.layout.addWidget(self.central_widget)

        self.clients_menu = PersistentMenu("Clients", self)
        select_all_action = QAction("Select All", self.clients_menu)
        select_all_action.triggered.connect(self.select_all)
        self.clients_menu.addAction(select_all_action)
        self.clients_menu.addSeparator()

        self.clients_button = QPushButton("Clients", self)
        self.clients_button.setStyleSheet("background-color: #f9e2af; color: #1e1e2e;")
        self.clients_button.setMenu(self.clients_menu)
        self.layout.addWidget(self.clients_button)

        self.share_button = QPushButton("Share Screen", self)
        self.layout.addWidget(self.share_button)

        self.line_layout = QHBoxLayout()
        self.line_edit = QLineEdit(self)
        self.send_button = QPushButton("Send", self)
        self.file_button = QPushButton("File", self)
        self.line_layout.addWidget(self.line_edit)
        self.line_layout.addWidget(self.send_button)
        self.line_layout.addWidget(self.file_button)
        self.layout.addLayout(self.line_layout)

        self.end_button = QPushButton("End Call", self)
        self.end_button.setStyleSheet("background-color: #f38ba8; color: #1e1e2e;")
        self.layout.addWidget(self.end_button)
        
        self.transfer_area = QVBoxLayout()
        self.transfer_area.setSpacing(4)
        self.layout.insertLayout(3, self.transfer_area)
        # existing download button creation...
        self.download_button = QToolButton(self)
        self.download_button.setText("Download")
        self.download_menu = QMenu(self)
        self.download_button.setMenu(self.download_menu)
        self.download_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.download_button.setFixedHeight(36)
        self.download_button.setMinimumWidth(120)

        # make same style and font as other buttons (bold, matching padding)
        self.download_button.setStyleSheet("""
            QToolButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QToolButton:hover { background-color: #74c7ec; }
            QToolButton:pressed { background-color: #5e9bd5; }
        """)


        self.line_layout.addWidget(self.download_button)

        # Hook: when download dropdown is clicked we refresh the files list
        self.download_button.clicked.connect(self._on_download_clicked)
        # maintain mapping transfer_id -> FileTransferItem (incoming)
        self.transfer_widgets: dict[str, FileTransferItem] = {}
        # existing transfer_area code remains
        
        
    def _on_download_clicked(self):
        # request server for file list for this client
        # server_conn is not directly available here; the MainWindow will connect server->files_list_signal
        # We rely on MainWindow to call server_conn.request_file_list() when needed
        # Emit a placeholder message so MainWindow can trigger a request
        # We will instead call the top-level window's server_conn if available
        try:
            parent = self.window()
            if hasattr(parent, 'server_conn') and parent.server_conn is not None:
                parent.server_conn.request_file_list()
        except Exception as e:
            print(f"[ERROR] Could not request file list: {e}")

    # === File Download UI Methods ===
    def populate_download_menu(self, files_list):
        """
        Populates the QMenu dropdown attached to the Download button.
        Each QAction in the menu represents one available file and stores metadata in .data().
        Expected entry format: {"transfer_id","filename","size","from","timestamp"}.
        """
        try:
            # Ensure we have a proper QMenu
            if not hasattr(self, "download_menu") or not isinstance(self.download_menu, QMenu):
                self.download_menu = QMenu(self)
                self.download_button.setMenu(self.download_menu)

            self.download_menu.clear()

            if not files_list:
                empty_action = self.download_menu.addAction("(No files available)")
                empty_action.setEnabled(False)
                return

            unique = {}
            for entry in files_list:
                if not isinstance(entry, dict):
                    continue
                tid = entry.get("transfer_id")
                if not tid or tid in unique:
                    continue
                unique[tid] = True

                filename = entry.get("filename", "<unknown>")
                sender = entry.get("from", "")
                size = entry.get("size", 0)
                size_kb = f"{size/1024:.1f} KB"
                label = f"{filename} ({size_kb}) — from {sender}"

                act = self.download_menu.addAction(label)
                act.setData(entry)
                act.triggered.connect(lambda checked=False, a=act: self._download_action_triggered(a))
            print(f"[ChatWidget] populate_download_menu: {len(files_list)} items")

        except Exception as e:
            print("[ChatWidget] populate_download_menu ERROR:", e)

    def _download_action_triggered(self, action):
        """Called when a file is selected from the download dropdown."""
        entry = action.data()
        if not entry:
            return
        transfer_id = entry.get("transfer_id")
        filename = entry.get("filename")
        size = entry.get("size", 0)

        try:
            parent = self.window()
            if hasattr(parent, 'server_conn') and parent.server_conn is not None:
                parent.server_conn.request_download(transfer_id)
                self.start_file_transfer(transfer_id, filename, size, entry.get("from", ""))
        except Exception as e:
            print(f"[ERROR] download request failed: {e}")

    def start_file_transfer(self, transfer_id: str, filename: str, total: int, from_name: str):
        """Called when a file starts arriving."""
        item = FileTransferItem(filename, total, self)
        self.transfer_area.addWidget(item)
        self.transfer_widgets[transfer_id] = item
        self.central_widget.append(f"[{from_name}] → File: {filename} ({self._human(total)})")

    def update_file_transfer(self, transfer_id: str, chunk: bytes):
        """Append a chunk to an in-progress transfer."""
        if transfer_id in self.transfer_widgets:
            self.transfer_widgets[transfer_id].append_data(chunk)

    def finish_file_transfer(self, transfer_id: str):
        """Called when server signals file download finished."""
        if transfer_id not in self.transfer_widgets:
            return
        widget = self.transfer_widgets[transfer_id]
        widget.progress.setValue(100)
        widget.save_btn.setEnabled(True)

    def update_download_progress(self, percent):
        """Optional download progress update (if server supports percent updates)."""
        try:
            if hasattr(self, "download_progress"):
                self.download_progress.setVisible(True)
                self.download_progress.setValue(int(percent))
        except Exception as e:
            print("[ChatWidget] update_download_progress ERROR:", e)

    def download_complete(self, filename):
        """Called when file download finishes."""
        try:
            if hasattr(self, "download_progress"):
                self.download_progress.setValue(100)
                self.download_progress.setVisible(False)
            self.add_message(f"Download complete: {filename}")
        except Exception as e:
            print("[ChatWidget] download_complete ERROR:", e)
    # === End File Download UI Methods ===



    def _start_file_download(self):
        """
        Called when user clicks Download button.
        Requests selected file (by transfer_id) from the server.
        """
        try:
            # find server_conn via top-level window if not directly set
            if not hasattr(self, "server_conn") and hasattr(self.window(), "server_conn"):
                self.server_conn = self.window().server_conn

            if not hasattr(self, "download_menu"):
                return

            data = self.download_menu.currentData()
            if not data or not isinstance(data, dict):
                # nothing selected or malformed entry
                QMessageBox.information(self, "Download", "No file selected.")
                return

            transfer_id = data.get("transfer_id")
            if not transfer_id:
                QMessageBox.warning(self, "Download", "Selected file lacks transfer id.")
                return

            # show progress bar UI
            self.download_progress.setValue(0)
            self.download_progress.setVisible(True)

            # Ask the server (via client-side ServerConnection wrapper) to stream this transfer
            # We call the convenience method on server_conn which sends the correct message format.
            # If server_conn is not available, fallback to manual send.
            try:
                self.server_conn.request_download(transfer_id)
            except Exception:
                # fallback
                msg = Message(self.window().client.name, DOWNLOAD_FILE, FILE, {"transfer_id": transfer_id})
                self.server_conn.send_msg(self.server_conn.main_socket, msg)

        except Exception as e:
            print("[ChatWidget] _start_file_download ERROR:", e)
            QMessageBox.critical(self, "Error", f"Failed to request download: {e}")


    def update_download_progress(self, percent):
        """
        Updates the progress bar as download proceeds.
        """
        try:
            if hasattr(self, "download_progress"):
                self.download_progress.setVisible(True)
                self.download_progress.setValue(int(percent))
        except Exception as e:
            print("[ChatWidget] update_download_progress ERROR:", e)

    def download_complete(self, filename):
        """
        Called when file download finishes.
        """
        try:
            if hasattr(self, "download_progress"):
                self.download_progress.setValue(100)
                self.download_progress.setVisible(False)
            self.add_message(f"Download complete: {filename}")
        except Exception as e:
            print("[ChatWidget] download_complete ERROR:", e)
    # === End File Download UI Methods ===


    def _download_action_triggered(self, action):
        entry = action.data()
        if not entry:
            return
        transfer_id = entry.get("transfer_id")
        filename = entry.get("filename")
        size = entry.get("size", 0)
        # Ask main window's server_conn to start the download
        try:
            parent = self.window()
            if hasattr(parent, 'server_conn') and parent.server_conn is not None:
                parent.server_conn.request_download(transfer_id)
                # UI: create an incoming transfer widget so user sees progress
                self.start_file_transfer(transfer_id, filename, size, entry.get("from", ""))
        except Exception as e:
            print(f"[ERROR] download request failed: {e}")
    def start_file_transfer(self, transfer_id: str, filename: str, total: int, from_name: str):
        """Called when a file starts arriving."""
        item = FileTransferItem(filename, total, self)
        self.transfer_area.addWidget(item)
        self.transfer_widgets[transfer_id] = item

        # also show a system line in the chat log
        self.central_widget.append(f"[{from_name}] → File: {filename} ({self._human(total)})")

    def update_file_transfer(self, transfer_id: str, chunk: bytes):
        """Append a chunk to an in-progress transfer."""
        if transfer_id in self.transfer_widgets:
            self.transfer_widgets[transfer_id].append_data(chunk)

    def finish_file_transfer(self, transfer_id: str):
        """Optional – called when server says transfer is done."""
        if transfer_id not in self.transfer_widgets:
            return
        widget = self.transfer_widgets[transfer_id]
        widget.progress.setValue(100)
        widget.save_btn.setEnabled(True)
        # keep the widget for a while so user can still click “Save…”
        
    def start_upload_transfer(self, upload_id: str, filename: str, total: int, to_names: tuple):
        """Create an upload progress widget for an outgoing file."""
        label_to = ", ".join(to_names) if isinstance(to_names, (list, tuple)) else str(to_names)
        item = FileTransferItem(filename, total, self)
        item.total_bytes = total  # store for progress calculations
        item.label.setText(f"Uploading to {label_to}: {filename} (0 / {self._human(total)})")
        self.transfer_area.addWidget(item)
        self.transfer_widgets[upload_id] = item


    def update_upload_progress(self, upload_id: str, percent: int):
        """Update outgoing upload progress widget by percent and bytes."""
        if upload_id in self.transfer_widgets:
            widget = self.transfer_widgets[upload_id]
            try:
                widget.progress.setValue(int(percent))
                if hasattr(widget, "total_bytes"):
                    sent_bytes = int((percent / 100) * widget.total_bytes)
                    label_prefix = widget.label.text().split('(')[0].strip()
                    widget.label.setText(f"{label_prefix} ({self._human(sent_bytes)} / {self._human(widget.total_bytes)})")
                else:
                    # fallback if total not stored
                    label_prefix = widget.label.text().split('(')[0].strip()
                    widget.label.setText(f"{label_prefix} ({percent}%)")
            except Exception as e:
                print(f"[UI] update_upload_progress ERROR: {e}")


    def finish_upload_transfer(self, upload_id: str):
        """Mark outgoing upload complete."""
        if upload_id in self.transfer_widgets:
            widget = self.transfer_widgets[upload_id]
            widget.progress.setValue(100)
            widget.save_btn.setEnabled(False)
            widget.save_btn.setText("Uploaded")
            widget.save_btn.setStyleSheet("""
                QPushButton {
                    background-color: #a6e3a1;
                    color: #1e1e2e;
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-weight: bold;
                }
            """)
    
    def _human(self, b: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if b < 1024:
                return f"{b:.1f}{unit}"
            b /= 1024
        return f"{b:.1f}TB"

    def add_client(self, name: str):
        if name in self.clients_checkboxes:
            return
        checkbox = QCheckBox(name, self)
        checkbox.setChecked(True)
        action = QWidgetAction(self.clients_menu)
        action.setDefaultWidget(checkbox)
        self.clients_menu.addAction(action)
        self.clients_checkboxes[name] = checkbox
        self.clients_menu_actions[name] = action

    def remove_client(self, name: str):
        if name in self.clients_menu_actions:
            self.clients_menu.removeAction(self.clients_menu_actions[name])
            del self.clients_checkboxes[name]
            del self.clients_menu_actions[name]

    def selected_clients(self):
        selected = []
        for name, checkbox in self.clients_checkboxes.items():
            if checkbox.isChecked():
                selected.append(name)
        return tuple(selected)

    def get_text(self):
        text = self.line_edit.text()
        self.line_edit.clear()
        return text

    def get_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select File")
        return filepath

    def add_msg(self, from_name: str, to_names: str, msg: str):
        formatted = f"[{from_name} -> {to_names}] {msg}\n"
        self.central_widget.append(formatted)

    def select_all(self):
        for checkbox in self.clients_checkboxes.values():
            checkbox.setChecked(True)


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Login")
        self.setStyleSheet(MODERN_STYLESHEET)

        self.layout = QGridLayout()
        self.setLayout(self.layout)

        self.name_label = QLabel("Username", self)
        self.name_label.setStyleSheet("font-weight: bold; color: #f9e2af;")
        self.layout.addWidget(self.name_label, 0, 0)

        self.name_edit = QLineEdit(self)
        self.layout.addWidget(self.name_edit, 0, 1)

        self.button = QPushButton("Login", self)
        self.button.setStyleSheet("background-color: #a6e3a1; color: #1e1e2e; font-weight: bold;")
        self.layout.addWidget(self.button, 1, 1)

        self.button.clicked.connect(self.login)
    
    def get_name(self):
        return self.name_edit.text()
    
    def login(self):
        if self.get_name() == "":
            QMessageBox.critical(self, "Error", "Username cannot be empty")
            return
        if " " in self.get_name():
            QMessageBox.critical(self, "Error", "Username cannot contain spaces")
            return
        self.accept()
    
    def close(self):
        self.reject()


class MainWindow(QMainWindow):
    def __init__(self, client, server_conn):
        super().__init__()
        self.client = client
        self.server_conn = server_conn
        self.audio_threads = {}
        self.screen_share_active = False
        self.other_sharing = False
        self.current_presenter = None

        self.server_conn.add_client_signal.connect(self.add_client)
        self.server_conn.remove_client_signal.connect(self.remove_client)
        self.server_conn.add_msg_signal.connect(self.add_msg)
        self.server_conn.screen_share_start_signal.connect(self.on_screen_share_start)
        self.server_conn.screen_share_stop_signal.connect(self.on_screen_share_stop)
        self.server_conn.screen_update_signal.connect(self.on_screen_update)
        self.server_conn.screen_share_reject_signal.connect(self.on_screen_share_reject)

        self.login_dialog = LoginDialog(self)
        if not self.login_dialog.exec():
            exit()
        
        self.server_conn.name = self.login_dialog.get_name()
        self.client.name = self.server_conn.name
        self.server_conn.start()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Video Conferencing")
        self.setGeometry(0, 0, 1920, 1000)
        self.setStyleSheet(MODERN_STYLESHEET)

        self.central_widget = QWidget()
        self.central_layout = QVBoxLayout()
        self.central_widget.setLayout(self.central_layout)
        self.setCentralWidget(self.central_widget)
        
        self.video_list_widget = VideoListWidget()
        self.central_layout.addWidget(self.video_list_widget)
        
        self.sidebar = QDockWidget("Chat", self)
        self.sidebar.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.chat_widget = ChatWidget(self)
        self.sidebar.setWidget(self.chat_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.sidebar)
        self.chat_widget.send_button.clicked.connect(lambda: self.send_msg(TEXT))
        self.chat_widget.line_edit.returnPressed.connect(lambda: self.send_msg(TEXT))
        self.chat_widget.file_button.clicked.connect(lambda: self.send_msg(FILE))
        self.chat_widget.share_button.clicked.connect(self.toggle_screen_share)
        self.chat_widget.end_button.clicked.connect(self.close)

        self.screen_timer = QTimer()
        self.screen_timer.timeout.connect(self.capture_and_send_screen)
        self.screen_timer.setInterval(500)
        
        self.camera_menu = self.menuBar().addMenu("Camera")
        self.camera_menu.setStyleSheet("QMenu { background-color: #313244; color: #cdd6f4; }")
        self.microphone_menu = self.menuBar().addMenu("Microphone")
        self.microphone_menu.setStyleSheet("QMenu { background-color: #313244; color: #cdd6f4; }")
        self.layout_menu = self.menuBar().addMenu("Layout")
        self.layout_menu.setStyleSheet("QMenu { background-color: #313244; color: #cdd6f4; }")
        
        self.camera_menu.addAction("Disable", self.toggle_camera)
        self.camera_menu.actions()[0].setIcon(QIcon('img/cam-disable.png'))
        self.microphone_menu.addAction("Disable", self.toggle_microphone)
        self.microphone_menu.actions()[0].setIcon(QIcon('img/mic-disable.png'))
        
        self.layout_actions = {}
        layout_action_group = QActionGroup(self)
        for res in frame_size.keys():
            layout_action = layout_action_group.addAction(res)
            layout_action.setCheckable(True)
            layout_action.triggered.connect(lambda checked, res=res: self.video_list_widget.resize_widgets(res))
            if res == LAYOUT_RES:
                layout_action.setChecked(True)
            self.layout_menu.addAction(layout_action)
            self.layout_actions[res] = layout_action
            
        # Periodically refresh file list (every 5 seconds)
        self.file_refresh_timer = QTimer()
        self.file_refresh_timer.timeout.connect(self.server_conn.request_file_list)
        self.file_refresh_timer.start(5000)  # 5 seconds

            
        # === FILE TRANSFER SIGNAL CONNECTIONS ===
        self.server_conn.files_list_signal.connect(self.chat_widget.populate_download_menu)
        self.server_conn.start_download_signal.connect(self.chat_widget.start_file_transfer)
        self.server_conn.download_chunk_signal.connect(self.chat_widget.update_file_transfer)
        self.server_conn.finish_download_signal.connect(self.chat_widget.finish_file_transfer)

        # Upload (sender) progress signals
        self.server_conn.start_upload_signal.connect(self.chat_widget.start_upload_transfer)
        self.server_conn.upload_progress_signal.connect(self.chat_widget.update_upload_progress)
        self.server_conn.finish_upload_signal.connect(self.chat_widget.finish_upload_transfer)
        # when a new file is uploaded successfully, refresh file list for all
        self.server_conn.finish_upload_signal.connect(
            lambda _: self.server_conn.request_file_list()
        )


    
    def capture_and_send_screen(self):
        if not self.client.screen_sharing:
            return
        data = self.client.get_screen()
        if data is not None:
            msg = Message(self.client.name, POST, SCREEN, data)
            self.server_conn.send_msg(self.server_conn.main_socket, msg)
    
    def add_client(self, client):
        self.video_list_widget.add_client(client)
        if ENABLE_AUDIO:
            self.audio_threads[client.name] = AudioThread(client, self)
            self.audio_threads[client.name].start()
        if not client.current_device:
            self.chat_widget.add_client(client.name)
        # --- new join message ---
        join_msg = f"🟢 {client.name} joined the chat"
        self.chat_widget.add_msg("System", "All", join_msg)

    def remove_client(self, name: str):
        self.video_list_widget.remove_client(name)
        if ENABLE_AUDIO and name in self.audio_threads:
            self.audio_threads[name].connected = False
            self.audio_threads[name].wait()
            self.audio_threads.pop(name)
        self.chat_widget.remove_client(name)
        # --- new leave message ---
        leave_msg = f"🔴 {name} left the chat"
        self.chat_widget.add_msg("System", "All", leave_msg)

    def send_msg(self, data_type: str = TEXT):
        selected = self.chat_widget.selected_clients()
        if len(selected) == 0:
            QMessageBox.critical(self, "Error", "Select at least one client")
            return
        
        if data_type == TEXT:
            msg_text = self.chat_widget.get_text()
        elif data_type == FILE:
            filepath = self.chat_widget.get_file()
            if not filepath:
                return
            msg_text = os.path.basename(filepath)
        else:
            print(f"{data_type} data_type not supported")
            return
        
        if msg_text == "":
            QMessageBox.critical(self, "Error", f"{data_type} cannot be empty")
            return
        
        msg = Message(self.client.name, POST, data_type, data=msg_text, to_names=selected)
        self.server_conn.send_msg(self.server_conn.main_socket, msg)
        
        if data_type == FILE:
            send_file_thread = Worker(self.server_conn.send_file, filepath, selected)
            self.server_conn.threadpool.start(send_file_thread)
            msg_text = f"Sending {msg_text}..."

        self.chat_widget.add_msg("You", ", ".join(selected), msg_text)
    
    def add_msg(self, from_name: str, msg: str):
        self.chat_widget.add_msg(from_name, "You", msg)

    def toggle_camera(self):
        # flip local state & change menu text/icon
        self.client.camera_enabled = not self.client.camera_enabled
        if self.client.camera_enabled:
            self.camera_menu.actions()[0].setText("Disable")
            self.camera_menu.actions()[0].setIcon(QIcon('img/cam-disable.png'))
        else:
            self.camera_menu.actions()[0].setText("Enable")
            self.camera_menu.actions()[0].setIcon(QIcon('img/cam-enable.png'))

        # notify server/others about the new camera state
        msg = Message(self.client.name, POST, TEXT, {"camera_enabled": self.client.camera_enabled})
        self.server_conn.send_msg(self.server_conn.main_socket, msg)


    def toggle_microphone(self):
        self.client.microphone_enabled = not self.client.microphone_enabled
        if self.client.microphone_enabled:
            self.microphone_menu.actions()[0].setText("Disable")
            self.microphone_menu.actions()[0].setIcon(QIcon('img/mic-disable.png'))
        else:
            self.microphone_menu.actions()[0].setText("Enable")
            self.microphone_menu.actions()[0].setIcon(QIcon('img/mic-enable.png'))

        # notify server/others about the new microphone state
        msg = Message(self.client.name, POST, TEXT, {"microphone_enabled": self.client.microphone_enabled})
        self.server_conn.send_msg(self.server_conn.main_socket, msg)


    def toggle_screen_share(self):
        if self.screen_share_active:
            msg = Message(self.client.name, STOP_SHARE, SCREEN)
            self.server_conn.send_msg(self.server_conn.main_socket, msg)
            print("[INFO] Screen share stop requested")
        elif not self.other_sharing:
            msg = Message(self.client.name, START_SHARE, SCREEN)
            self.server_conn.send_msg(self.server_conn.main_socket, msg)
            print("[INFO] Screen share start requested")

    def on_screen_share_start(self, presenter_name):
        print(f"[INFO] Screen share started by {presenter_name}")
        self.current_presenter = presenter_name

        if presenter_name == self.client.name:
            # You are the presenter
            self.video_list_widget.add_screen_share(presenter_name, b'', is_presenter=True)
            self.client.screen_sharing = True
            self.screen_share_active = True
            self.screen_timer.start()
            self.chat_widget.share_button.setText("Stop Screen Share")
            self.chat_widget.share_button.setEnabled(True)
        else:
            # Another user is sharing
            self.video_list_widget.add_screen_share(presenter_name, b'')
            self.screen_share_active = False
            self.other_sharing = True
            self.chat_widget.share_button.setText("Other is Sharing")
            self.chat_widget.share_button.setEnabled(False)


    def on_screen_update(self, image_bytes):
        if self.current_presenter:
            if not image_bytes:
                # nothing to show
                print("[DEBUG] on_screen_update received empty image_bytes")
                self.video_list_widget.add_screen_share(self.current_presenter, b'')
                return
            self.video_list_widget.add_screen_share(self.current_presenter, image_bytes)


    def on_screen_share_stop(self):
        print("[INFO] Screen share stopped")
        self.current_presenter = None
        self.video_list_widget.remove_screen_share()

        if self.screen_share_active:
            # You stopped sharing
            self.client.screen_sharing = False
            self.screen_timer.stop()
            self.screen_share_active = False

        # Reset button for everyone
        self.other_sharing = False
        self.chat_widget.share_button.setText("Share Screen")
        self.chat_widget.share_button.setEnabled(True)


    def on_screen_share_reject(self):
        self.other_sharing = True
        self.chat_widget.share_button.setText("Other is Sharing")
        self.chat_widget.share_button.setEnabled(False)
        QMessageBox.warning(self, "Screen Sharing", "Screen sharing already active by another user")
