"""Turn raw PCM pipes (librespot, AirPlay) into a continuous MP3 HTTP stream.

Silence is inserted whenever nothing is playing so that connected speakers
never see the stream drop. When several sources play at once, the first
one given on the command line wins.
"""

import argparse
import os
import queue
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RATE = 44100
FRAME = 4  # s16le stereo
BYTES_PER_SEC = RATE * FRAME
TICK = 0.02

clients = set()
clients_lock = threading.Lock()


def log(msg):
    print(f"[axis-spotify] {msg}", flush=True)


def feed_pcm(fifo_paths, ffmpeg_stdin):
    """Read PCM from the FIFOs at real-time pace, padding gaps with silence."""
    sources = [[os.open(path, os.O_RDONLY | os.O_NONBLOCK), b""] for path in fifo_paths]
    sent = 0
    start = time.monotonic()
    while True:
        target = int((time.monotonic() - start) * BYTES_PER_SEC) // FRAME * FRAME
        need = target - sent
        if need > 0:
            chunk = b""
            # Drain every source so no writer stalls, keep the first with audio
            for source in sources:
                fd, pending = source
                if len(pending) < need:
                    try:
                        pending += os.read(fd, need - len(pending))
                    except BlockingIOError:
                        pass
                take = min(len(pending), need) // FRAME * FRAME
                if take and not chunk:
                    chunk = pending[:take]
                source[1] = pending[take:]
            ffmpeg_stdin.write(chunk + b"\x00" * (need - len(chunk)))
            ffmpeg_stdin.flush()
            sent = target
        time.sleep(TICK)


def broadcast_mp3(ffmpeg_stdout):
    while True:
        data = ffmpeg_stdout.read1(4096)
        if not data:
            raise RuntimeError("ffmpeg stopped producing output")
        with clients_lock:
            for q in list(clients):
                try:
                    q.put_nowait(data)
                except queue.Full:
                    clients.discard(q)


class StreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("icy-name", "Spotify")
        self.end_headers()
        q = queue.Queue(maxsize=256)
        with clients_lock:
            clients.add(q)
        log(f"client connected: {self.client_address[0]} "
            f"{self.requestline!r} agent={self.headers.get('User-Agent')!r}")
        start = time.monotonic()
        sent = 0
        reason = "closed"
        try:
            while True:
                data = q.get(timeout=10)
                self.wfile.write(data)
                sent += len(data)
        except queue.Empty:
            reason = "no data for 10s (client too slow, dropped)"
        except OSError as err:
            reason = f"client closed connection ({err.__class__.__name__})"
        finally:
            with clients_lock:
                clients.discard(q)
            log(f"client disconnected: {self.client_address[0]} after "
                f"{time.monotonic() - start:.1f}s, {sent} bytes, {reason}")

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fifo", action="append", required=True)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--bitrate", type=int, default=192)
    args = parser.parse_args()

    ffmpeg = subprocess.Popen(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-f", "s16le", "-ar", str(RATE), "-ac", "2", "-i", "pipe:0",
            "-c:a", "libmp3lame", "-b:a", f"{args.bitrate}k",
            "-f", "mp3", "pipe:1",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    threading.Thread(target=feed_pcm, args=(args.fifo, ffmpeg.stdin), daemon=True).start()
    threading.Thread(target=broadcast_mp3, args=(ffmpeg.stdout,), daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", args.port), StreamHandler)
    server.daemon_threads = True
    log(f"streaming on port {args.port}")
    try:
        server.serve_forever()
    finally:
        ffmpeg.kill()


if __name__ == "__main__":
    main()
