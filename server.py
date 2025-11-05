# server.py
import socket
import threading
import time
import os
import traceback
import pickle
from dataclasses import dataclass, field
from constants import *

IP = ''
clients = {}
current_presenter = None
video_conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
audio_conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
media_conns = {VIDEO: video_conn, AUDIO: audio_conn}

# Directory to store uploaded files
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def cleanup_empty_files():
    """Remove any 0-byte files from the data directory"""
    if not os.path.exists(DATA_DIR):
        return
    
    for root, dirs, files in os.walk(DATA_DIR):
        for file in files:
            filepath = os.path.join(root, file)
            try:
                if os.path.getsize(filepath) == 0:
                    os.remove(filepath)
            except (OSError, FileNotFoundError):
                pass

def cleanup_duplicate_files():
    """Remove duplicate files based on name, size, and content hash"""
    if not os.path.exists(DATA_DIR):
        return
    
    import hashlib
    file_hashes = {}
    
    for root, dirs, files in os.walk(DATA_DIR):
        for file in files:
            filepath = os.path.join(root, file)
            try:
                if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                    continue
                    
                # Calculate file hash
                with open(filepath, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
                
                # Create a key based on filename and size
                file_key = f"{file}_{os.path.getsize(filepath)}"
                
                if file_key in file_hashes:
                    # Check if hash matches (same content)
                    if file_hashes[file_key]['hash'] == file_hash:
                        # Duplicate found, remove the newer file
                        if os.path.getctime(filepath) > os.path.getctime(file_hashes[file_key]['path']):
                            os.remove(filepath)
                        else:
                            os.remove(file_hashes[file_key]['path'])
                            file_hashes[file_key] = {'path': filepath, 'hash': file_hash}
                    else:
                        # Same name/size but different content, keep both
                        file_hashes[file_key] = {'path': filepath, 'hash': file_hash}
                else:
                    file_hashes[file_key] = {'path': filepath, 'hash': file_hash}
                    
            except (OSError, FileNotFoundError, PermissionError):
                pass

# Keep an index of saved files per recipient:
# files_index[recipient] = list of dicts: { "transfer_id": str, "filename": str, "path": str, "size": int, "from": str, "timestamp": float }
files_index: dict[str, list] = {}

# Temporary open file handles for ongoing transfers:
# active_transfers[(from_name, filename, transfer_id)] = { recipient_name: file_obj, ... }
active_transfers: dict[tuple, dict] = {}

def safe_filename(directory: str, filename: str) -> str:
    """Return a unique filename inside directory"""
    base, ext = os.path.splitext(filename)
    candidate = filename
    i = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{base}({i}){ext}"
        i += 1
    return candidate


# --- add this helper near top of file ---
def valid_file(path: str) -> bool:
    """Check that file exists and has non-zero size"""
    try:
        return os.path.exists(path) and os.path.getsize(path) > 0
    except Exception:
        return False


@dataclass
class Client:
    name: str
    main_conn: socket.socket
    connected: bool
    media_addrs: dict = field(default_factory=lambda: {VIDEO: None, AUDIO: None})

    def send_msg(self, from_name: str, request: str, data_type: str = None, data: any = None):
        msg = Message(from_name, request, data_type, data)
        try:
            if data_type in [VIDEO, AUDIO]:
                addr = self.media_addrs.get(data_type, None)
                if addr is None:
                    return
                # Use protocol 2 for better cross-platform compatibility
                media_conns[data_type].sendto(pickle.dumps(msg, protocol=2), addr)
            else:
                self.main_conn.send_bytes(pickle.dumps(msg, protocol=2))
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"[{self.name}] [ERROR] Connection error: {e}")
            self.connected = False

def broadcast_msg(from_name: str, request: str, data_type: str = None, data: any = None):
    all_clients = tuple(clients.values())
    for client in all_clients:
        if client.name == from_name:
            continue
        client.send_msg(from_name, request, data_type, data)

def multicast_msg(from_name: str, request: str, to_names: tuple[str], data_type: str = None, data: any = None):
    if not to_names:
        broadcast_msg(from_name, request, data_type, data)
        return
    for name in to_names:
        if name not in clients:
            continue
        clients[name].send_msg(from_name, request, data_type, data)

