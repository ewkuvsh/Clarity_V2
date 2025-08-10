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


SERVO_X_NEUTRAL = 75
SERVO_Y_NEUTRAL = 90

def main():

    #init servos
    i2c = busio.I2C(board.SCL, board.SDA)

    pca = PCA9685(i2c)
    pca.frequency = 50  # Set PWM frequency to 50Hz for servos

    y_servo = servo.Servo(pca.channels[14])
    x_servo = servo.Servo(pca.channels[15])

    # move both servos to center
    x_servo.angle = SERVO_X_NEUTRAL
    y_servo.angle = SERVO_Y_NEUTRAL


    # Create pipe for vision worker
    vision_parent_conn, vision_child_conn = mp.Pipe()

    # Create pipe for voice worker
    voice_parent_conn, voice_child_conn = mp.Pipe()

    # Start vision multiprocessing worker
    vision_proc = mp.Process(
        target=run_vision_worker,
        args=(vision_child_conn,)
    )
    vision_proc.start()

    # Start voice multiprocessing worker
    voice_proc = mp.Process(
        target=run_voice_worker,
        args=(voice_child_conn,)
    )
    voice_proc.start()

    parent_conns = [voice_parent_conn, vision_parent_conn]

    while vision_proc.is_alive() and voice_proc.is_alive() or True:
        ready_conns = wait(parent_conns)
        for conn in ready_conns:
            if conn == vision_parent_conn:
                handle_vision_detection(conn,x_servo, y_servo)

            print(conn.recv())



    # Cleanup
    if vision_proc and vision_proc.is_alive():
        vision_proc.terminate()
        vision_proc.join()

    if voice_proc and voice_proc.is_alive():
        voice_proc.terminate()
        voice_proc.join()

def run_vision_worker(conn):
    from vision import vision
    vision(conn)

def run_voice_worker(conn):
    from voice import voice
    voice(conn)


def handle_vision_detection(conn, x_servo, y_servo):
    """
    Handle vision detection and move servos accordingly.
    """
    while True:
        detections = conn.recv()

        bbox = detections[0].get_bbox()
        if bbox is not None:
            bbox_center_x = (bbox.xmin + bbox.xmax) / 2.0
            bbox_center_y = (bbox.ymin + bbox.ymax) / 2.0

            print("x: ", bbox_center_x, "y: ", bbox_center_y)


            

            


if __name__ == "__main__":
    main()
