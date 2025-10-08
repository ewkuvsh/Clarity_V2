#!/usr/bin/env python3
import pyaudio
import json
import vosk
import sys
import multiprocessing as mp

def find_respeaker_device():
    """Finds the respeaker"""
    p = pyaudio.PyAudio()
    respeaker_index = None
    
    print("Available devices:", flush=True)
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            print(f"  {i}: {info['name']} (channels: {info['maxInputChannels']})", flush=True)
            name = info['name'].lower()
            if 'respeaker' in name or 'usb audio' in name:
                respeaker_index = i
                print(f"    ^ Found potential ReSpeaker at index {i}", flush=True)
    
    p.terminate()
    
    if respeaker_index is None:
        return 0 
    
    print(f"Using device {respeaker_index}", flush=True)
    return respeaker_index

def process_audio(is_speaking, conn=None):
    try:
        model = vosk.Model("/home/evan/Clarity_V2/vosk-model-small-en-us-0.15")
        print("Model loaded", flush=True)
    except Exception as e:
        print(f"Model error: {e}", flush=True)
        return
        
    recognizer = vosk.KaldiRecognizer(model, 16000)
    # Enable more alternatives for better accuracy
    recognizer.SetMaxAlternatives(4)

    device_index = find_respeaker_device()
    print(f"Device: {device_index}", flush=True)
    p = pyaudio.PyAudio()
    
    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=2048, 
        )
        stream.start_stream()
        print("Listening...", flush=True)
        
        while True:
            if is_speaking.value == False:
                data = stream.read(2048, exception_on_overflow=False)
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result['alternatives'][0].get('text', '').strip()
                    print(text)
                    if conn and text != "" and "clarity" in text:
                        conn.send(text)
            else:
                _ = stream.read(4000, exception_on_overflow=False)  # Discard input during silent period to stop clarity from hearing itself



                      
    except KeyboardInterrupt:
        print("Stopped", flush=True)
    except Exception as e:
        print(f"Error: {e}", flush=True)
        if conn:
            conn.send({'type': 'error', 'message': str(e)})
    finally:
        if 'stream' in locals():
            stream.stop_stream()
            stream.close()
        p.terminate()

def voice(is_speaking, conn):
    """Voice processing wrapper"""
    process_audio(is_speaking, conn)


if __name__ == "__main__":
    # Direct execution - just print results
    process_audio(is_speaking = mp.Value('b', False))
