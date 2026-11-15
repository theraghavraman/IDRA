"""Explicit synthetic fixture provider. Never used by the GUI capture path."""
import cv2
import numpy as np


class SyntheticSource:
    synthetic = True
    timestamp_kind = "synthetic"
    def __init__(self, width=640, height=360):
        self.width, self.height, self.index = width, height, 0
        self.geometry = {"left": 0, "top": 0, "width": width, "height": height,
                         "monitor": 1, "backend": "synthetic_fixture"}
    def open(self):
        return self.geometry
    def grab(self):
        frame = np.zeros((self.height, self.width, 3), np.uint8)
        frame[:] = (32, 25, 18)
        for x in range(0, self.width, 40):
            cv2.line(frame, (x, 0), (x, self.height - 1), (60, 60, 60), 1)
        x = (self.index * 13) % max(1, self.width - 100)
        cv2.rectangle(frame, (x, 140), (x + 80, 220), (180, 160, 80), -1)
        cv2.putText(frame, "SYNTHETIC TEST FIXTURE - NOT A REAL RECORDING", (10, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (240, 240, 240), 1)
        cv2.putText(frame, f"Frame {self.index}", (10, 65), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (240, 240, 240), 1)
        self.index += 1
        return frame
    def close(self):
        return None
    def interrupt(self):
        return None
