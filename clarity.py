#!/usr/bin/env python3
"""
Main program file
"""

import multiprocessing as mp
from multiprocessing.connection import wait
import board
import busio
from adafruit_pca9685 import PCA9685
from adafruit_motor import servo
import hailo
import subprocess



def main():



    # Create pipe for vision worker
    vision_parent_conn, vision_child_conn = mp.Pipe()

    # Create pipe for voice worker
    voice_parent_conn, voice_child_conn = mp.Pipe()
    is_speaking = mp.Value('b', False)

    # Start vision multiprocessing worker
    vision_proc = mp.Process(
        target=run_vision,
        args=(vision_child_conn,)
    )
    vision_proc.start()

    # Start voice multiprocessing worker
    voice_proc = mp.Process(
        target=run_voice,
        args=(is_speaking, voice_child_conn)
    )
    voice_proc.start()

    parent_conns = [voice_parent_conn, vision_parent_conn]

    while vision_proc.is_alive() and voice_proc.is_alive() or True:
        ready_conns = wait(parent_conns)
        for conn in ready_conns:
            data = conn.recv()


            if conn == voice_parent_conn:
                is_speaking.value = True
                subprocess.run(f'espeak "{data}" --stdout | aplay -D softvol', shell=True)
                is_speaking.value = False
  






def run_vision(conn):
    from vision import vision
    vision(conn)

def run_voice(is_speaking, conn):
    from voice import voice
    voice(is_speaking, conn)

    


            


if __name__ == "__main__":
    main()