def media_server(media: str, port: int):
    conn = media_conns[media]
    conn.bind((IP, port))
    print(f"[LISTENING] {media} Server is listening on {IP}:{port}")
    while True:
        try:
            msg_bytes, addr = conn.recvfrom(MEDIA_SIZE[media])
        except OSError as e:
            if "10040" in str(e) or "message larger than" in str(e).lower():
                # Datagram too large, skip it
                print(f"[{media}] Skipping oversized packet")
                continue
            else:
                print(f"[{media}] Network error: {e}")
                continue
        except Exception as e:
            print(f"[{media}] Receive error: {e}")
            continue
            
        try:
            msg: Message = pickle.loads(msg_bytes)
        except (pickle.UnpicklingError, pickle.PickleError, EOFError, ValueError) as e:
            print(f"[{addr}] [{media}] [ERROR] Pickle error: {e}")
            continue
            
        if msg.request == ADD:
            client = clients[msg.from_name]
            client.media_addrs[media] = addr
            pass  # Client registered
        else:
            pass  # Broadcasting media
            broadcast_msg(msg.from_name, msg.request, msg.data_type, msg.data)

def ensure_files_index_for(recipient: str):
    if recipient not in files_index:
        files_index[recipient] = []

def add_file_index(recipient: str, filename: str, path: str, size: int, from_name: str, transfer_id: str):
    ensure_files_index_for(recipient)
    
    # Check if this transfer_id already exists for this recipient to prevent duplicates
    for existing in files_index[recipient]:
        if existing["transfer_id"] == transfer_id and existing["filename"] == filename:
            # Update existing entry instead of creating duplicate
            existing["size"] = size
            existing["timestamp"] = time.time()
            existing["path"] = path  # Update path in case it changed
            return
    
    # Also check for duplicate filenames with different transfer_ids (same file uploaded multiple times)
    for existing in files_index[recipient]:
        if existing["filename"] == filename and existing["from"] == from_name and existing["size"] == size:
            # This looks like a duplicate file, don't add it
            return
    
    # Add new entry only if it doesn't exist
    files_index[recipient].append({
        "transfer_id": transfer_id,
        "filename": filename,
        "path": path,
        "size": size,
        "from": from_name,
        "timestamp": time.time()
    })

def handle_file_post(msg: Message, from_name: str):
    """
    Handles incoming file POST messages.
    msg.data semantics:
      - str  : start-of-transfer (filename)
      - bytes: file data chunk
      - None : end-of-transfer marker
    msg.to_names: recipients tuple
    """
    global active_transfers

    # determine intended recipients
    if not msg.to_names:
        recipients = [n for n in clients.keys() if n != from_name]
    else:
        recipients = [n for n in msg.to_names if n in clients]

    # --- CASE 1: start-of-transfer (filename string) ---
    if isinstance(msg.data, str):
        filename = os.path.basename(msg.data)
        transfer_id = f"{from_name}_{filename}_{int(time.time() * 1000)}"

        handles = {}
        for r in recipients:
            rdir = os.path.join(DATA_DIR, r)
            os.makedirs(rdir, exist_ok=True)
            safe_name = safe_filename(rdir, filename)
            path = os.path.join(rdir, safe_name)
            try:
                fobj = open(path, "wb")
            except Exception as e:
                print(f"[ERROR] Could not open {path} for writing: {e}")
                continue
            handles[r] = {"fileobj": fobj, "path": path, "filename": safe_name}

        # register this active transfer
        active_transfers[(from_name, filename, transfer_id)] = handles
        return

    # --- CASE 2: safety guard: ignore stray chunks if no transfer started yet ---
    if not active_transfers:
        return

    # --- locate active transfer for this sender ---
    matched_keys = [k for k in active_transfers.keys() if k[0] == from_name]
    if not matched_keys:
        return

    matched_keys.sort(key=lambda k: k[2], reverse=True)  # pick newest
    transfer_key = matched_keys[0]
    handles = active_transfers.get(transfer_key)

    # --- CASE 3: end-of-transfer marker ---
    if msg.data is None:
        for r, info in list(handles.items()):
            try:
                fobj = info["fileobj"]
                path = info["path"]
                fobj.close()

                if not valid_file(path):
                    if os.path.exists(path):
                        os.remove(path)
                    continue

                size = os.path.getsize(path)
                # Add the completed file to the index
                add_file_index(r, info["filename"], path, size, from_name, transfer_key[2])

            except Exception as e:
                print(f"[ERROR] Closing file for {r}: {e}")

        active_transfers.pop(transfer_key, None)
        return

    # --- CASE 4: file data chunk (bytes) ---
    if isinstance(msg.data, (bytes, bytearray)):
        for r, info in handles.items():
            try:
                info["fileobj"].write(msg.data)
            except Exception as e:
                print(f"[ERROR] Writing chunk for {r}: {e}")
        return

    # --- fallback: unexpected type ---
    pass


