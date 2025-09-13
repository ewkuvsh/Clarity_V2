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
from clarity_intelligence import handle_input
import smbus2
import time


def main():

    last_seen = time.time()
    bus = smbus2.SMBus(1)
    change_color(bus, 'w')


    vision_parent_conn, vision_child_conn = mp.Pipe()

    voice_parent_conn, voice_child_conn = mp.Pipe()

    is_speaking = mp.Value('b', False)


    vision_proc = mp.Process(
        target=run_vision,
        args=(vision_child_conn,)
    )

    voice_proc = mp.Process(
        target=run_voice,
        args=(is_speaking, voice_child_conn)
    )

    vision_proc.start()
    voice_proc.start()

    parent_conns = [voice_parent_conn, vision_parent_conn]

    while vision_proc.is_alive() and voice_proc.is_alive():
        ready_conns = wait(parent_conns)
        for conn in ready_conns:
            data = conn.recv()


            if conn == voice_parent_conn:
                change_color(bus, 'g')
                is_speaking.value = True
                subprocess.run(f'espeak "{handle_input(data)}" --stdout | aplay -D softvol', shell=True)
                is_speaking.value = False
                change_color(bus, 'w')

            if conn == vision_parent_conn:
                if time.time()  > last_seen + 25200:
                    subprocess.run(f'espeak hello again --stdout | aplay -D softvol', shell=True)

                last_seen = time.time()
                    
                    

    change_color(bus, 'r')
  






def run_vision(conn):
    from vision import vision
    vision(conn)

def run_voice(is_speaking, conn):
    from voice import voice
    voice(is_speaking, conn)

def change_color(bus, value):
    #value is a lowercase character which is the first letter of the desired color
    device_address = 0x28
    bus.write_byte(device_address, ord(value))

if __name__ == "__main__":
    main()
