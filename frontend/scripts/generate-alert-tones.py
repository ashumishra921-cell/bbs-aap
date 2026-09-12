"""Generate two short, original notification chimes as bundled PCM assets."""
import math
import struct
import wave
from pathlib import Path

folder = Path(__file__).resolve().parents[1] / "assets" / "sounds"
folder.mkdir(parents=True, exist_ok=True)
for name, notes in {"complaint": [660, 880], "payment": [784, 988, 1175]}.items():
    frames = []
    rate = 22050
    for frequency in notes:
        for n in range(int(rate * 0.19)):
            t = n / rate
            envelope = min(t / 0.012, 1) * max(0, 1 - t / 0.19) ** 2
            frames.append(struct.pack("<h", int(13000 * envelope * math.sin(2 * math.pi * frequency * t))))
    with wave.open(str(folder / f"{name}.wav"), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"".join(frames))