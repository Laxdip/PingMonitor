#!/usr/bin/env python3
"""
================================================================================
  ADVANCED PING MONITOR - Pro Network Diagnostics Tool
  Author  : Parshaa
  Version : 2.0
  License : MIT
================================================================================
"""

import time
import json
import os
import csv
import sys
import socket
import statistics
import threading
import argparse
from datetime import datetime, timedelta
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from pythonping import ping as pyping
    PYTHONPING_AVAILABLE = True
except ImportError:
    PYTHONPING_AVAILABLE = False

try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
    COLOR = True
except ImportError:
    COLOR = False
    class _Dummy:
        def __getattr__(self, _): return ""
    Fore = Back = Style = _Dummy()

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
VERSION          = "2.0"
AUTHOR           = "Parsha"
DEFAULT_TIMEOUT  = 2
DEFAULT_INTERVAL = 1
DEFAULT_COUNT    = 4
DEFAULT_ALERT_MS = 150
ALERT_COOLDOWN_S = 30        # Suppress repeated alerts for N seconds
MAX_RTT_HISTORY  = 500       # Rolling window for stats
GRAPH_WIDTH      = 50        # ASCII graph width (columns)
LOG_MAX_ENTRIES  = 5000


# ──────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ──────────────────────────────────────────────────────────────────────────────

def _c(color_attr: str, text: str) -> str:
    """Apply colorama color only if color is enabled."""
    if not COLOR:
        return text
    return f"{getattr(Fore, color_attr.upper(), '')}{text}{Style.RESET_ALL}"


def resolve_host(host: str) -> str:
    """Resolve hostname to IP; return original string on failure."""
    try:
        return socket.gethostbyname(host)
    except socket.gaierror:
        return host


