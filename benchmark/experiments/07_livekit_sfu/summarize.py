"""In bảng kết quả và mô hình tài nguyên từ file JSON của sfu_load.py.

    python summarize.py results/mixed_20261125_1500.json [results/khac.json ...]

Mô hình tài nguyên: khớp tuyến tính CPU server (số lõi) theo số luồng video được chuyển
tiếp, chỉ dùng các mức hợp lệ (máy tạo tải chưa quá tải). Từ đó suy ra cần bao nhiêu lõi
cho một mức tải, và một máy N lõi chịu được bao nhiêu luồng / cuộc gọi.
"""
import json
import sys


def fit(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if not sxx:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - sum((y - a - b * x) ** 2 for x, y in zip(xs, ys)) / ss_tot if ss_tot else 1.0
    return a, b, r2


def show(path):
    rep = json.load(open(path, encoding="utf-8"))
    m = rep["machine"]
    print(f"\n## {rep['scenario']} — {path}")
    print(f"Máy: {m['cpus']} lõi, {m['ram_gb']} GB; server lõi {m['server_cpus']}, bot lõi {m['bot_cpus']}; "
          f"LiveKit {rep['livekit']}; mỗi mức đo {rep['args']['seconds']} s, video {rep['args']['resolution']}\n")
    print("| Mức | Cuộc | Người | Luồng video chuyển tiếp | Luồng nhận / dự kiến | Mất gói | "
          "CPU server (lõi) | RAM server | Ra (Mbps) | CPU bot | Đạt |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for s in rep["steps"]:
        ok = "đạt" if not s["fail_reasons"] else "**không**: " + "; ".join(s["fail_reasons"])
        print(f"| {s['step']} | {s['calls']} | {s['participants']} | {s['video_streams_forwarded']} | "
              f"{s['tracks_received']}/{s['tracks_expected']} | {s['subscriber_loss_pct']}% | "
              f"{s['server_cpu']:.2f} (đỉnh {s['server_cpu_max']:.2f}) | {s['server_rss_mb']:.0f} MB | "
              f"{s['server_out_mbps']} | {s['bot_cores_util']:.0f}% | {ok} |")

    valid = [s for s in rep["steps"] if s["bot_cores_util"] <= 85 and s["calls_connected"] == s["calls"]]
    f = fit([s["video_streams_forwarded"] for s in valid], [s["server_cpu"] for s in valid])
    if not f:
        print("\n(chưa đủ mức hợp lệ để khớp mô hình tài nguyên)")
        return
    a, b, r2 = f
    last = valid[-1]
    print(f"\n**Mô hình tài nguyên** (khớp {len(valid)} mức hợp lệ, R² = {r2:.3f}):")
    print(f"- CPU server ≈ {a:.3f} + {b * 100:.3f} lõi cho mỗi 100 luồng video chuyển tiếp")
    print(f"- Băng thông ra ≈ {last['server_out_mbps'] / max(1, last['video_streams_forwarded']):.2f} Mbps "
          f"mỗi luồng video (kèm phần âm thanh tương ứng)")
    print(f"- RAM ≈ {last['server_rss_mb'] / max(1, last['participants']):.1f} MB mỗi người (ở mức {last['step']})")
    if b > 0:
        calls = last["calls"]
        per_call = last["video_streams_forwarded"] / max(1, calls)
        print("\nSuy ra (giữ CPU server ≤ 80%):\n")
        print("| Số lõi cho LiveKit | Luồng video tối đa | ≈ cuộc gọi (cỡ như mức cuối) |")
        print("|---|---|---|")
        for cores in (1, 2, 4, 8):
            streams = max(0.0, (0.8 * cores - a) / b)
            print(f"| {cores} | {streams:.0f} | {streams / per_call:.0f} |")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        show(p)