def send_file_list_to(client_name: str):
    """
    Prepare a list of files available for client_name and send as FILE_LIST.
    The data payload will be a list of dicts: {transfer_id, filename, size, from, timestamp}
    """
    ensure_files_index_for(client_name)
    entries = files_index.get(client_name, [])
    
    # Filter out 0-byte files and files that don't exist
    valid_entries = []
    for e in entries:
        if e["size"] > 0 and valid_file(e["path"]):
            valid_entries.append(e)
    
    # Update the index to only contain valid entries
    files_index[client_name] = valid_entries
    
    # make a shallow copy with only necessary fields
    send_list = [
        {
            "transfer_id": e["transfer_id"],
            "filename": e["filename"],
            "size": e["size"],
            "from": e["from"],
            "timestamp": e.get("timestamp", 0)
        } for e in valid_entries
    ]
    # send from SERVER
    if client_name in clients:
        clients[client_name].send_msg(SERVER, FILE_LIST, FILE, send_list)

def handle_download_request(msg: Message, requester_name: str):
    """
    msg.data expected to be a dict: { "transfer_id": str }
    Server will stream file chunks for that transfer to the requester only.
    """
    if not isinstance(msg.data, dict) or "transfer_id" not in msg.data:
        clients[requester_name].send_msg(SERVER, POST, TEXT, "Invalid download request")
        return
    transfer_id = msg.data["transfer_id"]
    # Find the file entry for requester
    ensure_files_index_for(requester_name)
    entry = None
    for e in files_index.get(requester_name, []):
        if e["transfer_id"] == transfer_id:
            entry = e
            break
    if entry is None:
        clients[requester_name].send_msg(SERVER, POST, TEXT, "Requested file not found")
        return
    path = entry["path"]
    filename = entry["filename"]
    size = entry["size"]
    
    # Validate file exists and has content before streaming
    if not valid_file(path):
        clients[requester_name].send_msg(SERVER, POST, TEXT, "Requested file is empty or corrupted")
        return
        
    # send a FILE_CHUNK metadata start message with size & filename
    metadata = {"transfer_id": transfer_id, "filename": filename, "size": size, "from": entry.get("from", "")}
    clients[requester_name].send_msg(SERVER, FILE_CHUNK, FILE, metadata)
    
    # stream file in chunks
    try:
        with open(path, "rb") as f:
            bytes_sent = 0
            while True:
                chunk = f.read(SIZE)
                if not chunk:
                    break
                clients[requester_name].send_msg(SERVER, FILE_CHUNK, FILE, chunk)
                bytes_sent += len(chunk)
                # small sleep to avoid flooding
                time.sleep(0.001)
                
        # Verify we sent the expected amount of data
        if bytes_sent != size:
            clients[requester_name].send_msg(SERVER, POST, TEXT, f"File transfer incomplete: sent {bytes_sent}/{size} bytes")
            
    except Exception as e:
        print(f"[ERROR] Error while sending file {path} to {requester_name}: {e}")
        clients[requester_name].send_msg(SERVER, POST, TEXT, f"Error streaming file: {e}")
        return
    # send final None marker to indicate end
    clients[requester_name].send_msg(SERVER, FILE_CHUNK, FILE, None)

