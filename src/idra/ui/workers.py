import threading

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class Worker(QObject):
    result = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(float)
    done = pyqtSignal()
    def __init__(self, work, cancel: threading.Event):
        super().__init__()
        self.work, self.cancel = work, cancel
    @pyqtSlot()
    def run(self):
        try:
            self.result.emit(self.work(self.cancel, self.progress.emit))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.done.emit()
