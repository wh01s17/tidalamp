#!/usr/bin/env python3
"""A stand-in for cava: emits binary frames on stdout like the real one.

Reads the generated config to learn how many bars to send, so the test also
covers that we write a config cava could actually read.
"""

from __future__ import annotations

import os
import sys
import time


def main():
    config = sys.argv[sys.argv.index("-p") + 1]
    bars, frames = 19, None
    with open(config, encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("bars"):
                bars = int(line.split("=")[1])
    frames = int(os.environ.get("FAKE_CAVA_FRAMES", "0"))  # 0 = forever

    sent = 0
    while frames == 0 or sent < frames:
        # A ramp, so the test can tell band order apart.
        payload = bytes((i * 255) // max(1, bars - 1) for i in range(bars))
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        sent += 1
        time.sleep(0.02)


if __name__ == "__main__":
    main()
