#!/usr/bin/env python3
"""HTTP reverse proxy: receives from phtunnel (HTTP mode), forwards to Vite"""
import socket
import threading
import sys

HOST = "0.0.0.0"
PORT = 10444
VITE_HOST = "127.0.0.1"
VITE_PORT = 5173

def handle_request(client_sock, addr):
    print(f"[proxy] conn from {addr}")
    vite_sock = None
    try:
        # Read all available data from client (the full HTTP request)
        data = b""
        while True:
            chunk = client_sock.recv(8192)
            if not chunk:
                break
            data += chunk
            # If we've received headers and possibly body, stop when we have enough
            if b"\r\n\r\n" in data:
                # Check if we have all the data we need
                header_end = data.index(b"\r\n\r\n") + 4
                headers = data[:header_end].decode('ascii', errors='replace')
                # Check Content-Length
                for line in headers.split('\r\n'):
                    if line.lower().startswith('content-length:'):
                        cl = int(line.split(':')[1].strip())
                        body_start = header_end
                        body_received = len(data) - header_end
                        if body_received >= cl:
                            print(f"[proxy] got full request {len(data)}b (body={cl})")
                            data = data[:header_end + cl]  # trim to actual content
                            break
                else:
                    # No Content-Length, or body complete
                    print(f"[proxy] got request {len(data)}b")
                break
            if len(data) > 1024 * 1024:  # 1MB limit
                print(f"[proxy] request too large {len(data)}b")
                break

        if not data:
            print(f"[proxy] empty request, closing")
            client_sock.close()
            return

        # Connect to Vite
        try:
            vite_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            vite_sock.settimeout(15)
            vite_sock.connect((VITE_HOST, VITE_PORT))
            print(f"[proxy] connected to Vite")
        except Exception as e:
            print(f"[proxy] Vite connect error: {e}")
            client_sock.close()
            return

        # Forward request
        sent = vite_sock.sendall(data)
        print(f"[proxy] forwarded {len(data)}b to Vite")

        # Read response from Vite and send back to client
        while True:
            response = vite_sock.recv(32768)
            if not response:
                break
            client_sock.sendall(response)
            print(f"[proxy] sent {len(response)}b back to client")

        print(f"[proxy] done")

    except Exception as e:
        print(f"[proxy] error: {e}")
    finally:
        try:
            client_sock.close()
        except Exception:
            pass
        try:
            if vite_sock:
                vite_sock.close()
        except Exception:
            pass

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(50)
    print(f"[proxy] HTTP proxy {HOST}:{PORT} -> {VITE_HOST}:{VITE_PORT}", flush=True)
    while True:
        try:
            client, addr = server.accept()
            t = threading.Thread(target=handle_request, args=(client, addr), daemon=True)
            t.start()
        except KeyboardInterrupt:
            print("\n[proxy] bye")
            break
        except Exception as e:
            print(f"[proxy] accept error: {e}")

if __name__ == "__main__":
    main()
