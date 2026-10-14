"""Create an isolated environment, install once, then launch the app."""
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import venv


def main():
    if sys.version_info[:2] not in ((3, 11), (3, 12)) or struct.calcsize("P") != 8:
        print("AuraFlow needs 64-bit Python 3.11 or 3.12. Install it from https://www.python.org/downloads/windows/")
        return 1
    root = Path(__file__).resolve().parent
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        print("Creating AuraFlow's private Python environment…", flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    requirements = root / "requirements.txt"
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = environment / ".auraflow-dependencies"
    if not stamp.exists() or stamp.read_text() != fingerprint:
        print("Installing app dependencies. The first launch needs internet and may take a few minutes.", flush=True)
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(requirements)], cwd=root, check=True)
        stamp.write_text(fingerprint)
    if "--install-only" in sys.argv:
        return 0
    args = [arg for arg in sys.argv[1:] if arg == "--demo"]
    return subprocess.call([str(python), str(root / "main.py"), *args], cwd=root)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, subprocess.CalledProcessError) as exc:
        print("\nSetup could not finish:", exc)
        print("Check your connection and that the extracted app folder is writable, then launch again.")
        sys.exit(1)
