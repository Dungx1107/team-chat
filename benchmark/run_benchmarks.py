import subprocess
import json
import os
import shutil
from pathlib import Path

JMETER_BIN = "/home/dungx/Applications/apache-jmeter-5.6.3/bin/jmeter"
BASE_DIR = Path(__file__).resolve().parent / "experiments" / "01_redis_pubsub" / "00_baseline"
JMX_FILE = BASE_DIR / "baseline_test.jmx"
FINAL_SUMMARY_FILE = BASE_DIR / "summary_results.json"

# Đã thêm mốc 1000 và 2000 users
USER_STEPS = [50, 100, 200, 500, 1000, 2000]


def run_benchmarks():
    all_results = []

    for u in USER_STEPS:
        print(f"\n================ ĐANG ĐO TẢI MỐC: {u} USERS ================")

        temp_jtl = BASE_DIR / f"temp_{u}u.jtl"
        temp_html_dir = BASE_DIR / f"temp_html_{u}u"

        if temp_jtl.exists(): os.remove(temp_jtl)
        if temp_html_dir.exists(): shutil.rmtree(temp_html_dir)

        # Ramp-up bằng 1/2 số user (Vd: 100 users -> rampup 50s; 200 users -> rampup 100s)
        ramp_up = max(10, u // 2)

        cmd = [
            JMETER_BIN, "-n",
            "-t", str(JMX_FILE),
            "-Jthreads", str(u),
            "-Jduration=60",
            f"-Jrampup={ramp_up}",
            "-l", str(temp_jtl),
            "-e", "-o", str(temp_html_dir)
        ]

        subprocess.run(cmd, check=True)

        stat_file = temp_html_dir / "content" / "js" / "statistics.json"
        if stat_file.exists():
            with open(stat_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            api_stats = data.get("POST Send Message", {})

            result_entry = {
                "users": u,
                "samples": api_stats.get("sampleCount"),
                "error_pct": round(api_stats.get("errorPct", 0), 2),
                "throughput_req_sec": round(api_stats.get("throughput", 0), 2),
                "mean_res_time_ms": round(api_stats.get("meanResTime", 0), 2),
                "median_res_time_ms": round(api_stats.get("medianResTime", 0), 2),
                "p95_res_time_ms": round(api_stats.get("pct2ResTime", 0), 2),
                "p99_res_time_ms": round(api_stats.get("pct3ResTime", 0), 2)
            }
            all_results.append(result_entry)
            print(
                f"-> Mốc {u} Users xong! Throughput: {result_entry['throughput_req_sec']} req/s | Avg Latency: {result_entry['mean_res_time_ms']}ms")

        # Dọn dẹp folder và log tạm
        if temp_jtl.exists(): os.remove(temp_jtl)
        if temp_html_dir.exists(): shutil.rmtree(temp_html_dir)
        jmeter_log = Path("jmeter.log")
        if jmeter_log.exists(): os.remove(jmeter_log)

    with open(FINAL_SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n=== HOÀN THÀNH TẤT CẢ MỐC! Kết quả tổng hợp lưu tại: {FINAL_SUMMARY_FILE} ===")


if __name__ == "__main__":
    run_benchmarks()