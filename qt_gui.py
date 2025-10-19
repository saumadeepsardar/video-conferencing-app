import os
import cv2
import pyaudio
import numpy as np
from PyQt6.QtCore import Qt, QThread, QTimer, QSize, QRunnable, pyqtSlot, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QImage, QPixmap, QActionGroup, QIcon, QFont
from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout, QDockWidget \
    , QLabel, QWidget, QListWidget, QListWidgetItem, QMessageBox \
    , QComboBox, QTextEdit, QLineEdit, QPushButton, QFileDialog \
    , QDialog, QMenu, QWidgetAction, QCheckBox, QStyleFactory, QGraphicsDropShadowEffect

from constants import *

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
    # '1080p': (1920, 1080)
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

# Modern Stylesheet (box-shadow removed; shadows handled programmatically with QGraphicsDropShadowEffect)
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


class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        # Store constructor arguments (re-used for processing)
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
        # if this is the current client, then don't play audio
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
        for index in range(3):  # Try indices 0, 1, 2
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
        self.sct = None
        try:
            import mss
            self.sct = mss.mss()
            # Force initialization in main thread to avoid threading issues
            _ = self.sct.monitors
            print("[INFO] ScreenCapturer initialized successfully")
        except ImportError:
            print("[ERROR] mss library not installed. Install with 'pip install mss' for screen sharing.")
            self.sct = None
        except Exception as e:
            print(f"[ERROR] MSS initialization failed: {e}")
            self.sct = None

    def capture(self):
        if self.sct is None:
            print("[ERROR] ScreenCapturer not available")
            return None
        try:
            screenshot = self.sct.grab(self.sct.monitors[1])  # Primary monitor
            img = np.array(screenshot)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            # Compress
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
        # self.resize(FRAME_WIDTH, FRAME_HEIGHT)
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
            # replace bottom center part of the frame with nomic frame
            nomic_h, nomic_w, _ = NOMIC_FRAME.shape
            x, y = FRAME_WIDTH//2 - nomic_w//2, FRAME_HEIGHT - 50
            frame[y:y+nomic_h, x:x+nomic_w] = NOMIC_FRAME.copy()

        h, w, ch = frame.shape
        bytes_per_line = ch * w
        q_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self.video_viewer.setPixmap(QPixmap.fromImage(q_img))


class VideoListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_items = {}
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
        item.setFlags(item.flags() & ~(Qt.ItemFlag.ItemIsSelectable|Qt.ItemFlag.ItemIsEnabled))
        if client.current_device:
            self.insertItem(0, item)
        else:
            self.addItem(item)
        # item.setSizeHint(video_widget.sizeHint())
        item.setSizeHint(QSize(FRAME_WIDTH, FRAME_HEIGHT))
        self.setItemWidget(item, video_widget)
        self.all_items[client.name] = item
        self.resize_widgets()
    
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
            self.item(i).setSizeHint(QSize(FRAME_WIDTH, FRAME_HEIGHT))

    def remove_client(self, name: str):
        self.takeItem(self.row(self.all_items[name]))
        self.all_items.pop(name)
        self.resize_widgets()


class ChatWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        # self.resize(800, 600)
        self.layout = QVBoxLayout()
        self.layout.setSpacing(10)
        self.setLayout(self.layout)

        self.central_widget = QTextEdit(self)
        self.central_widget.setReadOnly(True)
        self.layout.addWidget(self.central_widget)

        self.clients_menu = QMenu("Clients", self)
        self.clients_menu.aboutToShow.connect(self.resize_clients_menu)
        self.clients_checkboxes = {}
        self.clients_menu_actions = {}

        self.select_all_checkbox, _ = self.add_client("") # Select All Checkbox
        self.clients_menu.addSeparator()

        self.clients_button = QPushButton("Clients", self)
        self.clients_button.setStyleSheet("background-color: #f9e2af; color: #1e1e2e;")
        self.clients_button.setMenu(self.clients_menu)
        self.layout.addWidget(self.clients_button)

        self.share_button = QPushButton("Share Screen", self)
        self.share_button.setStyleSheet("background-color: #f9e2af; color: #1e1e2e;")
        self.layout.addWidget(self.share_button)

        self.file_button = QPushButton("Send File", self)
        self.file_button.setStyleSheet("background-color: #f5c2e7; color: #1e1e2e;")
        self.layout.addWidget(self.file_button)

        self.send_layout = QHBoxLayout()
        self.send_layout.setSpacing(10)
        self.layout.addLayout(self.send_layout)

        self.line_edit = QLineEdit(self)
        self.line_edit.setPlaceholderText("Type message here...")
        self.line_edit.setStyleSheet("QLineEdit {border: 2px solid #9399b2; background-color: #313244;}"
                                     "QLineEdit:focus {border: 2px solid #89b4fa;}")
        self.send_layout.addWidget(self.line_edit)

        self.send_button = QPushButton("Send", self)
        self.send_button.setStyleSheet("background-color: #a6e3a1; color: #1e1e2e; min-width: 60px;")
        self.send_layout.addWidget(self.send_button)

        self.layout.addSpacing(30)

        self.end_button = QPushButton("End Call", self)
        self.end_button.setStyleSheet("QPushButton {background-color: #f38ba8; color: #1e1e2e; font-weight: bold;}")
        self.layout.addWidget(self.end_button)
    
    def add_client(self, name: str):
        checkbox = QCheckBox(name, self)
        checkbox.setChecked(True)
        checkbox.setStyleSheet("QCheckBox { color: #cdd6f4; spacing: 5px; }")
        action_widget = QWidgetAction(self)
        action_widget.setDefaultWidget(checkbox)
        self.clients_menu.addAction(action_widget)

        if name == "": # Select All Checkbox
            checkbox.setText("Select All")
            checkbox.setStyleSheet("QCheckBox { color: #f9e2af; font-weight: bold; }")
            checkbox.stateChanged.connect(
                lambda state: self.on_checkbox_click(state, is_select_all=True)
            )
            return checkbox, action_widget
        
        checkbox.stateChanged.connect(
            lambda state: self.on_checkbox_click(state)
        )
        self.clients_checkboxes[name] = checkbox
        self.clients_menu_actions[name] = action_widget
    
    def remove_client(self, name: str):
        self.clients_menu.removeAction(self.clients_menu_actions[name])
        self.clients_menu_actions.pop(name)
        self.clients_checkboxes.pop(name)

    def resize_clients_menu(self):
        self.clients_menu.setMinimumWidth(self.clients_button.width())
    
    def on_checkbox_click(self, is_checked: bool, is_select_all: bool = False):
        if is_select_all:
            for client_checkbox in self.clients_checkboxes.values():
                client_checkbox.blockSignals(True)
                client_checkbox.setChecked(is_checked)
                client_checkbox.blockSignals(False)
        else:
            if not is_checked:
                self.select_all_checkbox.blockSignals(True)
                self.select_all_checkbox.setChecked(False)
                self.select_all_checkbox.blockSignals(False)
    
    def selected_clients(self):
        selected = []
        for name, checkbox in self.clients_checkboxes.items():
            if checkbox.isChecked():
                selected.append(name)
        return tuple(selected)

    def get_file(self):
        file_path = QFileDialog.getOpenFileName(None, "Select File", options= QFileDialog.Option.DontUseNativeDialog)[0]
        return file_path

    def get_text(self):
        text = self.line_edit.text()
        self.line_edit.clear()
        return text
    
    def add_msg(self, from_name: str, to_name: str, msg: str):
        self.central_widget.append(f"<span style='color: #89b4fa'>[{from_name}]</span> <span style='color: #f9e2af'>→ {to_name}</span> <span style='color: #cdd6f4'>{msg}</span>")


class ScreenShareWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.hide()

        self.presenter_label = QLabel("Screen Share by: ")
        self.layout.addWidget(self.presenter_label, alignment=Qt.AlignmentFlag.AlignCenter)
        self.screen_viewer = QLabel()
        self.screen_viewer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_viewer.setStyleSheet("border: 2px solid #a6e3a1; border-radius: 12px; background-color: #313244;")
        self.layout.addWidget(self.screen_viewer)
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def init_ui(self):
        self.setStyleSheet("background-color: rgba(30, 30, 46, 200); border-radius: 16px;")
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(Qt.GlobalColor.black)
        shadow.setOffset(0, 5)
        self.setGraphicsEffect(shadow)

    def show_share(self, presenter_name, image_bytes):
        self.presenter_label.setText(f"Screen Share by: <span style='color: #f9e2af'>{presenter_name}</span>")
        image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = image.shape
        bytes_per_line = ch * w
        q_img = QImage(image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        self.screen_viewer.setPixmap(QPixmap.fromImage(q_img).scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        if not self.isVisible():
            self.setWindowOpacity(0)
            self.show()
            self.raise_()
            self.animation.setStartValue(0)
            self.animation.setEndValue(1)
            self.animation.start()
        else:
            self.animation.setStartValue(self.windowOpacity())
            self.animation.setEndValue(1)
            self.animation.start()

    def hide_share(self):
        self.animation.setStartValue(self.windowOpacity())
        self.animation.setEndValue(0)
        self.animation.finished.connect(self.hide)
        self.animation.start()


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
        self.current_presenter = None

        self.server_conn.add_client_signal.connect(self.add_client)
        self.server_conn.remove_client_signal.connect(self.remove_client)
        self.server_conn.add_msg_signal.connect(self.add_msg)
        self.server_conn.screen_share_start_signal.connect(self.on_screen_share_start)
        self.server_conn.screen_share_stop_signal.connect(self.on_screen_share_stop)
        self.server_conn.screen_update_signal.connect(self.on_screen_update)

        self.login_dialog = LoginDialog(self)
        if not self.login_dialog.exec():
            exit()
        
        self.server_conn.name = self.login_dialog.get_name()
        self.server_conn.start()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Video Conferencing")
        self.setGeometry(0, 0, 1920, 1000)
        self.setStyleSheet(MODERN_STYLESHEET)

        # Create a central widget with a layout
        self.central_widget = QWidget()
        self.central_layout = QVBoxLayout()
        self.central_widget.setLayout(self.central_layout)
        self.setCentralWidget(self.central_widget)
        
        self.video_list_widget = VideoListWidget()
        self.central_layout.addWidget(self.video_list_widget)
        
        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,0.5);")
        self.overlay_layout = QVBoxLayout(self.overlay)
        self.overlay_layout.setContentsMargins(50, 50, 50, 50)
        self.overlay.setLayout(self.overlay_layout)
        self.screen_share_widget = ScreenShareWidget(self)
        self.overlay_layout.addWidget(self.screen_share_widget)
        self.central_layout.addWidget(self.overlay)
        self.overlay.hide()
        
        self.sidebar = QDockWidget("Chat", self)
        self.sidebar.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.chat_widget = ChatWidget()
        self.sidebar.setWidget(self.chat_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.sidebar)
        self.chat_widget.send_button.clicked.connect(lambda: self.send_msg(TEXT))
        self.chat_widget.line_edit.returnPressed.connect(lambda: self.send_msg(TEXT))
        self.chat_widget.file_button.clicked.connect(lambda: self.send_msg(FILE))
        self.chat_widget.share_button.clicked.connect(self.toggle_screen_share)
        self.chat_widget.end_button.clicked.connect(self.close)

        # Screen sharing timer (runs in main thread)
        self.screen_timer = QTimer()
        self.screen_timer.timeout.connect(self.capture_and_send_screen)
        self.screen_timer.setInterval(500)  # 2 FPS for screen sharing
        
        # menus for camera and microphone toggle
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
        if ENABLE_AUDIO:
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
        if self.client.camera_enabled:
            self.camera_menu.actions()[0].setText("Enable")
            self.camera_menu.actions()[0].setIcon(QIcon('img/cam-enable.png'))
        else:
            self.camera_menu.actions()[0].setText("Disable")
            self.camera_menu.actions()[0].setIcon(QIcon('img/cam-disable.png'))
        self.client.camera_enabled = not self.client.camera_enabled

    def toggle_microphone(self):
        if self.client.microphone_enabled:
            self.microphone_menu.actions()[0].setText("Enable")
            self.microphone_menu.actions()[0].setIcon(QIcon('img/mic-enable.png'))
        else:
            self.microphone_menu.actions()[0].setText("Disable")
            self.microphone_menu.actions()[0].setIcon(QIcon('img/mic-disable.png'))
        self.client.microphone_enabled = not self.client.microphone_enabled

    def toggle_screen_share(self):
        if not self.screen_share_active:
            # Request start
            msg = Message(self.client.name, START_SHARE)
            self.server_conn.send_msg(self.server_conn.main_socket, msg)
            print("[INFO] Screen share start requested")
        else:
            # Request stop
            msg = Message(self.client.name, STOP_SHARE)
            self.server_conn.send_msg(self.server_conn.main_socket, msg)
            print("[INFO] Screen share stop requested")

    def on_screen_share_start(self, presenter_name):
        print(f"[INFO] Screen share started by {presenter_name}")
        self.current_presenter = presenter_name
        if presenter_name == self.client.name:
            # I am the presenter, start timer
            self.client.screen_sharing = True
            self.screen_timer.start()
            self.screen_share_active = True
            self.chat_widget.share_button.setText("Stop Screen Share")
            print("[INFO] Local screen sharing started")
        else:
            self.overlay.show()
            print("[INFO] Remote screen sharing started")

    def on_screen_share_stop(self):
        print("[INFO] Screen share stopped")
        self.current_presenter = None
        self.overlay.hide()
        if self.screen_share_active:
            self.client.screen_sharing = False
            self.screen_timer.stop()
            self.screen_share_active = False
            self.chat_widget.share_button.setText("Share Screen")
            print("[INFO] Local screen sharing stopped")

    def on_screen_update(self, image_bytes):
        if self.current_presenter and self.current_presenter != self.client.name:
            self.screen_share_widget.show_share(self.current_presenter, image_bytes)
