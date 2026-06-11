"""CI build script for GitHub Actions - Windows."""
import os
import sys
import subprocess
import shutil
import traceback
from pathlib import Path


def log(msg):
    print(msg, flush=True)


def main():
    log("=" * 50)
    log("WeChat Spider CI Build Script (Python)")
    log("=" * 50)

    env_vars = {k: v for k, v in sorted(os.environ.items())
                if k.startswith(("CI_", "UPX_", "GITHUB_", "RUNNER_"))}
    for k, v in env_vars.items():
        log(f"  {k}={v}")

    version = os.environ.get("CI_VERSION", "").lstrip("v")
    if not version:
        log("ERROR: CI_VERSION env var not set")
        log(f"All env vars with CI_: {[(k, v) for k, v in os.environ.items() if 'CI' in k.upper()]}")
        sys.exit(1)

    upx_path = os.environ.get("UPX_EXE", "")
    project_dir = Path(__file__).resolve().parent.parent

    log(f"Project: {project_dir}")
    log(f"Version: {version}")
    log(f"UPX: {upx_path or 'not set'}")

    # Clean
    log("\n[Clean] Removing dist/build...")
    for d in [project_dir / "dist", project_dir / "build"]:
        if d.exists():
            shutil.rmtree(d)
            log(f"  Removed {d.name}")

    # Run PyInstaller
    log("\n[PyInstaller] Starting...")
    cmd = ["pyinstaller", "--clean", "--noconfirm"]
    if upx_path:
        upx_dir = str(Path(upx_path).parent)
        cmd.extend(["--upx-dir", upx_dir])
        log(f"  UPX dir: {upx_dir}")
    cmd.append("WeChatSpider.spec")
    log(f"  Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=str(project_dir), capture_output=False)
    if result.returncode != 0:
        log(f"ERROR: PyInstaller failed (exit code {result.returncode})")
        sys.exit(1)

    # Copy icon
    dist_dir = project_dir / "dist" / "WeChatSpider"
    icon = project_dir / "gnivu-cfd69-001.ico"
    if icon.exists():
        shutil.copy2(str(icon), str(dist_dir / icon.name))
        log("Icon copied")

    # UPX post-compression
    log("\n[UPX] Post-compression...")
    if upx_path and os.path.exists(upx_path):
        log(f"  UPX found at {upx_path}")
        exe = dist_dir / "WeChatSpider.exe"
        if exe.exists():
            subprocess.run([upx_path, "-t", str(exe)], capture_output=True)
            subprocess.run([upx_path, "--best", "--lzma", str(exe)], capture_output=True)

        skip_dlls = ["Qt6WebEngine", "Qt6Quick", "vcruntime", "ucrtbase",
                     "api-ms-win", "msvcp", "python3"]
        compress_count = 0
        skip_count = 0
        for f in dist_dir.rglob("*.dll"):
            if any(s in f.name for s in skip_dlls):
                skip_count += 1
                continue
            r = subprocess.run([upx_path, "-t", str(f)], capture_output=True)
            if r.returncode != 0:
                r = subprocess.run([upx_path, "--best", "--lzma", str(f)],
                                   capture_output=True)
                if r.returncode == 0:
                    compress_count += 1
        log(f"  DLL: compressed {compress_count}, skipped {skip_count}")
    else:
        log("  Skipping UPX")

    # Cleanup
    log("\n[Cleanup] Removing test files...")
    for pattern in ["*test*.py", "*_test.py"]:
        for f in dist_dir.rglob(pattern):
            f.unlink(missing_ok=True)
    for d in list(dist_dir.rglob("__pycache__")):
        shutil.rmtree(d, ignore_errors=True)
    for f in dist_dir.rglob("*.pyc"):
        f.unlink(missing_ok=True)

    log(f"\n Build OK! Version: {version}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
