# client.py
import os
import time
import sys
import socket
import pickle
from collections import defaultdict

from PyQt6.QtCore import QThreadPool, QRunnable, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QMessageBox
from qt_gui import MainWindow, Camera, Microphone, Worker, ScreenCapturer

from constants import *

IP = socket.gethostbyname(socket.gethostname())
# IP = "192.168.12.1"
VIDEO_ADDR = (IP, VIDEO_PORT)
AUDIO_ADDR = (IP, AUDIO_PORT)


class Client:
    def __init__(self, name: str, current_device = False):
        self.name = name
        self.current_device = current_device

        self.video_frame = None
        self.audio_data = None
        self.screen_image = None

        if self.current_device:
            self.camera = Camera()
            self.microphone = Microphone()
            self.screen_capturer = ScreenCapturer()
        else:
            self.camera = None
            self.microphone = None
            self.screen_capturer = None
        
        self.camera_enabled = True
        self.microphone_enabled = True
        self.screen_sharing = False

    def get_video(self):
        if not self.camera_enabled:
            self.video_frame = None
            return None

        if self.camera is not None:
            self.video_frame = self.camera.get_frame()

        return self.video_frame
    
    def get_audio(self):
        if not self.microphone_enabled:
            self.audio_data = None
            return None

        if self.microphone is not None:
            self.audio_data = self.microphone.get_data()

        return self.audio_data

    def get_screen(self):
        if not self.screen_sharing or self.screen_capturer is None:
            self.screen_image = None
            return None
        self.screen_image = self.screen_capturer.capture()
        return self.screen_image


