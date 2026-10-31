import argparse
import socket
import sys

from util import PacketHeader, compute_checksum

T_START, T_END, T_DATA, T_ACK = 0, 1, 2, 3
HDR = 16


def encode(kind, seq, body=b""):
    hdr = PacketHeader(type=kind, seq_num=seq, length=len(body))
    hdr.checksum = compute_checksum(hdr / body)
    return bytes(hdr / body)


def decode(raw):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("receiver_ip")
    ap.add_argument("receiver_port", type=int)
    ap.add_argument("window_size", type=int)
    a = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((a.receiver_ip, a.receiver_port))
    out = sys.stdout.buffer

    connected = False
    want = 1            # seq ke tiep can nhan theo thu tu
    pending = {}        # goi den som (out-of-order)

    while True:
        raw, src = sock.recvfrom(2048)
        msg = decode(raw)
        if msg is None:                 # hong -> bo, khong ack
            continue
        kind, seq, body = msg

        if kind == T_START:
            if connected:               # dang giua ket noi -> bo qua
                continue
            connected, want = True, 1
            pending.clear()
            sock.sendto(encode(T_ACK, 1), src)
        elif not connected:
            continue
        elif kind == T_DATA:
            if seq >= want + a.window_size:     # ngoai cua so
                continue
            if seq >= want:
                pending.setdefault(seq, body)
                while want in pending:
                    out.write(pending.pop(want))
                    want += 1
            sock.sendto(encode(T_ACK, seq), src)    # ack rieng tung goi
        elif kind == T_END:
            sock.sendto(encode(T_ACK, seq), src)
            break

    out.flush()


if __name__ == "__main__":
    main()