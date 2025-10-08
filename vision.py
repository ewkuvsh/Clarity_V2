#!/usr/bin/env python3
"""
Vision worker - simplified with idle, sweep, and track modes
"""

# region imports
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import cv2
import sys
import hailo
from hailo_apps.hailo_app_python.core.common.buffer_utils import get_caps_from_pad, get_numpy_from_buffer
from hailo_apps.hailo_app_python.core.gstreamer.gstreamer_app import app_callback_class
from custom_pipeline import GStreamerDetectionApp
import board
import busio
from adafruit_pca9685 import PCA9685
from adafruit_motor import servo
import time
import random
# endregion imports

# Servo settings
SERVO_X_NEUTRAL = 75
SERVO_Y_NEUTRAL = 90

# Tracking sensitivity
TRACKING_STEP = 5  # Degrees to move per frame (increased from 2)
DEADZONE_MIN = 0.40  # More aggressive deadzone (was 0.45)
DEADZONE_MAX = 0.60  # More aggressive deadzone (was 0.55)

class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        self.x_servo = None
        self.y_servo = None
        self.latest_detections = []
        self.mode = "idle"  # idle, tracking, sweeping
        self.sweep_start_angle = None
        self.sweep_target_angle = None
        self.sweep_steps = 0
        self.sweep_max_steps = 0

def app_callback(pad, info, user_data):
    buffer = info.get_buffer()
    if buffer is None:
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
        if label in ["person", "cat"]:
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

    user_data.latest_detections = detection_results

    # Handle different modes
    if user_data.mode == "tracking" and detection_results:
        # Track the first thing we see
        handle_tracking(detection_results[0], user_data)
    elif user_data.mode == "sweeping":
        handle_sweeping(user_data)

    return Gst.PadProbeReturn.OK

def handle_tracking(detection, user_data):
    """Track whatever detection is provided"""
    bbox = detection['bbox']
    bbox_center_x = (bbox.xmin() + bbox.xmax()) / 2.0
    bbox_center_y = (bbox.ymin() + bbox.ymax()) / 2.0
    
    # Calculate error from center with proportional control
    x_error = bbox_center_x - 0.5
    y_error = bbox_center_y - 0.5
    
    # Use proportional control for smoother, more responsive tracking
    x_step = int(x_error * 20)  # Scale error to movement (max ~10 degrees)
    y_step = int(y_error * 20)
    
    # Clamp to reasonable step sizes
    x_step = max(-10, min(10, x_step))
    y_step = max(-10, min(10, y_step))
    
    # Move X servo (left/right)
    if bbox_center_x > DEADZONE_MAX:  # Target is to the right
        new_angle = user_data.x_servo.angle - abs(x_step)
        if new_angle >= 0:
            user_data.x_servo.angle = new_angle
    elif bbox_center_x < DEADZONE_MIN:  # Target is to the left
        new_angle = user_data.x_servo.angle + abs(x_step)
        if new_angle <= 180:
            user_data.x_servo.angle = new_angle
            
    # Move Y servo (up/down)
    if bbox_center_y > DEADZONE_MAX:  # Target is below center
        new_angle = user_data.y_servo.angle + abs(y_step)
        if new_angle <= 180:
            user_data.y_servo.angle = new_angle
    elif bbox_center_y < DEADZONE_MIN:  # Target is above center
        new_angle = user_data.y_servo.angle - abs(y_step)
        if new_angle >= 0:
            user_data.y_servo.angle = new_angle

def handle_sweeping(user_data):
    """Quick sweep that stops at a random angle"""
    if user_data.sweep_steps >= user_data.sweep_max_steps:
        # Sweep complete - go back to idle
        user_data.mode = "idle"
        print(f"Sweep complete, stopped at angle {user_data.x_servo.angle}")
        return
    
    # Interpolate between start and target angle
    progress = user_data.sweep_steps / user_data.sweep_max_steps
    current_angle = user_data.sweep_start_angle + (user_data.sweep_target_angle - user_data.sweep_start_angle) * progress
    
    if 0 <= current_angle <= 180:
        user_data.x_servo.angle = int(current_angle)
    
    user_data.sweep_steps += 1

def worker_function(conn_incoming):
    global conn
    conn = conn_incoming
    
    # Init servos
    i2c = busio.I2C(board.SCL, board.SDA)
    pca = PCA9685(i2c)
    pca.frequency = 50

    original_argv = sys.argv.copy()
    sys.argv = ['worker_process', '--input', 'rpi', '--frame-rate', '25']
    user_data = user_app_callback_class()
    user_data.y_servo = servo.Servo(pca.channels[14])
    user_data.x_servo = servo.Servo(pca.channels[15])

    # Center servos
    user_data.x_servo.angle = SERVO_X_NEUTRAL
    user_data.y_servo.angle = SERVO_Y_NEUTRAL

    user_data.latest_detections = []
    app = GStreamerDetectionApp(app_callback, user_data)
    sys.argv = original_argv

    import threading
    gst_thread = threading.Thread(target=app.run, daemon=True)
    gst_thread.start()

    last_sent = None
    while True:
        # Check for commands from parent process
        if conn.poll(0.001):
            try:
                command = conn.recv()
                if isinstance(command, dict):
                    if command.get("command") == "sweep":
                        # Start a quick sweep to a random angle
                        user_data.mode = "sweeping"
                        user_data.sweep_start_angle = user_data.x_servo.angle
                        # Pick a random target angle (30-120 degrees range)
                        user_data.sweep_target_angle = random.randint(30, 120)
                        # Short sweep: 20-40 steps (about 1-2 seconds at 25fps)
                        user_data.sweep_max_steps = random.randint(20, 40)
                        user_data.sweep_steps = 0
                        print(f"Starting quick sweep from {user_data.sweep_start_angle}° to {user_data.sweep_target_angle}°")
                        
                    elif command.get("command") == "track":
                        user_data.mode = "tracking"
                        print("Starting tracking mode - will follow first detected object")
                        
                    elif command.get("command") == "idle":
                        user_data.mode = "idle"
                        print("Returning to idle mode")
            except:
                pass

        # Send detection updates
        if user_data.latest_detections != last_sent:
            try:
                conn.send(user_data.latest_detections)
                last_sent = list(user_data.latest_detections)
            except (BrokenPipeError, IOError):
                break
        
        time.sleep(0.01)

def vision(conn):
    worker_function(conn)
