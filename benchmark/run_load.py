"""Chạy một phép đo theo thang 50 -> 2000 người dùng đồng thời bằng Locust.

Cần: môi trường đo đang chạy và đã seed (xem README.md), `pip install locust`.

    python benchmark/run_load.py --scenario send --out benchmark/experiments/01_redis_pubsub/results/before.json
    python benchmark/run_load.py --scenario rooms --steps 50 100 --out kq.json

Kịch bản: rooms | history | send | upload (xem locustfile.py).

Mỗi mức u người dùng:
  - dùng u user đầu của tokens.csv = u/50 nhóm đầu
  - lên đủ u người trong RAMP_UP giây, chạy tổng SKIP_SECONDS + HOLD_SECONDS giây
  - số liệu CHỈ tính HOLD_SECONDS cuối, bỏ SKIP_SECONDS đầu lúc server còn khởi động
  - nghỉ REST_SECONDS cho server hết việc tồn đọng rồi sang mức sau
  - lỗi quá STOP_ERROR_PCT thì dừng: các mức cao hơn chắc chắn cũng lỗi
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCUSTFILE = HERE / "locustfile.py"
TOKENS_FILE = HERE / "shared" / "data" / "tokens.csv"
SEED_INFO = HERE / "shared" / "data" / "seed_info.json"

HOST = os.getenv("BENCH_HOST", "http://localhost:8001")
DEFAULT_STEPS = [50, 100, 200, 500, 1000, 2000]

# Không để tăng tải 0 s: 2000 kết nối mở trong cùng một tích tắc gây lỗi do chính cách test
RAMP_UP = float(os.getenv("BENCH_RAMP_UP", "5"))
SKIP_SECONDS = int(os.getenv("BENCH_SKIP_SECONDS", "10"))
HOLD_SECONDS = int(os.getenv("BENCH_HOLD_SECONDS", "60"))
REST_SECONDS = int(os.getenv("BENCH_REST_SECONDS", "15"))
THINK_S = os.getenv("BENCH_THINK_S", "1")
STOP_ERROR_PCT = float(os.getenv("BENCH_STOP_ERROR_PCT", "50"))


def _percentile(sorted_values, pct):
    if not sorted_values:
        return 0
    k = max(0, min(len(sorted_values) - 1, round(pct / 100 * len(sorted_values)) - 1))
    return sorted_values[k]


def summarize(samples: list, users: int) -> dict:
    if not samples:
        # Request chưa xong khi hết giờ không được Locust ghi lại: server nghẽn tới mức
        # không trả lời kịp request nào trong thời gian đo
        return {"users": users, "samples": 0, "error_pct": 100.0,
                "errors": {"Không request nào hoàn thành trong thời gian đo (server nghẽn)": 1}}
    times = sorted(s[1] for s in samples)
    failures = [s for s in samples if not s[2]]
    errors = {}
    for s in failures:
        errors[s[3]] = errors.get(s[3], 0) + 1
    window = max(1e-3, max(s[0] + s[1] / 1000 for s in samples) - min(s[0] for s in samples))
    return {
        "users": users,
        "samples": len(samples),
        "error_pct": round(100 * len(failures) / len(samples), 2),
        "throughput_req_sec": round(len(samples) / window, 2),
        "mean_res_time_ms": round(sum(times) / len(times), 2),
        "median_res_time_ms": round(_percentile(times, 50), 2),
        "p95_res_time_ms": round(_percentile(times, 95), 2),
        "p99_res_time_ms": round(_percentile(times, 99), 2),
        "max_res_time_ms": round(times[-1], 2),
        "errors": dict(sorted(errors.items(), key=lambda kv: -kv[1])[:5]),
    }


def run_level(scenario: str, users: int, workers: int) -> dict:
    samples_dir = tempfile.mkdtemp(prefix="bench_")
    base_env = {
        **os.environ,
        "BENCH_SCENARIO": scenario,
        "BENCH_TOKENS": str(TOKENS_FILE),
        "BENCH_THINK_S": THINK_S,
        "BENCH_SKIP_SECONDS": str(SKIP_SECONDS),
        "BENCH_SAMPLES_DIR": samples_dir,
        "BENCH_WORKER_COUNT": str(workers),
        "PYTHONIOENCODING": "utf-8",
    }
    common = [sys.executable, "-m", "locust", "-f", str(LOCUSTFILE), "--host", HOST,
              "--headless", "--only-summary", "--loglevel", "WARNING"]
    load = ["-u", str(users), "-r", str(max(1.0, users / RAMP_UP)), "-t", f"{SKIP_SECONDS + HOLD_SECONDS}s"]

    if workers == 1:
        subprocess.run(common + load, env={**base_env, "BENCH_WORKER_INDEX": "0"})
    else:
        # Windows không có --processes của Locust: tự dựng 1 master + n worker
        master = subprocess.Popen(common + load + ["--master", "--expect-workers", str(workers)],
                                  env={**base_env, "BENCH_WORKER_INDEX": "-1"})
        procs = [
            subprocess.Popen(common + ["--worker"], env={**base_env, "BENCH_WORKER_INDEX": str(i)},
                             stdout=subprocess.DEVNULL)
            for i in range(workers)
        ]
        master.wait()
        for p in procs:
            p.wait(timeout=60)

    samples = []
    for f in Path(samples_dir).glob("samples_*.json"):
        samples += json.loads(f.read_text(encoding="utf-8"))
    shutil.rmtree(samples_dir, ignore_errors=True)
    return summarize(samples, users)


def main():
    # Console Windows mặc định cp1252, in tiếng Việt sẽ lỗi
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Đo tải theo thang người dùng đồng thời")
    parser.add_argument("--scenario", required=True, choices=["rooms", "history", "send", "upload"])
    parser.add_argument("--out", required=True, type=Path, help="tệp JSON kết quả")
    parser.add_argument("--steps", type=int, nargs="+", default=DEFAULT_STEPS)
    parser.add_argument("--workers", type=int, default=int(os.getenv("BENCH_LOCUST_WORKERS", "4")),
                        help="số tiến trình Locust; 2000 người cần nhiều hơn 1 nhân CPU")
    parser.add_argument("--note", default="", help="ghi chú: commit, số worker backend, ...")
    args = parser.parse_args()

    if not TOKENS_FILE.exists():
        sys.exit("Chưa có shared/data/tokens.csv -- chạy seed_data.py trước (xem README.md)")

    results = []
    for i, u in enumerate(args.steps):
        if i:
            time.sleep(REST_SECONDS)
        print(f"\n===== {args.scenario.upper()}: {u} người dùng =====", flush=True)
        r = run_level(args.scenario, u, args.workers)
        results.append(r)
        if r["samples"]:
            print(f"-> {r['throughput_req_sec']} req/s | trung bình {r['mean_res_time_ms']} ms | "
                  f"p95 {r['p95_res_time_ms']} ms | lỗi {r['error_pct']}%", flush=True)
        for err, count in r.get("errors", {}).items():
            print(f"   lỗi x{count}: {err}", flush=True)
        if r["error_pct"] > STOP_ERROR_PCT:
            print(f"-> Lỗi vượt {STOP_ERROR_PCT}%, dừng ở mức {u} người dùng")
            break

    report = {
        "scenario": args.scenario,
        "note": args.note,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "settings": {"host": HOST, "ramp_up_s": RAMP_UP, "skip_s": SKIP_SECONDS, "hold_s": HOLD_SECONDS,
                     "rest_s": REST_SECONDS, "think_s": float(THINK_S), "locust_workers": args.workers},
        "seed": json.loads(SEED_INFO.read_text(encoding="utf-8")) if SEED_INFO.exists() else None,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n=== XONG! Kết quả: {args.out} ===")


if __name__ == "__main__":
    main()