def disconnect_client(client: Client):
    global clients, current_presenter
    if current_presenter == client.name:
        current_presenter = None
        broadcast_msg(SERVER, STOP_SHARE, SCREEN)
    client.media_addrs.update({VIDEO: None, AUDIO: None})
    client.connected = False
    broadcast_msg(client.name, RM)
    try:
        client.main_conn.disconnect()
    except Exception:
        pass
    try:
        clients.pop(client.name)
    except KeyError:
        pass

def handle_main_conn(name: str):
    global current_presenter
    client: Client = clients[name]
    conn = client.main_conn
    # Send list of existing clients to the new one
    for client_name in clients:
        if client_name == name:
            continue
        client.send_msg(client_name, ADD)
    broadcast_msg(name, ADD)

    while client.connected:
        msg_bytes = conn.recv_bytes()
        if not msg_bytes:
            break
        try:
            msg = pickle.loads(msg_bytes)
        except (pickle.UnpicklingError, pickle.PickleError, EOFError, ValueError) as e:
            print(f"[{name}] [ERROR] Pickle error: {e}")
            continue



        if msg.request == DISCONNECT:
            break

        # SCREEN sharing logic unchanged
        elif msg.request == START_SHARE:
            if current_presenter is None:
                current_presenter = name
                # send explicit start confirmation to the requester
                clients[name].send_msg(SERVER, START_SHARE, SCREEN, data=name)
                # broadcast to the rest that someone started sharing
                broadcast_msg(SERVER, START_SHARE, SCREEN, data=name)
            else:
                # send rejection to requester only
                clients[name].send_msg(SERVER, POST, TEXT, "Screen sharing already active by another user")

        elif msg.request == STOP_SHARE:
            if current_presenter == name:
                current_presenter = None
                broadcast_msg(SERVER, STOP_SHARE, SCREEN)
            else:
                clients[name].send_msg(SERVER, POST, TEXT, "You are not the current presenter")

        # FILE transfer posted by a client (server stores it)
        elif msg.request == POST and msg.data_type == FILE:
            try:
                handle_file_post(msg, name)
            except Exception as e:
                print(f"[ERROR] handle_file_post: {e}")
                traceback.print_exc()

        # Client requests list of files available for them
        elif msg.request == GET_FILES:
            # msg.from_name is the requester
            try:
                send_file_list_to(name)
            except Exception as e:
                print(f"[ERROR] send_file_list_to: {e}")

        # Client requests server to stream a particular file to them
        elif msg.request == DOWNLOAD_FILE and msg.data_type == FILE:
            try:
                handle_download_request(msg, name)
            except Exception as e:
                print(f"[ERROR] handle_download_request: {e}")

        else:
            # default behavior: forward as multicast (text, video, audio, etc.)
            multicast_msg(name, msg.request, msg.to_names, msg.data_type, msg.data)

    disconnect_client(client)

def main_server():
    main_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    main_socket.bind((IP, MAIN_PORT))
    main_socket.listen()
    print(f"[LISTENING] Main Server is listening on {IP}:{MAIN_PORT}")

    video_server_thread = threading.Thread(target=media_server, args=(VIDEO, VIDEO_PORT))
    video_server_thread.start()

    audio_server_thread = threading.Thread(target=media_server, args=(AUDIO, AUDIO_PORT))
    audio_server_thread.start()

    while True:
        conn, addr = main_socket.accept()
        name = conn.recv_bytes().decode()
        if name in clients:
            conn.send_bytes("Username already taken".encode())
            continue
        conn.send_bytes(OK.encode())
        clients[name] = Client(name, conn, True)
        main_conn_thread = threading.Thread(target=handle_main_conn, args=(name,))
        main_conn_thread.start()

if __name__ == "__main__":
    try:
        # Clean up any leftover 0-byte files and duplicates from previous runs
        cleanup_empty_files()
        cleanup_duplicate_files()
        main_server()
    except KeyboardInterrupt:
        for client in list(clients.values()):
            disconnect_client(client)
    except Exception as e:
        print(f"[ERROR] {e}")
        print(traceback.format_exc())
    finally:
        os._exit(0)

