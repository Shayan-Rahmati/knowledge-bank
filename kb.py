"""Entry point. Run with: python kb.py"""
import os
import sys
import subprocess
import argparse
import importlib
from kb_config import PIP_EXTRA, NOWIN, externally_managed
from kb_core import App          # the window (kb_ui) is imported only after the Qt check, so a missing PySide6 is handled

def ensure_qt():
    try:
        import PySide6  # noqa
        return True
    except ImportError:
        pass
    print("The desktop window needs PySide6 (a one-time install, about 150 MB).")
    if sys.platform.startswith("linux"):
        print("On Ubuntu/Debian you can use the system packages instead of pip:")
        print("  sudo apt install python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets python3-pyside6.qtsvg")
        print("Otherwise the installer below uses pip into your user folder (no admin rights).")
    # Without a terminal (a script, a service, a scheduled task) nothing is installed silently: the user runs --install.
    if not (sys.stdin and sys.stdin.isatty()):
        print("Not running in a terminal, so nothing was installed. Run:  python3 kb.py --install")
        return False
    try:
        ans = input("Install it now? [Y/n] ")
    except (EOFError, KeyboardInterrupt):
        return False
    if ans.strip().lower() not in ("", "y", "yes"):
        return False
    cmd = [sys.executable, "-m", "pip", "install", "--user", "--disable-pip-version-check", "--progress-bar", "on"]
    if externally_managed():
        cmd.append("--break-system-packages")  # installs into the user folder only (--user)
    cmd += PIP_EXTRA
    cmd.append("PySide6")
    print("\nInstalling PySide6 — pip shows the download progress below. This takes a minute or two...\n")
    rc = subprocess.call(cmd, **NOWIN)  # pip inherits the terminal, so its progress bar shows
    if rc != 0:
        print("\nThe install did not finish. If the message above says 'name resolution' or 'connection', the network\n"
              "is blocking or failing to reach the package server. Options:\n"
              "  1) python3 kb.py --pip-index https://<a-pypi-mirror>/simple\n"
              "  2) on a machine with internet: pip download PySide6 -d wheels   then copy the folder here and run\n"
              "     python3 kb.py --wheels wheels\n"
              "  3) WSL only: fix DNS (nameserver 1.1.1.1 in /etc/resolv.conf), then run again.")
        return False
    try:
        import site
        sp = site.getusersitepackages()
        if sp not in sys.path:
            sys.path.append(sp)  # the user site folder may be new since Python started
    except Exception:
        pass
    importlib.invalidate_caches()
    try:
        import PySide6  # noqa
        print("\nPySide6 installed. Starting Knowledge Bank...\n")
        return True
    except ImportError:
        print("\nInstalled. Please start the app again:  python3 kb.py")
        return False


def main():
    ap = argparse.ArgumentParser(description="Knowledge Bank (native Python desktop app)")
    ap.add_argument("--add", action="append", default=[], help="add a folder or file, index it, and exit (no window)")
    ap.add_argument("--pip-index", help="PyPI mirror URL to use for pip installs (…/simple)")
    ap.add_argument("--wheels", help="folder of downloaded .whl files for an offline pip install")
    ap.add_argument("--install", action="store_true", help="pip-install PySide6 and the optional packages, then exit")
    ap.add_argument("--diagnose", action="store_true", help="write data/logs/diagnostic.txt with the system state, then exit")
    a = ap.parse_args()
    from kb_log import enable_debug_trace
    enable_debug_trace()
    if a.pip_index:
        PIP_EXTRA.extend(["--index-url", a.pip_index])
    if a.wheels:
        PIP_EXTRA.extend(["--no-index", "--find-links", os.path.abspath(a.wheels)])
    if a.install:
        pk = ["PySide6", "numpy", "pypdf"]
        sys.exit(subprocess.call([sys.executable, "-m", "pip", "install", "--user"] + PIP_EXTRA + pk))
    if a.diagnose:
        from kb_log import snapshot
        from kb_config import DATA
        core = App()
        try:
            snapshot(core)
            print(os.path.join(DATA, 'logs', 'diagnostic.txt'))
        finally:
            core.close()
        return
    if a.add:
        core = App()
        for p in a.add:
            core.add_source(p)
        core.sync(force=True)
        print("indexed %d passages" % core.ix.N)
        return
    if not ensure_qt():
        sys.exit(1)
    from kb_log import install_qt_handler
    from kb_ui import run_gui
    install_qt_handler()
    core = App()
    try:
        code = run_gui(core)
    finally:
        core.close()           # stop background work and close the database
    sys.exit(code)


if __name__ == "__main__":
    main()