def percentile(data: list, pct: float) -> float:
    """Compute the p-th percentile of a sorted list."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_data) - 1)
    return round(sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (k - lo), 2)


def compute_jitter(rtts: list) -> float:
    """Mean absolute deviation between consecutive RTTs (RFC 3393 style)."""
    if len(rtts) < 2:
        return 0.0
    diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))]
    return round(statistics.mean(diffs), 2)


def ascii_spark(rtts: deque, width: int = GRAPH_WIDTH, max_val: float = None) -> str:
    """Render a compact ASCII bar graph of recent RTT values."""
    blocks = " _.,:-=+*#@"
    if not rtts:
        return ""
    vals = list(rtts)[-width:]
    hi = max_val or (max(vals) if max(vals) > 0 else 1)
    bar = ""
    for v in vals:
        idx = int((v / hi) * (len(blocks) - 1))
        bar += blocks[min(idx, len(blocks) - 1)]
    return bar


# ──────────────────────────────────────────────────────────────────────────────
# Core ping engine
# ──────────────────────────────────────────────────────────────────────────────

def _raw_ping(host: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    Single ICMP ping.  Falls back to a TCP connect on port 80 when
    pythonping is unavailable or fails (e.g., no root privileges).
    """
    ts = datetime.now().isoformat()

    if PYTHONPING_AVAILABLE:
        try:
            resp = pyping(host, count=1, timeout=timeout, verbose=False)
            if resp.success():
                return {"success": True,  "rtt": round(resp.rtt_avg_ms, 2), "host": host, "timestamp": ts}
            return {"success": False, "rtt": None, "host": host, "timestamp": ts, "error": "Timeout"}
        except Exception as exc:
            # Fall through to TCP fallback
            pass

    # TCP fallback — measures TCP connect latency (not ICMP)
    try:
        t0 = time.perf_counter()
        with socket.create_connection((host, 80), timeout=timeout):
            rtt = round((time.perf_counter() - t0) * 1000, 2)
        return {"success": True, "rtt": rtt, "host": host, "timestamp": ts, "method": "tcp"}
    except Exception as exc:
        return {"success": False, "rtt": None, "host": host, "timestamp": ts, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────────────────
# Per-host statistics tracker
# ──────────────────────────────────────────────────────────────────────────────

class HostStats:
    """Maintains rolling statistics for a single monitored host."""

    def __init__(self, host: str, alert_threshold: int = DEFAULT_ALERT_MS):
        self.host           = host
        self.ip             = resolve_host(host)
        self.alert_threshold = alert_threshold

        self.sent      = 0
        self.received  = 0
        self.lost      = 0
        self.rtts      = deque(maxlen=MAX_RTT_HISTORY)
        self.history   = deque(maxlen=MAX_RTT_HISTORY)   # bool per ping
        self.results   = []

        # Alert state
        self._last_alert_time: float = 0
        self._was_down: bool = False

    # ── derived ────────────────────────────────────────────────────────────────

    @property
    def loss_pct(self) -> float:
        return round((self.lost / self.sent * 100), 2) if self.sent else 0.0

    @property
    def min_rtt(self) -> float:
        return round(min(self.rtts), 2) if self.rtts else 0.0

    @property
    def max_rtt(self) -> float:
        return round(max(self.rtts), 2) if self.rtts else 0.0

    @property
    def avg_rtt(self) -> float:
        return round(statistics.mean(self.rtts), 2) if self.rtts else 0.0

    @property
    def stddev_rtt(self) -> float:
        return round(statistics.pstdev(self.rtts), 2) if len(self.rtts) > 1 else 0.0

    @property
    def jitter(self) -> float:
        return compute_jitter(list(self.rtts))

    @property
    def uptime_pct(self) -> float:
        return round((self.received / self.sent * 100), 2) if self.sent else 0.0

    def quality_label(self) -> tuple:
        """Return (label_str, color_str) based on current stats."""
        if self.loss_pct == 0 and self.avg_rtt < 50:
            return "EXCELLENT", "GREEN"
        if self.loss_pct < 2 and self.avg_rtt < 100:
            return "GOOD", "CYAN"
        if self.loss_pct < 10 and self.avg_rtt < 200:
            return "FAIR", "YELLOW"
        if self.loss_pct < 25:
            return "POOR", "MAGENTA"
        return "CRITICAL", "RED"

    # ── update ─────────────────────────────────────────────────────────────────

    def ingest(self, result: dict) -> list:
        """
        Record a ping result. Returns a list of alert strings that should
        be displayed (may be empty).
        """
        self.sent += 1
        success = result["success"]
        self.history.append(success)
        self.results.append(result)

        alerts = []

        if success:
            rtt = result["rtt"]
            self.rtts.append(rtt)
            self.received += 1

            # High-latency alert with cooldown
            if rtt > self.alert_threshold:
                now = time.time()
                if now - self._last_alert_time > ALERT_COOLDOWN_S:
                    alerts.append(f"HIGH LATENCY: {rtt}ms > threshold {self.alert_threshold}ms on {self.host}")
                    self._last_alert_time = now

            # Recovery alert
            if self._was_down:
                alerts.append(f"HOST RECOVERED: {self.host} is reachable again")
                self._was_down = False
        else:
            self.lost += 1
            if not self._was_down:
                self._was_down = True
                alerts.append(f"HOST DOWN: {self.host} is not responding")

        return alerts

    def summary_dict(self) -> dict:
        """Return a serialisable summary of current stats."""
        rtts_list = list(self.rtts)
        return {
            "host":       self.host,
            "ip":         self.ip,
            "sent":       self.sent,
            "received":   self.received,
            "lost":       self.lost,
            "loss_pct":   self.loss_pct,
            "uptime_pct": self.uptime_pct,
            "min_rtt":    self.min_rtt,
            "avg_rtt":    self.avg_rtt,
            "max_rtt":    self.max_rtt,
            "stddev_rtt": self.stddev_rtt,
            "jitter":     self.jitter,
            "p50_rtt":    percentile(rtts_list, 50),
            "p90_rtt":    percentile(rtts_list, 90),
            "p99_rtt":    percentile(rtts_list, 99),
            "quality":    self.quality_label()[0],
        }


# ──────────────────────────────────────────────────────────────────────────────
# Display engine
# ──────────────────────────────────────────────────────────────────────────────

class Display:
    """All terminal output logic in one place."""

    @staticmethod
    def banner():
        line = "=" * 68
        print(_c("cyan",    line))
        print(_c("green",   f"  ADVANCED PING MONITOR  v{VERSION}"))
        print(_c("yellow",  f"  Professional Network Diagnostics Tool"))
        print(_c("white",   f"  Author : {AUTHOR}"))
        print(_c("cyan",    line))

    @staticmethod
    def result_line(result: dict, seq: int):
        ts  = datetime.now().strftime("%H:%M:%S")
        host = result["host"]
        if result["success"]:
            rtt = result["rtt"]
            if rtt < 50:
                col, sym = "GREEN",  "OK"
            elif rtt < DEFAULT_ALERT_MS:
                col, sym = "YELLOW", "WARN"
            else:
                col, sym = "RED",    "HIGH"
            method = f" [{result.get('method','icmp').upper()}]" if "method" in result else ""
            print(_c(col, f"  [{ts}] #{seq:<5} {sym:<5}  {host:<30} {rtt:>8.2f} ms{method}"))
        else:
            err = result.get("error", "Timeout")
            print(_c("RED", f"  [{ts}] #{seq:<5} FAIL   {host:<30} {'---':>8}    ({err})"))

    @staticmethod
    def alert(msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(_c("RED", f"\n  *** ALERT [{ts}]: {msg} ***\n"))

    @staticmethod
    def stats_block(hs: HostStats, spark: bool = True):
        sep = "-" * 68
        ql, qc = hs.quality_label()
        rtts_list = list(hs.rtts)

        print(_c("cyan", f"\n  {sep}"))
        print(_c("yellow", f"  STATISTICS  --  {hs.host}  ({hs.ip})"))
        print(_c("cyan", f"  {sep}"))
        print(_c("white", f"  Packets   : Sent={hs.sent}  Received={hs.received}  Lost={hs.lost}  Loss={hs.loss_pct}%"))
        print(_c("white", f"  Uptime    : {hs.uptime_pct}%"))
        if hs.rtts:
            print(_c("white",
                f"  RTT (ms)  : Min={hs.min_rtt}  Avg={hs.avg_rtt}  Max={hs.max_rtt}  StdDev={hs.stddev_rtt}"))
            print(_c("white",
                f"  Percentile: P50={percentile(rtts_list,50)}  P90={percentile(rtts_list,90)}  P99={percentile(rtts_list,99)}"))
            print(_c("white", f"  Jitter    : {hs.jitter} ms"))
        print(_c(qc,    f"  Quality   : {ql}"))
        if spark and hs.rtts:
            graph = ascii_spark(hs.rtts)
            print(_c("cyan", f"  Trend     : [{graph}]  (left=old, right=new)"))
        print(_c("cyan", f"  {sep}\n"))

    @staticmethod
    def heatmap(hs: HostStats, cols: int = 60):
        """Print a small reachability heatmap from history."""
        history = list(hs.history)[-cols:]
        row = ""
        for ok in history:
            row += _c("GREEN", "#") if ok else _c("RED", ".")
        print(f"  Heatmap   : [{row}]  (# = up, . = down)")

    @staticmethod
    def multi_summary(all_stats: dict):
        """Summary table for multiple hosts."""
        print(_c("cyan", "\n  " + "=" * 68))
        print(_c("yellow", "  MULTI-HOST SUMMARY"))
        print(_c("cyan", "  " + "=" * 68))
        header = f"  {'HOST':<28} {'SENT':>5} {'LOSS%':>6} {'AVG':>7} {'P90':>7} {'JITTER':>7} {'QUALITY':<10}"
        print(_c("white", header))
        print(_c("cyan", "  " + "-" * 68))
        for host, hs in sorted(all_stats.items()):
            rtts_list = list(hs.rtts)
            p90 = percentile(rtts_list, 90) if rtts_list else 0
            ql, qc = hs.quality_label()
            row = (f"  {host:<28} {hs.sent:>5} {hs.loss_pct:>5.1f}%"
                   f" {hs.avg_rtt:>6.1f}ms {p90:>6.1f}ms {hs.jitter:>6.1f}ms  {ql:<10}")
            print(_c(qc, row))
        print(_c("cyan", "  " + "=" * 68 + "\n"))


# ──────────────────────────────────────────────────────────────────────────────
# Logger
# ──────────────────────────────────────────────────────────────────────────────

class Logger:
    """Thread-safe file logger with rotation."""

    def __init__(self, log_file: str = "ping_log.json"):
        self.log_file  = log_file
        self._lock     = threading.Lock()

    def save_session(self, session_meta: dict, all_stats: dict):
        """Append a session summary entry to the JSON log."""
        entry = {
            "session_end": datetime.now().isoformat(),
            "meta":        session_meta,
            "hosts":       {h: hs.summary_dict() for h, hs in all_stats.items()},
        }
        with self._lock:
            try:
                logs = []
                if os.path.exists(self.log_file):
                    with open(self.log_file, "r") as f:
                        logs = json.load(f)
                logs.append(entry)
                if len(logs) > LOG_MAX_ENTRIES:
                    logs = logs[-LOG_MAX_ENTRIES:]
                with open(self.log_file, "w") as f:
                    json.dump(logs, f, indent=2)
                print(_c("GREEN", f"\n  Log saved to {self.log_file}"))
            except Exception as exc:
                print(_c("RED", f"\n  Log save failed: {exc}"))

    def export_csv(self, all_stats: dict, filename: str = "ping_report.csv"):
        """Export all raw results to CSV."""
        try:
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Host", "IP", "Success", "RTT_ms", "Error", "Method"])
                for host, hs in all_stats.items():
                    ip = hs.ip
                    for r in hs.results:
                        writer.writerow([
                            r["timestamp"], r["host"], ip,
                            r["success"],
                            r["rtt"] if r["rtt"] is not None else "",
                            r.get("error", ""),
                            r.get("method", "icmp"),
                        ])
            print(_c("GREEN", f"  CSV exported to {filename}"))
        except Exception as exc:
            print(_c("RED", f"  CSV export failed: {exc}"))

    def export_json_summary(self, all_stats: dict, filename: str = "ping_summary.json"):
        """Export per-host summary stats to JSON."""
        data = {h: hs.summary_dict() for h, hs in all_stats.items()}
        try:
            with open(filename, "w") as f:
                json.dump(data, f, indent=2)
            print(_c("GREEN", f"  JSON summary exported to {filename}"))
        except Exception as exc:
            print(_c("RED", f"  JSON export failed: {exc}"))


# ──────────────────────────────────────────────────────────────────────────────
# Monitor orchestrator
# ──────────────────────────────────────────────────────────────────────────────

class PingMonitor:
    """High-level monitor: orchestrates pinging, stats, display, and logging."""

    def __init__(self):
        self.logger     = Logger()
        self.all_stats: dict[str, HostStats] = {}
        self._alert_threshold = DEFAULT_ALERT_MS
        self._session_start   = None

    # ── configuration ──────────────────────────────────────────────────────────

    def set_alert_threshold(self, ms: int):
        self._alert_threshold = ms
        for hs in self.all_stats.values():
            hs.alert_threshold = ms
        print(_c("GREEN", f"  Alert threshold set to {ms} ms"))

    def _get_or_create(self, host: str) -> HostStats:
        if host not in self.all_stats:
            self.all_stats[host] = HostStats(host, self._alert_threshold)
        return self.all_stats[host]

    # ── single-shot pings ──────────────────────────────────────────────────────

    def single_ping(self, host: str, count: int = DEFAULT_COUNT, timeout: int = DEFAULT_TIMEOUT):
        hs = self._get_or_create(host)
        print(_c("GREEN", f"\n  Sending {count} ping(s) to {host} ({hs.ip}) ...\n"))

        for i in range(1, count + 1):
            result = _raw_ping(host, timeout)
            alerts = hs.ingest(result)
            Display.result_line(result, i)
            for a in alerts:
                Display.alert(a)
            if i < count:
                time.sleep(1)

        Display.stats_block(hs)

    # ── continuous single-host ─────────────────────────────────────────────────

    def continuous_monitor(self, host: str, interval: float = DEFAULT_INTERVAL,
                           timeout: int = DEFAULT_TIMEOUT, stats_every: int = 10):
        hs = self._get_or_create(host)
        self._session_start = datetime.now()

        print(_c("GREEN",  f"\n  Starting continuous monitor: {host} ({hs.ip})"))
        print(_c("YELLOW", f"  Interval: {interval}s  |  Timeout: {timeout}s  |  Alert: {self._alert_threshold}ms"))
        print(_c("CYAN",   "  Press Ctrl+C to stop\n"))

        try:
            seq = 0
            while True:
                seq += 1
                result = _raw_ping(host, timeout)
                alerts = hs.ingest(result)
                Display.result_line(result, seq)
                for a in alerts:
                    Display.alert(a)

                if hs.sent % stats_every == 0:
                    Display.stats_block(hs)
                    Display.heatmap(hs)

                time.sleep(interval)

        except KeyboardInterrupt:
            print(_c("YELLOW", "\n\n  Monitoring stopped."))
        finally:
            Display.stats_block(hs)
            Display.heatmap(hs)
            self._save_session()

    # ── multi-host parallel ────────────────────────────────────────────────────

    def monitor_multiple_hosts(self, hosts: list, interval: float = 5,
                               timeout: int = DEFAULT_TIMEOUT, rounds: int = 0):
        """
        Ping all hosts in parallel each round.
        rounds=0 means infinite until Ctrl+C.
        """
        for h in hosts:
            self._get_or_create(h)

        self._session_start = datetime.now()
        print(_c("GREEN",  f"\n  Monitoring {len(hosts)} hosts in parallel"))
        print(_c("YELLOW", f"  Interval: {interval}s  |  Timeout: {timeout}s"))
        print(_c("CYAN",   "  Press Ctrl+C to stop\n"))

        round_num = 0
        try:
            while True:
                round_num += 1
                print(_c("cyan", f"  -- Round {round_num}  [{datetime.now().strftime('%H:%M:%S')}] " + "-" * 40))

                with ThreadPoolExecutor(max_workers=min(len(hosts), 20)) as pool:
                    futures = {pool.submit(_raw_ping, h, timeout): h for h in hosts}
                    for future in as_completed(futures):
                        host   = futures[future]
                        result = future.result()
                        hs     = self.all_stats[host]
                        alerts = hs.ingest(result)
                        Display.result_line(result, hs.sent)
                        for a in alerts:
                            Display.alert(a)

                Display.multi_summary(self.all_stats)

                if rounds and round_num >= rounds:
                    break

                time.sleep(interval)

        except KeyboardInterrupt:
            print(_c("YELLOW", "\n\n  Monitoring stopped."))
        finally:
            Display.multi_summary(self.all_stats)
            self._save_session()

    def monitor_from_file(self, filepath: str, interval: float = 5,
                          timeout: int = DEFAULT_TIMEOUT):
        """Load host list from file and run parallel monitoring."""
        try:
            with open(filepath, "r") as f:
                hosts = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        except FileNotFoundError:
            print(_c("RED", f"  File not found: {filepath}"))
            return

        if not hosts:
            print(_c("YELLOW", "  No hosts found in file."))
            return

        self.monitor_multiple_hosts(hosts, interval=interval, timeout=timeout)

    # ── export ─────────────────────────────────────────────────────────────────

    def export_csv(self, filename: str = "ping_report.csv"):
        if not self.all_stats:
            print(_c("YELLOW", "  No data to export."))
            return
        self.logger.export_csv(self.all_stats, filename)

    def export_json(self, filename: str = "ping_summary.json"):
        if not self.all_stats:
            print(_c("YELLOW", "  No data to export."))
            return
        self.logger.export_json_summary(self.all_stats, filename)

    def view_results(self, n: int = 20):
        if not self.all_stats:
            print(_c("YELLOW", "  No results yet."))
            return
        for host, hs in self.all_stats.items():
            print(_c("cyan", f"\n  Last {n} results for {host}:"))
            for r in hs.results[-n:]:
                sym = "OK  " if r["success"] else "FAIL"
                rtt = f"{r['rtt']:>8.2f} ms" if r["rtt"] is not None else "  ---     "
                print(f"    [{r['timestamp'][11:19]}] {sym}  {rtt}")

    # ── internals ──────────────────────────────────────────────────────────────

    def _save_session(self):
        if not self.all_stats:
            return
        meta = {
            "start":   self._session_start.isoformat() if self._session_start else None,
            "end":     datetime.now().isoformat(),
            "author":  AUTHOR,
            "version": VERSION,
        }
        self.logger.save_session(meta, self.all_stats)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def interactive_menu(monitor: PingMonitor):
    """Full interactive menu."""
    Display.banner()

    menu = [
        ("1",  "Continuous monitor  (single host)"),
        ("2",  "Quick ping test     (4 pings)"),
        ("3",  "Custom ping count"),
        ("4",  "Multi-host parallel (inline list)"),
        ("5",  "Multi-host parallel (from file)"),
        ("6",  "Set alert threshold"),
        ("7",  "Export results to CSV"),
        ("8",  "Export summary to JSON"),
        ("9",  "View recent results"),
        ("0",  "Exit"),
    ]

    while True:
        print(_c("CYAN", "\n  MAIN MENU"))
        print(_c("cyan", "  " + "-" * 40))
        for key, label in menu:
            print(_c("WHITE", f"  [{key}]  {label}"))
        print(_c("cyan", "  " + "-" * 40))

        choice = input(_c("GREEN", "  Select: ")).strip()

        if choice == "1":
            host     = input("  Host/IP: ").strip()
            interval = input("  Interval seconds [1]: ").strip()
            monitor.continuous_monitor(host, interval=float(interval) if interval else 1)

        elif choice == "2":
            host = input("  Host/IP: ").strip()
            monitor.single_ping(host, count=4)

        elif choice == "3":
            host  = input("  Host/IP: ").strip()
            count = input("  Number of pings: ").strip()
            monitor.single_ping(host, count=int(count) if count.isdigit() else 4)

        elif choice == "4":
            raw   = input("  Hosts (comma-separated): ").strip()
            hosts = [h.strip() for h in raw.split(",") if h.strip()]
            if hosts:
                ivl = input("  Interval seconds [5]: ").strip()
                monitor.monitor_multiple_hosts(hosts, interval=float(ivl) if ivl else 5)
            else:
                print(_c("YELLOW", "  No hosts entered."))

        elif choice == "5":
            path = input("  Hosts file path: ").strip()
            ivl  = input("  Interval seconds [5]: ").strip()
            monitor.monitor_from_file(path, interval=float(ivl) if ivl else 5)

        elif choice == "6":
            val = input(f"  Threshold ms [current={monitor._alert_threshold}]: ").strip()
            if val.isdigit():
                monitor.set_alert_threshold(int(val))

        elif choice == "7":
            fname = input("  CSV filename [ping_report.csv]: ").strip()
            monitor.export_csv(fname if fname else "ping_report.csv")

        elif choice == "8":
            fname = input("  JSON filename [ping_summary.json]: ").strip()
            monitor.export_json(fname if fname else "ping_summary.json")

        elif choice == "9":
            n = input("  How many recent results per host [20]: ").strip()
            monitor.view_results(int(n) if n.isdigit() else 20)

        elif choice == "0":
            print(_c("GREEN", "\n  Goodbye.\n"))
            break

        else:
            print(_c("RED", "  Invalid option."))

        if choice not in ("0",):
            input(_c("YELLOW", "\n  Press Enter to continue..."))


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ping_monitor",
        description=f"Advanced Ping Monitor v{VERSION} by {AUTHOR}",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("host",           nargs="?",                   help="Target host/IP")
    p.add_argument("-c", "--count",  type=int, default=0,         help="Ping count (0 = continuous)")
    p.add_argument("-i", "--interval",type=float, default=1,      help="Interval between pings (s)")
    p.add_argument("-t", "--timeout", type=int, default=2,        help="Ping timeout (s)")
    p.add_argument("-a", "--alert",   type=int, default=DEFAULT_ALERT_MS, help="Alert threshold (ms)")
    p.add_argument("-f", "--file",   metavar="FILE",              help="Hosts file for multi-host mode")
    p.add_argument("--csv",          metavar="FILE",              help="Auto-export CSV on exit")
    p.add_argument("--json",         metavar="FILE",              help="Auto-export JSON on exit")
    return p


def main():
    parser = build_argparser()
    args   = parser.parse_args()

    monitor = PingMonitor()
    monitor.set_alert_threshold(args.alert)

    # Non-interactive mode when host or file supplied
    if args.host or args.file:
        Display.banner()
        try:
            if args.file:
                monitor.monitor_from_file(args.file, interval=args.interval, timeout=args.timeout)
            elif args.count == 0:
                monitor.continuous_monitor(args.host, interval=args.interval, timeout=args.timeout)
            else:
                monitor.single_ping(args.host, count=args.count, timeout=args.timeout)
        finally:
            if args.csv:
                monitor.export_csv(args.csv)
            if args.json:
                monitor.export_json(args.json)
    else:
        interactive_menu(monitor)


if __name__ == "__main__":
    main()
