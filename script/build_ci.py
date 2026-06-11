"""CI build script for GitHub Actions - Windows."""
import os
import sys
import subprocess
import shutil
from pathlib import Path


def main():
    version = os.environ.get("CI_VERSION", "").lstrip("v")
    if not version:
        print("ERROR: CI_VERSION environment variable not set")
        sys.exit(1)

    upx_path = os.environ.get("UPX_EXE", "")
    project_dir = Path(__file__).resolve().parent.parent
    dist_dir = project_dir / "dist" / "WeChatSpider"

    print(f"Project: {project_dir}")
    print(f"Version: {version}")
    print(f"UPX: {upx_path or 'not set'}")

    # Clean
    for d in [project_dir / "dist", project_dir / "build"]:
        if d.exists():
            shutil.rmtree(d)
            print(f"Cleaned {d}")

    # Run PyInstaller
    print("\n[4/6] Running PyInstaller...")
    cmd = ["pyinstaller", "--clean", "--noconfirm"]
    if upx_path:
        upx_dir = str(Path(upx_path).parent)
        cmd.extend(["--upx-dir", upx_dir])
        print(f"Using UPX dir: {upx_dir}")
    cmd.append("WeChatSpider.spec")

    result = subprocess.run(cmd, cwd=str(project_dir))
    if result.returncode != 0:
        print("ERROR: PyInstaller failed")
        sys.exit(1)

    # Copy icon
    icon = project_dir / "gnivu-cfd69-001.ico"
    if icon.exists():
        shutil.copy2(str(icon), str(dist_dir / icon.name))

    # UPX post-compression
    print("\n[5/6] UPX post-compression...")
    if upx_path and os.path.exists(upx_path):
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
        print(f"DLL: compressed {compress_count}, skipped {skip_count}")

        pyd_count = 0
        for f in dist_dir.rglob("*.pyd"):
            r = subprocess.run([upx_path, "-t", str(f)], capture_output=True)
            if r.returncode != 0:
                r = subprocess.run([upx_path, "--best", "--lzma", str(f)],
                                   capture_output=True)
                if r.returncode == 0:
                    pyd_count += 1
        print(f"PYD: compressed {pyd_count} files")
    else:
        print("Skipping UPX post-compression")

    # Cleanup
    print("\n[6/6] Cleanup...")
    for pattern in ["*test*.py", "*_test.py"]:
        for f in dist_dir.rglob(pattern):
            f.unlink(missing_ok=True)
    for d in list(dist_dir.rglob("__pycache__")):
        shutil.rmtree(d, ignore_errors=True)
    for f in dist_dir.rglob("*.pyc"):
        f.unlink(missing_ok=True)

    print(f"\nBuild OK! Version: {version}")


if __name__ == "__main__":
    main()
