"""Đo sức chịu của LiveKit SFU bằng bot nhẹ, server và bot ghim lõi CPU riêng.

Chạy trên Linux (Kaggle, Colab, VPS). Không cần Docker, backend hay DB: script tự tải
livekit-server và lk (LiveKit CLI), chạy server trên một nhóm lõi, chạy bot trên nhóm
lõi còn lại, đo từng mức tải rồi ghi kết quả.

    python sfu_load.py --scenario mixed   --steps "10 20 40 60 80"
    python sfu_load.py --scenario uniform --steps "2 4 8 16 24 32 48"   # k cuộc x 4 người
    python sfu_load.py --scenario large   --steps "16 32 50 100"        # 1 cuộc N người

Bot (`lk load-test`) gửi video đã mã hóa sẵn (có simulcast) và nhận mà không giải mã,
nên rẻ hơn trình duyệt thật hàng chục lần. Một cuộc gọi N người, c người bật camera,
a người bật micro được mô phỏng bằng: c bot phát video + a bot phát âm thanh + (N-1)
bot nhận. Số luồng SFU phải chuyển tiếp đúng bằng cuộc gọi thật: c(N-1) video và
a(N-1) âm thanh. Số kết nối nhiều hơn thật (c + a + N - 1 so với N), tức là hơi bi quan.
"""
import argparse
import json
import os
import platform
import random
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import psutil

LIVEKIT_VERSION = "1.13.11"   # cùng bản với docker-compose.yml
LK_VERSION = "2.20.1"
API_KEY = "benchkey"
API_SECRET = "bench-secret-bench-secret-bench-secret"
HTTP_PORT, METRICS_PORT = 7880, 6789
HERE = Path(__file__).resolve().parent
BIN = HERE / "bin"

# Mô hình tải "mixed": cỡ cuộc gọi nhóm của công ty ~2000 người (xem README)
SIZE_MIX = [((3, 4), 0.6), ((5, 8), 0.3), ((10, 16), 0.1)]


# ----------------------------------------------------------------- công cụ

