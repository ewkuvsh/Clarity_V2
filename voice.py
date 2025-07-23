#!/usr/bin/env python3
"""
Voice worker
"""
import json
import pyaudio
import vosk

def obtain_processed_data(recognizer, data):
    if recognizer.AcceptWaveform(data):
        result = recognizer.Result()
        user_input = json.loads(result)["text"]
        print("onboard result:" + user_input)
        return True, user_input
    return False, ""

def voice(conn):
    model = vosk.Model("/home/evan/clarity/vosk-model-small-en-us-0.15")
    recognizer = vosk.KaldiRecognizer(model, 44100)  # Changed to 44100
    
    # Set up PyAudio to capture the microphone input at 44.1kHz
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=44100,  # 44.1kHz sample rate
        input=True,
        frames_per_buffer=8000,  # Larger buffer for 44.1kHz
    )
    stream.start_stream()
    
    print("Start speaking...")
    while True:
        data = stream.read(8000, exception_on_overflow=False)  # Read 8000 frames
        accepted, user_input = obtain_processed_data(recognizer, data)
        
        if accepted:
            print(user_input)
            # Send recognized text through the pipe
            if conn:
                conn.send(user_input)

def worker_function(conn):
    voice(conn)

if __name__ == "__main__":
    voice(None)