import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="dataforge-scheduler", description="Start a Dask scheduler."
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8786, help="Port to listen on (default: 8786)"
    )

    args = parser.parse_args()

    cmd = [
        sys.executable,
        "-m",
        "dask",
        "scheduler",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]

    # 打印启动信息到 stderr（不影响 stdout，且 exec 后不会残留）
    print("🚀 Starting Dask Scheduler", file=sys.stderr)
    print(f"   Address: {args.host}:{args.port}", file=sys.stderr)
    print(f"   Dashboard: http://{args.host}:8787", file=sys.stderr)
    print(f"   Command: {' '.join(cmd)}\n", file=sys.stderr)

    # 直接替换当前进程为 dask scheduler
    os.execvp(sys.executable, cmd)