class ServerConnection(QThread):
    add_client_signal = pyqtSignal(Client)
    remove_client_signal = pyqtSignal(str)
    add_msg_signal = pyqtSignal(str, str)
    screen_share_start_signal = pyqtSignal(str)
    screen_share_stop_signal = pyqtSignal()
    screen_update_signal = pyqtSignal(bytes)
    screen_share_reject_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.threadpool = None
        self.name = None  # Set after login

        self.main_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.audio_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.connected = False
        self.recieving_filename = None
        self.screen_broadcast_thread = None

    def run(self):
        self.init_conn()
        if not self.connected:
            return
        self.threadpool = QThreadPool()
        self.start_conn_threads()
        self.start_broadcast_threads()

        self.add_client_signal.emit(client)

        while self.connected:
            time.sleep(0.1)  # Prevent tight loop
        self.disconnect_server()

    def init_conn(self):
        try:
            self.main_socket.connect((IP, MAIN_PORT))

            self.main_socket.send_bytes(self.name.encode())
            conn_status = self.main_socket.recv_bytes().decode()
            if conn_status != OK:
                QMessageBox.critical(None, "Error", conn_status)
                self.main_socket.close()
                window.close()
                self.connected = False
                return
            
            self.send_msg(self.video_socket, Message(self.name, ADD, VIDEO))
            self.send_msg(self.audio_socket, Message(self.name, ADD, AUDIO))

            self.connected = True
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}")
            self.connected = False
    
    def start_conn_threads(self):
        self.main_conn_thread = Worker(self.handle_conn, self.main_socket, TEXT)
        self.threadpool.start(self.main_conn_thread)

        self.video_conn_thread = Worker(self.handle_conn, self.video_socket, VIDEO)
        self.threadpool.start(self.video_conn_thread)

        self.audio_conn_thread = Worker(self.handle_conn, self.audio_socket, AUDIO)
        self.threadpool.start(self.audio_conn_thread)

    def start_broadcast_threads(self):
        self.video_broadcast_thread = Worker(self.media_broadcast_loop, self.video_socket, VIDEO)
        self.threadpool.start(self.video_broadcast_thread)

        self.audio_broadcast_thread = Worker(self.media_broadcast_loop, self.audio_socket, AUDIO)
        self.threadpool.start(self.audio_broadcast_thread)
    
    def disconnect_server(self):
        if self.connected:
            self.send_msg(self.main_socket, Message(self.name, DISCONNECT))
            self.main_socket.disconnect()
        self.connected = False
    
    def send_msg(self, conn: socket.socket, msg: Message):
        msg_bytes = pickle.dumps(msg)
        # print("Sending..", len(msg_bytes))
        try:
            if msg.data_type == VIDEO:
                conn.sendto(msg_bytes, VIDEO_ADDR)
            elif msg.data_type == AUDIO:
                conn.sendto(msg_bytes, AUDIO_ADDR)
            else:
                conn.send_bytes(msg_bytes)
        except (BrokenPipeError, ConnectionResetError, OSError):
            print(f"[ERROR] Connection not present")
            self.connected = False
    
    def send_file(self, filepath: str, to_names: tuple[str]):
        filename = os.path.basename(filepath)
        with open(filepath, 'rb') as f:
            data = f.read(SIZE)
            while data:
                msg = Message(self.name, POST, FILE, data, to_names)
                self.send_msg(self.main_socket, msg)
                data = f.read(SIZE)
            msg = Message(self.name, POST, FILE, None, to_names)
            self.send_msg(self.main_socket, msg)
        self.add_msg_signal.emit(self.name, f"File {filename} sent.")
    
    def media_broadcast_loop(self, conn: socket.socket, media: str):
        while self.connected:
            if media == VIDEO:
                data = client.get_video()
            elif media == AUDIO:
                data = client.get_audio()
            else:
                print(f"[ERROR] Invalid media type")
                break
            if data is None:
                time.sleep(1/30)
                continue
            msg = Message(self.name, POST, media, data)
            self.send_msg(conn, msg)
            time.sleep(1/30)  # ~30 FPS for video/audio

    def handle_conn(self, conn: socket.socket, media: str):
        while self.connected:
            if media in [VIDEO, AUDIO]:
                msg_bytes, _ = conn.recvfrom(MEDIA_SIZE[media])
            else:
                msg_bytes = conn.recv_bytes()
            if not msg_bytes:
                self.connected = False
                break
            try:
                msg = pickle.loads(msg_bytes)
            except pickle.UnpicklingError:
                print(f"[{self.name}] [{media}] [ERROR] UnpicklingError")
                continue

            if msg.request == DISCONNECT:
                self.connected = False
                break
            try:
                self.handle_msg(msg)
            except Exception as e:
                print(f"[{self.name}] [{media}] [ERROR] {e}")
                continue

    def handle_msg(self, msg: Message):
        global all_clients
        client_name = msg.from_name
        if msg.request == POST:
            if msg.data_type == TEXT and client_name == SERVER:
                if msg.data == "Screen sharing already active by another user":
                    self.screen_share_reject_signal.emit()
                    return
            if client_name not in all_clients:
                if msg.data_type in [VIDEO, AUDIO]:
                    all_clients[client_name] = Client(client_name)
                    self.add_client_signal.emit(all_clients[client_name])
                else:
                    print(f"[{self.name}] [ERROR] Invalid client name {client_name}: {msg}")
                    return
            if msg.data_type == VIDEO:
                all_clients[client_name].video_frame = msg.data
            elif msg.data_type == AUDIO:
                all_clients[client_name].audio_data = msg.data
            elif msg.data_type == SCREEN:
                self.screen_update_signal.emit(msg.data)
            if msg.data_type == TEXT:
                # special status update (camera / microphone) sent as dict
                if isinstance(msg.data, dict):
                    status = msg.data
                    # ensure client exists
                    if client_name not in all_clients:
                        all_clients[client_name] = Client(client_name)
                        self.add_client_signal.emit(all_clients[client_name])
                    c = all_clients[client_name]
                    if 'camera_enabled' in status:
                        c.camera_enabled = bool(status['camera_enabled'])
                        # if camera is off, clear last frame
                        if not c.camera_enabled:
                            c.video_frame = None
                    if 'microphone_enabled' in status:
                        c.microphone_enabled = bool(status['microphone_enabled'])
                        if not c.microphone_enabled:
                            c.audio_data = None
                    # optionally show a small system message
                    self.add_msg_signal.emit(client_name, f"Status updated: {status}")
                else:
                    # legacy / regular chat text
                    self.add_msg_signal.emit(client_name, msg.data)

            elif msg.data_type == FILE:
                if type(msg.data) == str:
                    if os.path.exists(msg.data): # create copy
                        filename, ext = os.path.splitext(msg.data)
                        i = 1
                        while os.path.exists(f"{filename}({i}){ext}"):
                            i += 1
                        msg.data = f"{filename}({i}){ext}"
                    self.recieving_filename = msg.data
                    with open(self.recieving_filename, 'wb') as f:
                        pass
                elif msg.data is None:
                    self.add_msg_signal.emit(client_name, f"File {self.recieving_filename} recieved.")
                    self.recieving_filename = None
                else:
                    with open(self.recieving_filename, 'ab') as f:
                        f.write(msg.data)
            else:
                print(f"[{self.name}] [ERROR] Invalid data type {msg.data_type}")
        elif msg.request == ADD:
            if client_name not in all_clients:
                all_clients[client_name] = Client(client_name)
                self.add_client_signal.emit(all_clients[client_name])
        elif msg.request == RM:
            if client_name not in all_clients:
                print(f"[{self.name}] [ERROR] Invalid client name {client_name}")
                return
            self.remove_client_signal.emit(client_name)
            all_clients.pop(client_name)
        elif msg.request == START_SHARE:
            self.screen_share_start_signal.emit(msg.data)
        elif msg.request == STOP_SHARE:
            self.screen_share_stop_signal.emit()

client = Client("You", current_device=True)

all_clients = defaultdict(lambda: Client(""))

if __name__ == "__main__":
    app = QApplication(sys.argv)

    server_conn = ServerConnection()
    window = MainWindow(client, server_conn)
    window.show()

    status_code = app.exec()
    server_conn.disconnect_server()
    os._exit(status_code)
