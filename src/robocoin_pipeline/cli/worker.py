import argparse
import os
import shutil
import subprocess
import sys


def get_physical_resources():
    """Detect physical system resources (CPU, memory, GPU) without extra dependencies."""
    # CPU: logical core count
    try:
        import multiprocessing

        cpu = multiprocessing.cpu_count()
    except Exception:
        cpu = 4

    # Memory: total RAM in GB
    mem_gb = 8  # fallback default
    try:
        if sys.platform == "linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        mem_gb = kb // 1024 // 1024
                        break
        elif sys.platform == "darwin":  # macOS
            result = subprocess.run(
                ["sysctl", "hw.memsize"], capture_output=True, text=True
            )
            if result.returncode == 0:
                bytes_total = int(result.stdout.split()[-1])
                mem_gb = bytes_total // (1024**3)
    except Exception:
        pass

    # GPU: NVIDIA only (via nvidia-smi)
    gpu = 0
    if shutil.which("nvidia-smi"):
        try:
            result = subprocess.run(
                ["nvidia-smi", "-L"], capture_output=True, text=True
            )
            if result.returncode == 0:
                gpu = len([line for line in result.stdout.strip().split("\n") if line])
        except Exception:
            pass

    return cpu, mem_gb, gpu


def main():
    parser = argparse.ArgumentParser(
        prog="dataforge-worker",
        description="Start a Dask Worker with automatic resource limits based on system capacity.",
    )
    parser.add_argument(
        "scheduler",
        nargs="?",
        default="tcp://127.0.0.1:8786",
        help="Scheduler address (default: tcp://127.0.0.1:8786)",
    )
    parser.add_argument(
        "--cpu", type=int, default=4, help="Requested CPU units (default: 4)"
    )
    parser.add_argument(
        "--mem", type=int, default=8, help="Requested memory in GB (default: 8)"
    )
    parser.add_argument(
        "--gpu", type=int, default=0, help="Requested number of GPUs (default: 0)"
    )

    args = parser.parse_args()

    # Detect physical resources
    phys_cpu, phys_mem, phys_gpu = get_physical_resources()

    # Apply safety headroom
    alloc_cpu = min(max(1, args.cpu), phys_cpu - 1 if phys_cpu > 1 else 1)
    alloc_mem = min(max(1, args.mem), phys_mem - 4 if phys_mem > 4 else 1)
    alloc_gpu = min(max(0, args.gpu), phys_gpu)

    # Build resource string
    resources = f"CPU={alloc_cpu},MEMORY_GB={alloc_mem}"
    if alloc_gpu > 0:
        resources += f",GPU={alloc_gpu}"

    cmd = [
        sys.executable,
        "-m",
        "dask",
        "worker",
        args.scheduler,
        "--nthreads",
        str(alloc_cpu),
        "--memory-limit",
        f"{alloc_mem}GB",
        "--resources",
        resources,
    ]

    print("💻 Starting Dask Worker")
    print(f"   Scheduler: {args.scheduler}")
    print(f"   Requested: CPU={args.cpu}, MEM={args.mem}GB, GPU={args.gpu}")
    print(f"   Allocated: CPU={alloc_cpu}, MEM={alloc_mem}GB, GPU={alloc_gpu}")
    print(f"   System max: CPU={phys_cpu}, MEM={phys_mem}GB, GPU={phys_gpu}")

    os.execvp(sys.executable, cmd)