def _download(url: str, name: str) -> Path:
    BIN.mkdir(exist_ok=True)
    target = BIN / name
    if target.exists():
        return target
    arch = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
    url = url.format(arch=arch)
    print(f"-> tải {url}")
    archive = BIN / "tmp.tar.gz"
    urllib.request.urlretrieve(url, archive)
    with tarfile.open(archive) as tar:
        member = next(m for m in tar.getmembers() if Path(m.name).name == name)
        member.name = name
        tar.extract(member, BIN, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    archive.unlink()
    target.chmod(0o755)
    return target


def tools():
    server = shutil.which("livekit-server") or _download(
        f"https://github.com/livekit/livekit/releases/download/v{LIVEKIT_VERSION}/"
        f"livekit_{LIVEKIT_VERSION}_linux_{{arch}}.tar.gz", "livekit-server")
    lk = shutil.which("lk") or _download(
        f"https://github.com/livekit/livekit-cli/releases/download/v{LK_VERSION}/"
        f"lk_{LK_VERSION}_linux_{{arch}}.tar.gz", "lk")
    return str(server), str(lk)


def pinned(cmd, cpus):
    return (["taskset", "-c", cpus] + cmd) if cpus else cmd


def cpu_list(spec: str):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


# ----------------------------------------------------------------- mô hình tải

def build_calls(scenario: str, step: int, args, rng: random.Random):
    """Trả về list cuộc gọi (N, video_pubs, audio_pubs)."""
    if scenario == "uniform":
        return [(args.size, args.size, args.size)] * step
    if scenario == "large":
        return [(step, args.large_cameras, args.large_cameras)]
    calls = []
    for _ in range(step):
        r, acc = rng.random(), 0.0
        for (lo, hi), p in SIZE_MIX:
            acc += p
            if r <= acc:
                break
        n = rng.randint(lo, hi)
        c = max(1, round(n * args.camera_ratio))
        a = max(1, round(n * args.mic_ratio))
        calls.append((n, c, a))
    return calls


def layout_for(n: int) -> str:
    return "3x3" if n <= 9 else "4x4" if n <= 16 else "5x5"


# ----------------------------------------------------------------- số đo server

def scrape():
    """Đọc bộ đếm Prometheus của LiveKit -> dict tổng theo tên + nhãn chọn lọc."""
    try:
        body = urllib.request.urlopen(f"http://127.0.0.1:{METRICS_PORT}/metrics", timeout=5).read().decode()
    except Exception:
        return {}
    out = {}
    for line in body.splitlines():
        if not line.startswith("livekit_"):
            continue
        m = re.match(r'(\w+)(\{[^}]*\})?\s+(\S+)', line)
        if not m:
            continue
        name, labels, value = m.group(1), m.group(2) or "", float(m.group(3))
        direction = re.search(r'[{,]direction="(\w+)"', labels)
        kind = re.search(r'[{,]type="(\w+)"', labels)
        key = name + (":" + direction.group(1) if direction else "") + (":" + kind.group(1) if kind else "")
        out[key] = out.get(key, 0.0) + value
    return out


def delta(a, b, key):
    return b.get(key, 0.0) - a.get(key, 0.0)


def avg_hist(a, b, base):
    count = delta(a, b, base + "_count")
    return delta(a, b, base + "_sum") / count if count else None


class Sampler(threading.Thread):
    """Lấy CPU/RAM của server, của bot và từng lõi mỗi 2 giây."""

    def __init__(self, server_pid, bot_pids, server_cpus, bot_cpus):
        super().__init__(daemon=True)
        self.server = psutil.Process(server_pid)
        self.bots = [psutil.Process(p) for p in bot_pids if psutil.pid_exists(p)]
        self.server_cpus, self.bot_cpus = server_cpus, bot_cpus
        self.rows, self.stop_flag = [], threading.Event()

    def _cpu(self, procs):
        total = 0.0
        for p in procs:
            try:
                total += p.cpu_percent(None)
            except psutil.Error:
                pass
        return total

    def run(self):
        self._cpu([self.server] + self.bots)
        psutil.cpu_percent(percpu=True)
        while not self.stop_flag.wait(2):
            per_core = psutil.cpu_percent(percpu=True)
            try:
                rss = self.server.memory_info().rss
            except psutil.Error:
                rss = 0
            self.rows.append(dict(
                t=time.time(),
                server_cpu=self._cpu([self.server]) / 100,      # số lõi đang dùng
                bots_cpu=self._cpu(self.bots) / 100,
                server_rss_mb=rss / 2**20,
                server_cores_util=sum(per_core[i] for i in self.server_cpus) / len(self.server_cpus),
                bot_cores_util=sum(per_core[i] for i in self.bot_cpus) / len(self.bot_cpus),
            ))

    def summary(self):
        if not self.rows:
            return {}
        keys = [k for k in self.rows[0] if k != "t"]
        avg = {k: sum(r[k] for r in self.rows) / len(self.rows) for k in keys}
        peak = {k + "_max": max(r[k] for r in self.rows) for k in keys}
        return {**{k: round(v, 3) for k, v in avg.items()}, **{k: round(v, 3) for k, v in peak.items()}}


# ----------------------------------------------------------------- kết quả bot

TOTAL_RE = re.compile(r"│\s*Total\s*│\s*(\d+)/(\d+)\s*│\s*([\d.]+)\s*(kbps|mbps|bps)[^│]*│\s*(\d+)\s*\(([\d.]+)%\)\s*│\s*(\d+)")


def parse_lk(text: str):
    m = TOTAL_RE.search(text)
    if not m:
        return None
    got, exp, rate, unit, lost, loss_pct, errors = m.groups()
    kbps = float(rate) * {"bps": 0.001, "kbps": 1, "mbps": 1000}[unit]
    return dict(tracks=int(got), expected=int(exp), kbps=kbps, lost=int(lost),
                loss_pct=float(loss_pct), errors=int(errors))


class Bot:
    def __init__(self, cmd, cpus):
        self.proc = subprocess.Popen(pinned(cmd, cpus), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace")
        self.buf, self.connected_at = [], None
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            self.buf.append(line)
            if self.connected_at is None and "Finished connecting" in line:
                self.connected_at = time.time()

    @property
    def text(self):
        return "".join(self.buf)


# ----------------------------------------------------------------- một mức tải

def start_server(server_bin, cpus, workdir: Path):
    cfg = workdir / "livekit.yaml"
    cfg.write_text(
        f"port: {HTTP_PORT}\n"
        "bind_addresses: [127.0.0.1]\n"
        "rtc: {tcp_port: 7881, udp_port: 7882, use_external_ip: false}\n"
        f"keys: {{{API_KEY}: {API_SECRET}}}\n"
        "room: {auto_create: true}\n"
        f"prometheus_port: {METRICS_PORT}\n"
        "logging: {level: warn}\n")
    log = open(workdir / "livekit.log", "a")
    proc = subprocess.Popen(pinned([server_bin, "--config", str(cfg), "--node-ip", "127.0.0.1"], cpus),
                            stdout=log, stderr=subprocess.STDOUT)
    for _ in range(50):
        if scrape():
            return proc
        time.sleep(0.2)
    raise SystemExit("livekit-server không lên, xem livekit.log")


def stop(proc):
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def run_step(step, calls, args, server_bin, lk_bin, workdir):
    server = start_server(server_bin, args.server_cpus, workdir)
    stagger = args.stagger
    duration = args.seconds + len(calls) * stagger + 60
    bots = []
    t0 = time.time()
    for i, (n, c, a) in enumerate(calls):
        cmd = [lk_bin, "load-test", "--url", f"http://127.0.0.1:{HTTP_PORT}",
               "--api-key", API_KEY, "--api-secret", API_SECRET,
               "--room", f"bench-{step}-{i}", "--identity-prefix", f"s{step}c{i}",
               "--video-publishers", str(c), "--audio-publishers", str(a), "--subscribers", str(n - 1),
               "--video-resolution", args.resolution, "--layout", layout_for(n),
               "--num-per-second", "5", "--duration", f"{duration}s"]
        bots.append(Bot(cmd, args.bot_cpus))
        time.sleep(stagger)

    # Chờ mọi cuộc gọi kết nối xong rồi mới bắt đầu cửa sổ đo
    deadline = time.time() + 120 + len(calls) * stagger
    while time.time() < deadline and any(b.connected_at is None and b.proc.poll() is None for b in bots):
        time.sleep(1)
    connected = sum(b.connected_at is not None for b in bots)
    connect_s = max((b.connected_at for b in bots if b.connected_at), default=time.time()) - t0
    time.sleep(5)

    sampler = Sampler(server.pid, [b.proc.pid for b in bots],
                      cpu_list(args.server_cpus), cpu_list(args.bot_cpus))
    before = scrape()
    sampler.start()
    time.sleep(args.seconds)
    sampler.stop_flag.set()
    sampler.join()
    after = scrape()

    for b in bots:
        try:
            b.proc.wait(timeout=duration + 60)
        except subprocess.TimeoutExpired:
            b.proc.kill()
    time.sleep(0.5)
    stop(server)

    parsed = [parse_lk(b.text) for b in bots]
    ok = [p for p in parsed if p]
    (workdir / f"step_{step}_bots.log").write_text(
        "\n\n".join(f"### call {i} {calls[i]}\n{b.text}" for i, b in enumerate(bots)), encoding="utf-8")

    secs = args.seconds
    video_fwd = sum(c * (n - 1) for n, c, a in calls)
    audio_fwd = sum(a * (n - 1) for n, c, a in calls)
    tracks = sum(p["tracks"] for p in ok)
    expected = sum((n - 1) * (c + a) for n, c, a in calls)
    res = dict(
        step=step, calls=len(calls), participants=sum(n for n, _, _ in calls),
        cameras=sum(c for _, c, _ in calls), mics=sum(a for _, _, a in calls),
        video_streams_forwarded=video_fwd, audio_streams_forwarded=audio_fwd,
        calls_connected=connected, connect_seconds=round(connect_s, 1),
        bots_reporting=len(ok), tracks_received=tracks, tracks_expected=expected,
        tracks_ratio=round(tracks / expected, 4) if expected else None,
        bot_errors=sum(p["errors"] for p in ok),
        subscriber_kbps_avg=round(sum(p["kbps"] for p in ok) / max(1, sum(n - 1 for n, _, _ in calls)), 1),
        server_in_mbps=round(delta(before, after, "livekit_packet_bytes:incoming") * 8 / secs / 1e6, 2),
        server_out_mbps=round(delta(before, after, "livekit_packet_bytes:outgoing") * 8 / secs / 1e6, 2),
        loss_out_video_pct=avg_hist(before, after, "livekit_packet_loss_percent:outgoing:VIDEO"),
        loss_out_audio_pct=avg_hist(before, after, "livekit_packet_loss_percent:outgoing:AUDIO"),
        jitter_out_video_ms=(avg_hist(before, after, "livekit_jitter_us:outgoing:VIDEO") or 0) / 1000,
        join_latency_ms=avg_hist({}, after, "livekit_session_join_latency_ms"),
        **sampler.summary(),
    )
    # Mất gói phía bot nhận: trung bình có trọng số theo số bot nhận
    weights = [(p["loss_pct"], n - 1) for p, (n, _, _) in zip(parsed, calls) if p]
    res = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res.items()}
    res["subscriber_loss_pct"] = round(sum(l * w for l, w in weights) / max(1, sum(w for _, w in weights)), 3)
    return res, sampler.rows


def verdict(r, args):
    reasons = []
    if r["bot_cores_util"] > 85:
        reasons.append("MÁY TẠO TẢI QUÁ TẢI (kết quả không dùng được)")
    if r["calls_connected"] < r["calls"]:
        reasons.append(f"chỉ {r['calls_connected']}/{r['calls']} cuộc kết nối")
    if r["tracks_ratio"] is not None and r["tracks_ratio"] < 0.99:
        reasons.append(f"nhận {r['tracks_ratio']:.1%} luồng")
    if r["subscriber_loss_pct"] > 2:
        reasons.append(f"mất gói {r['subscriber_loss_pct']}%")
    if r["server_cores_util"] > 80:
        reasons.append(f"CPU server {r['server_cores_util']:.0f}%")
    return reasons


def main():
    sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", choices=["mixed", "uniform", "large"], default="mixed")
    ap.add_argument("--steps", default=None, help="mixed/uniform: số cuộc gọi; large: số người")
    ap.add_argument("--seconds", type=int, default=180, help="độ dài cửa sổ đo mỗi mức")
    ap.add_argument("--stagger", type=float, default=0.5, help="giãn cách khởi động mỗi cuộc gọi (giây)")
    ap.add_argument("--resolution", default="medium", choices=["low", "medium", "high"])
    ap.add_argument("--size", type=int, default=4, help="uniform: số người mỗi cuộc")
    ap.add_argument("--camera-ratio", type=float, default=0.6)
    ap.add_argument("--mic-ratio", type=float, default=1.0)
    ap.add_argument("--large-cameras", type=int, default=4)
    ap.add_argument("--server-cpus", default=None, help='vd "0,1" (mặc định: nửa đầu số lõi)')
    ap.add_argument("--bot-cpus", default=None, help='vd "2,3" (mặc định: nửa sau)')
    ap.add_argument("--keep-going", action="store_true", help="đo tiếp cả khi mức trước đã hỏng")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    n = psutil.cpu_count()
    half = max(1, n // 2)
    args.server_cpus = args.server_cpus or (f"0-{half - 1}" if half > 1 else "0")
    args.bot_cpus = args.bot_cpus or (f"{half}-{n - 1}" if n - 1 > half else str(min(half, n - 1)))
    default_steps = {"mixed": "10 20 40 60 80", "uniform": "2 4 8 16 24 32 48", "large": "16 32 50 100"}
    steps = [int(s) for s in (args.steps or default_steps[args.scenario]).split()]

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    name = f"{args.scenario}_{stamp}"
    out = Path(args.out) if args.out else HERE / "results" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    workdir = out.parent / f"{out.stem}_logs"
    workdir.mkdir(exist_ok=True)

    server_bin, lk_bin = tools()
    machine = dict(cpus=n, cpu_model=platform.processor() or platform.machine(),
                   ram_gb=round(psutil.virtual_memory().total / 2**30, 1), host=platform.node()[:20],
                   server_cpus=args.server_cpus, bot_cpus=args.bot_cpus)
    print(f"-> máy: {machine}")
    report = dict(scenario=args.scenario, started=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  machine=machine, args={k: v for k, v in vars(args).items()},
                  livekit=LIVEKIT_VERSION, lk=LK_VERSION, steps=[])
    rng = random.Random(42)
    timeline = []
    for step in steps:
        calls = build_calls(args.scenario, step, args, rng)
        print(f"\n===== mức {step}: {len(calls)} cuộc, {sum(c[0] for c in calls)} người "
              f"({datetime.now():%H:%M:%S}) =====")
        res, rows = run_step(step, calls, args, server_bin, lk_bin, workdir)
        res["fail_reasons"] = verdict(res, args)
        res["call_sizes"] = calls
        report["steps"].append(res)
        timeline += [dict(step=step, **r) for r in rows]
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"   luồng nhận {res['tracks_received']}/{res['tracks_expected']}, mất gói {res['subscriber_loss_pct']}%, "
              f"server {res['server_cpu']:.2f} lõi ({res['server_cores_util']:.0f}% nhóm lõi), "
              f"ra {res['server_out_mbps']} Mbps, bot {res['bot_cores_util']:.0f}% nhóm lõi")
        if res["fail_reasons"]:
            print("   KHÔNG ĐẠT: " + "; ".join(res["fail_reasons"]))
            if not args.keep_going:
                break
    (out.parent / f"{out.stem}_timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
    print(f"\n=== XONG -> {out} ===")
    os.system(f'{sys.executable} "{HERE / "summarize.py"}" "{out}"')


if __name__ == "__main__":
    main()
