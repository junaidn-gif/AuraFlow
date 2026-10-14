"""Run with python main.py, or double-click Start_AuraFlow.bat on Windows."""
import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="AuraFlow hand control studio")
    parser.add_argument("--demo", action="store_true", help="Open synthetic demo without a webcam")
    args = parser.parse_args()
    # OpenCV's Linux wheel may override Qt plugin paths; use PySide's own plugins.
    os.environ.setdefault("QT_API", "pyside6")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    from auraflow.app import MainWindow
    app = QApplication(sys.argv)
    app.setApplicationName("AuraFlow")
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow(demo=args.demo)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
