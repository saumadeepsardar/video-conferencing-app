import socket
import struct
import pickle
from dataclasses import astuple, dataclass
import time

# Ports
PORT = 53535
MAIN_PORT = 53530
VIDEO_PORT = 53531
AUDIO_PORT = 53532
SIZE = 1024

SERVER = 'SERVER'
OK = 'OK'

# Requests
GET = 'GET'
POST = 'POST'
ADD = 'ADD'
RM = 'RM'
START_SHARE = 'START_SHARE'
STOP_SHARE = 'STOP_SHARE'
DISCONNECT = 'QUIT!'

# File-related requests
GET_FILES = 'GET_FILES'          # Client asks server for available files for that client
DOWNLOAD_FILE = 'DOWNLOAD_FILE'  # Client asks server to start sending a file
FILE_LIST = 'FILE_LIST'          # Server sends list of files (metadata)
FILE_CHUNK = 'FILE_CHUNK'        # Server sends file chunks (or metadata start)

# Data types
VIDEO = 'Video'
AUDIO = 'Audio'
TEXT = 'Text'
FILE = 'File'
SCREEN = 'Screen'

MEDIA_SIZE = {VIDEO: 65536, AUDIO: 8192}  # 64KB video, 8KB audio - balanced for stability

# --- socket helpers (send/recv with length prefix) ---
def send_bytes(self, msg: bytes):
    # Prefix each message with a 4-byte length (network byte order)
    try:
        packet = struct.pack('>I', len(msg)) + msg
        self.sendall(packet)
    except (BrokenPipeError, ConnectionResetError, OSError):
        # Connection closed, raise silently
        raise
    except Exception as e:
        print(f"[send_bytes ERROR] {e}")
        raise

def recv_bytes(self):
    # Read message length and unpack it into an integer
    raw_msglen = self.recvall(4)
    if not raw_msglen:
        return b''
    msglen = struct.unpack('>I', raw_msglen)[0]
    # Read the message data
    return self.recvall(msglen)

def recvall(self, n):
    # Helper function to recv n bytes or return b'' if EOF is hit
    data = bytearray()
    while len(data) < n:
        try:
            packet = self.recv(n - len(data))
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Connection closed, return empty bytes silently
            return b''
        if not packet:
            return b''
        data.extend(packet)
    return bytes(data)

def disconnect(self):
    msg = Message(SERVER, DISCONNECT)
    try:
        self.send_bytes(pickle.dumps(msg))
    except (BrokenPipeError, ConnectionResetError, OSError):
        print(f"[ERROR] Connection not present")
    try:
        self.close()
    except Exception:
        pass

# Monkey-patch socket methods
socket.socket.send_bytes = send_bytes
socket.socket.recv_bytes = recv_bytes
socket.socket.recvall = recvall
socket.socket.disconnect = disconnect

# --- Message dataclass ---
@dataclass
class Message:
    from_name: str
    request: str
    data_type: str = None
    data: any = None
    to_names: tuple[str] = None

    def __str__(self):
        if self.data_type in [VIDEO, AUDIO, SCREEN]:
            data = ""
        else:
            data = self.data
        return f"[{self.from_name}] {self.request}:{self.data_type} -> {self.to_names} {data}"

    def __iter__(self):
        return iter(astuple(self))
    
    def __getitem__(self, keys):
        return iter(getattr(self, k) for k in keys)

