import os
import cv2
import pyaudio
import numpy as np
import sys
from PyQt6.QtCore import Qt, QThread, QTimer, QSize, QRunnable, pyqtSlot, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QImage, QPixmap, QActionGroup, QIcon, QFont, QAction
from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout, QDockWidget \
    , QLabel, QWidget, QListWidget, QListWidgetItem, QMessageBox \
    , QComboBox, QTextEdit, QLineEdit, QPushButton, QFileDialog \
    , QDialog, QMenu, QWidgetAction, QCheckBox, QStyleFactory, QGraphicsDropShadowEffect

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
        print("[INFO] ScreenCapturer initialized with integrated capture method")

    def capture(self):
        try:
            if sys.platform in ["win32", "darwin"]:
                screenshot = ig.grab()
            else:
                screenshot = ig.grab(backend=bkend)
            img = np.array(screenshot)
            if sys.platform not in ["win32", "darwin"]:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            else:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
            _, img_encoded = cv2.imencode('.jpg', img, encode_param)
            print("[INFO] Screen captured successfully")
            return img_encoded.tobytes()
        except Exception as e:
            print(f"[ERROR] Screen capture failed: {e}")
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
        self.init_ui()

    def init_ui(self):
        # Bottom resizable panel
        self.setMinimumHeight(200)
        self.setStyleSheet("border-radius: 12px; background-color: #1e1e2e; border: 2px solid #45475a;")

        self.presenter_label = QLabel("Screen Share by: None")
        self.presenter_label.setStyleSheet("color: #f9e2af; font-weight: bold;")
        self.presenter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.screen_viewer = QLabel()
        self.screen_viewer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_viewer.setStyleSheet(
            "border: none; background-color: #000000; border-radius: 12px;"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self.presenter_label)
        layout.addWidget(self.screen_viewer, 1)
        self.setLayout(layout)

    def show_share(self, presenter_name, image_bytes):
        self.presenter_name = presenter_name
        self.presenter_label.setText(f"Screen shared by: {presenter_name}")
        if image_bytes:
            try:
                image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
                if image is not None:
                    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                    h, w, ch = image.shape
                    bytes_per_line = ch * w
                    q_img = QImage(image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(q_img).scaled(
                        self.screen_viewer.size(), Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.screen_viewer.setPixmap(pixmap)
                    return
            except Exception as e:
                print(f"[ERROR] Failed to render screen share image: {e}")
        # Fallback text if no valid frame
        self.screen_viewer.setText("Waiting for screen data...")


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

    
    def add_screen_share(self, presenter_name, image_bytes):
        # Show only one screen share panel at the bottom
        if not self.screen_share_widget:
            self.screen_share_widget = ScreenShareWidget()
            self.parentWidget().layout().addWidget(self.screen_share_widget)
        self.screen_share_widget.show_share(presenter_name, image_bytes)

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


class ChatWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.clients_checkboxes = {}
        self.clients_menu_actions = {}
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
    
    def capture_and_send_screen(self):
        if not self.client.screen_sharing:
            return
        data = self.client.get_screen()
        if data is not None:
            msg = Message(self.client.name, POST, SCREEN, data)
            self.server_conn.send_msg(self.server_conn.main_socket, msg)
    
    def add_client(self, client):
        self.video_list_widget.add_client(client)
        self.layout_actions[LAYOUT_RES].setChecked(True)
        if ENABLE_AUDIO:
            self.audio_threads[client.name] = AudioThread(client, self)
            self.audio_threads[client.name].start()
        if not client.current_device:
            self.chat_widget.add_client(client.name)
    
    def remove_client(self, name: str):
        self.video_list_widget.remove_client(name)
        self.layout_actions[LAYOUT_RES].setChecked(True)
        if ENABLE_AUDIO and name in self.audio_threads:
            self.audio_threads[name].connected = False
            self.audio_threads[name].wait()
            self.audio_threads.pop(name)
            print(f"Audio Thread for {name} terminated")
        print(f"removing {name} chat...")
        self.chat_widget.remove_client(name)
        print(f"{name} removed")

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
        self.video_list_widget.add_screen_share(presenter_name, b'')

        if presenter_name == self.client.name:
            # You are the presenter
            self.client.screen_sharing = True
            self.screen_share_active = True
            self.screen_timer.start()
            self.chat_widget.share_button.setText("Stop Screen Share")
            self.chat_widget.share_button.setEnabled(True)
        else:
            # Another user is sharing
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
