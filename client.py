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

    # New signals to communicate file-related info to UI
    files_list_signal = pyqtSignal(list)  # emits list of file metadata
    start_download_signal = pyqtSignal(str, str, int, str)  # transfer_id, filename, size, from_name
    download_chunk_signal = pyqtSignal(str, bytes)  # transfer_id, chunk
    finish_download_signal = pyqtSignal(str)  # transfer_id

    # --- NEW: upload signals for sender-side UI ---
    start_upload_signal = pyqtSignal(str, str, int, tuple)   # upload_id, filename, total_bytes, to_names
    upload_progress_signal = pyqtSignal(str, int)           # upload_id, percent (0-100)
    finish_upload_signal = pyqtSignal(str)                  # upload_id
# --------------------------------------------------------------------

    
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
        """Send a file to server (server will store and make available to recipients).
           Allows screen sharing to continue smoothly by throttling send speed slightly."""
        import time
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath) if os.path.exists(filepath) else 0

        # generate a local upload id (client-side only) so the UI can display progress
        upload_id = f"upload_{filename}_{int(time.time()*1000)}"

        # Notify server about the filename (start of transfer)
        self.send_msg(self.main_socket, Message(self.name, POST, FILE, filename, to_names))

        # Emit start_upload_signal so sender UI creates an outgoing progress widget
        try:
            self.start_upload_signal.emit(upload_id, filename, filesize, to_names)
        except Exception:
            pass

        total_sent = 0
        last_percent_emitted = -1

        try:
            with open(filepath, 'rb') as f:
                while True:
                    data = f.read(SIZE - 1024)  # use slightly smaller chunks
                    if not data:
                        break

                    msg = Message(self.name, POST, FILE, data, to_names)
                    self.send_msg(self.main_socket, msg)
                    total_sent += len(data)

                    # yield briefly to avoid starving screen-share thread
                    time.sleep(0.002)

                    # compute percent and emit progress updates
                    percent = int((total_sent * 100) / (filesize or 1))
                    if percent != last_percent_emitted:
                        try:
                            self.upload_progress_signal.emit(upload_id, percent)
                        except Exception:
                            pass
                        last_percent_emitted = percent

            # send end marker
            self.send_msg(self.main_socket, Message(self.name, POST, FILE, None, to_names))

            # notify finish
            try:
                self.finish_upload_signal.emit(upload_id)
            except Exception:
                pass

            # Optional confirmation in chat
            self.add_msg_signal.emit(self.name, f"File {filename} uploaded successfully.")

        except Exception as e:
            # handle error
            self.add_msg_signal.emit(self.name, f"Error sending file: {e}")
            try:
                self.finish_upload_signal.emit(upload_id)
            except Exception:
                pass



    def request_file_list(self):
        """Ask server for files available for this client"""
        msg = Message(self.name, GET_FILES)
        self.send_msg(self.main_socket, msg)

    def request_download(self, transfer_id: str):
        """Ask server to stream the file with transfer_id to this client"""
        msg = Message(self.name, DOWNLOAD_FILE, FILE, {"transfer_id": transfer_id})
        self.send_msg(self.main_socket, msg)

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
                    # treat non-media messages from new senders as creating a client entry
                    all_clients[client_name] = Client(client_name)
                    self.add_client_signal.emit(all_clients[client_name])
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

            elif msg.data_type == FILE and msg.request == POST:
                # Deprecated: peer-to-peer direct file sending.
                # Skip to avoid duplicate empty file creation.
                return

            else:
                # Unknown data_type for POST
                pass

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

        # NEW: server responds with a FILE_LIST (list of files available for this client)
        elif msg.request == FILE_LIST and msg.data_type == FILE:
            # msg.data is a list of dict metadata
            file_list = msg.data if isinstance(msg.data, list) else []
            # forward to UI
            self.files_list_signal.emit(file_list)

        # NEW: server streams file chunks using FILE_CHUNK / FILE with different payloads
        elif msg.request == FILE_CHUNK and msg.data_type == FILE:
            # msg.data may be:
            #  - dict metadata: {"transfer_id","filename","size","from"}
            #  - bytes chunk
            #  - None == end of stream
            if isinstance(msg.data, dict):
                meta = msg.data
                transfer_id = meta.get("transfer_id")
                filename = meta.get("filename")
                size = meta.get("size", 0)
                from_name = meta.get("from", "")
                # notify UI to create a download widget
                self.start_download_signal.emit(transfer_id, filename, size, from_name)
            elif msg.data is None:
                # finish
                # we don't have a transfer id in this message; but start_download_signal used by UI to
                # map future chunk events. To correlate, chunks are accompanied by start signal first.
                # We'll send a generic finish signal (UI should map by last active transfer).
                # To be robust, client GUI should track transfer ids it started and match finish order.
                # Here we just emit finish without id (UI will handle per-implementation).
                # But better: the server streams only to the requester, so UI can assume the single active incoming.
                # We'll emit finish_download_signal with an empty transfer id (UI should adapt).
                self.finish_download_signal.emit("")
            else:
                # bytes chunk — we need transfer id, but server does not include it in chunk messages to save space.
                # To be robust, server could have sent transfer_id with every chunk; if not, we emit chunk with empty id.
                # For simplicity, we emit chunk with empty id; GUI should use the last started transfer id.
                chunk = msg.data
                self.download_chunk_signal.emit("", chunk)

        elif msg.request == GET_FILES:
            # not expected from server to client
            pass

        elif msg.request == DOWNLOAD_FILE:
            # not expected from server to client
            pass

        elif msg.request == START_SHARE:
            # duplicate handling guard
            pass

        else:
            # any other messages from server (text notifications)
            if msg.data_type == TEXT and msg.from_name == SERVER:
                self.add_msg_signal.emit("System", str(msg.data))
            else:
                # fallback: emit text
                try:
                    self.add_msg_signal.emit(msg.from_name, str(msg.data))
                except Exception:
                    pass

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

