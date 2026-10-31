import argparse
import select
import socket
import sys
import time

from util import PacketHeader, compute_checksum

T_START, T_END, T_DATA, T_ACK = 0, 1, 2, 3
HDR = 16
MAX_BODY = 1472 - HDR
RTO = 0.5


def encode(kind, seq, body=b""):
    hdr = PacketHeader(type=kind, seq_num=seq, length=len(body))
    hdr.checksum = compute_checksum(hdr / body)
    return bytes(hdr / body)


def decode(raw):
    """Tra ve (type, seq, body) hoac None neu goi hong."""
    if len(raw) < HDR:
        return None
    hdr = PacketHeader(raw[:HDR])
    body = raw[HDR:HDR + hdr.length]
    if len(body) != hdr.length:
        return None
    claimed = hdr.checksum
    hdr.checksum = 0
    if compute_checksum(hdr / body) != claimed:
        return None
    return hdr.type, hdr.seq_num, body


def wait_ack(sock, timeout):
    """Cho 1 goi ACK hop le trong toi da `timeout` giay, tra ve seq hoac None."""
    ready, _, _ = select.select([sock], [], [], max(timeout, 0))
    if not ready:
        return None
    msg = decode(sock.recvfrom(2048)[0])
    if msg and msg[0] == T_ACK:
        return msg[1]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("receiver_ip")
    ap.add_argument("receiver_port", type=int)
    ap.add_argument("window_size", type=int)
    a = ap.parse_args()

    payload = sys.stdin.buffer.read()
    pieces = [payload[i:i + MAX_BODY] for i in range(0, len(payload), MAX_BODY)]
    total = len(pieces)                       # DATA co seq 1..total
    frames = {i + 1: encode(T_DATA, i + 1, p) for i, p in enumerate(pieces)}
    end_seq = total + 1

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer = (a.receiver_ip, a.receiver_port)

    # ---- handshake: START -> ACK(1)
    while True:
        sock.sendto(encode(T_START, 0), peer)
        if wait_ack(sock, RTO) == 1:
            break

    # ---- Selective Repeat: chi gui lai goi chua duoc ack
    left, right = 1, 1
    got = set()                 # cac goi trong cua so da duoc ack rieng le
    t0 = time.time()
    while left <= total:
        while right <= total and right < left + a.window_size:
            sock.sendto(frames[right], peer)
            right += 1
        remain = RTO - (time.time() - t0)
        if remain <= 0:
            for s in range(left, right):
                if s not in got:
                    sock.sendto(frames[s], peer)
            t0 = time.time()
            continue
        ack = wait_ack(sock, remain)
        if ack is not None and left <= ack < right:
            got.add(ack)
            if ack == left:                      # cua so truot
                while left in got:
                    got.discard(left)
                    left += 1
                t0 = time.time()

    # ---- ket thuc: END, doi ACK(end_seq) hoac 500ms
    deadline = time.time() + RTO
    while time.time() < deadline:
        sock.sendto(encode(T_END, end_seq), peer)
        stop_at = min(time.time() + 0.1, deadline)
        done = False
        while time.time() < stop_at:
            if wait_ack(sock, stop_at - time.time()) == end_seq:
                done = True
                break
        if done:
            break


if __name__ == "__main__":
    main()