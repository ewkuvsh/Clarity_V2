#!/usr/bin/env python3
"""
Vision worker
"""


# region imports
# Standard library imports

# Third-party imports
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import cv2
import sys
# Local application-specific imports
import hailo
from hailo_apps.hailo_app_python.core.common.buffer_utils import get_caps_from_pad, get_numpy_from_buffer
from hailo_apps.hailo_app_python.core.gstreamer.gstreamer_app import app_callback_class
from custom_pipeline import GStreamerDetectionApp
import board
import busio
from adafruit_pca9685 import PCA9685
from adafruit_motor import servo
import hailo
# endregion imports

# -----------------------------------------------------------------------------------------------
# User-defined class to be used in the callback function
# -----------------------------------------------------------------------------------------------
# Inheritance from the app_callback_class
class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        self.new_variable = 42  # New variable example

    def new_function(self):  # New function example
        return "The meaning of life is: "

# -----------------------------------------------------------------------------------------------
# User-defined callback function
# -----------------------------------------------------------------------------------------------


SERVO_X_NEUTRAL = 75
SERVO_Y_NEUTRAL = 90



def app_callback(pad, info, user_data):
    buffer = info.get_buffer()
    if buffer is None:
        # Ensure we clear detections if the buffer is empty
        user_data.latest_detections = []
        return Gst.PadProbeReturn.OK

    user_data.increment()
    format, width, height = get_caps_from_pad(pad)
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    detection_results = []
    for detection in detections:
        label = detection.get_label()
        bbox = detection.get_bbox()
        confidence = detection.get_confidence()
        if label == "person":
            track_id = 0
            track = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
            if len(track) == 1:
                track_id = track[0].get_id()
            detection_results.append({
                "id": track_id,
                "label": label,
                "confidence": confidence,
                "bbox": bbox
            })
            handle_vision_detection(detection_results, user_data.x_servo, user_data.y_servo)

    # Always update, even if empty
    user_data.latest_detections = detection_results

    return Gst.PadProbeReturn.OK

def worker_function(conn_incoming):
    global conn
    conn = conn_incoming
    
    
    #init servos
    i2c = busio.I2C(board.SCL, board.SDA)

    pca = PCA9685(i2c)
    pca.frequency = 50  # Set PWM frequency to 50Hz for servos

    user_data.y_servo = servo.Servo(pca.channels[14])
    user_data.x_servo = servo.Servo(pca.channels[15])

    # move both servos to center
    user_data.x_servo.angle = SERVO_X_NEUTRAL
    user_data.y_servo.angle = SERVO_Y_NEUTRAL



    original_argv = sys.argv.copy()
    sys.argv = ['worker_process', '--input', 'rpi', '--frame-rate', '30']
    user_data = user_app_callback_class()
    user_data.latest_detections = []
    app = GStreamerDetectionApp(app_callback, user_data)
    sys.argv = original_argv

    import threading
    gst_thread = threading.Thread(target=app.run, daemon=True)
    gst_thread.start()

    import time
    last_sent = None
    while True:
        # Only send if new data is available

        if user_data.latest_detections != last_sent:
            try:
                conn.send(user_data.latest_detections)
                last_sent = list(user_data.latest_detections)  # Make a copy to compare
            except (BrokenPipeError, IOError):
                break
        time.sleep(0.001)  # Small sleep to avoid busy-waiting

def vision(conn):
    worker_function(conn)


def handle_vision_detection(detections, x_servo, y_servo):

    max_confidence = 0
    current_focus = None

    for detection in detections:
        if detection['confidence'] >= max_confidence:
            current_focus = detection 
        
    if current_focus != None:
        bbox = current_focus['bbox']
        if bbox is not None:
            bbox_center_x = (bbox.xmin() + bbox.xmax()) / 2.0
            bbox_center_y = (bbox.ymin() + bbox.ymax()) / 2.0 

            if bbox_center_x > 0.53:
                x_servo.angle = x_servo.angle - 5
            if bbox_center_x < 0.47:
                x_servo.angle = x_servo.angle + 5

            print("x: ", bbox_center_x, "y: ", bbox_center_y)


            
#if __name__ == "__main__":
#    import multiprocessing as mp
#    parent_conn, child_conn = mp.Pipe()
#    p = mp.Process(target=vision, args=(child_conn,))
#    p.start()
#    while True:
#        print(parent_conn.recv())
