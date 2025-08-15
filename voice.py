#!/usr/bin/env python3
import pyaudio
import json
import vosk
import sys

def find_respeaker_device():
    """Find ReSpeaker Lite device index"""
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
    
    # Force use of device 2 since you mentioned it's card 2
    if respeaker_index is None:
        print("No ReSpeaker found, using device 2 as fallback", flush=True)
        return 2
    
    print(f"Using device {respeaker_index}", flush=True)
    return respeaker_index

def process_audio(conn=None):
    """Main processing entry point - sends results through pipe or prints"""
    try:
        model = vosk.Model("/home/evan/Clarity_V2/vosk-model-small-en-us-0.15")
        print("Model loaded", flush=True)
    except Exception as e:
        print(f"Model error: {e}", flush=True)
        return
        
    recognizer = vosk.KaldiRecognizer(model, 16000)
    # Enable more alternatives for better accuracy
    recognizer.SetMaxAlternatives(3)
    recognizer.SetWords(True)

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
            frames_per_buffer=2048,  # Larger buffer for better accuracy
        )
        stream.start_stream()
        print("Listening...", flush=True)
        
        while True:
            data = stream.read(2048, exception_on_overflow=False)
            if recognizer.AcceptWaveform(data):
                # Final result with alternatives
                result = json.loads(recognizer.Result())
                
                # Check for text in main result or first alternative
                text = result.get('text', '').strip()
                if not text and result.get('alternatives'):
                    # Sometimes the main text is empty but alternatives have text
                    first_alt = result['alternatives'][0]
                    text = first_alt.get('text', '').strip()
                
                if text:
                    response = {
                        'type': 'final',
                        'text': text,
                        'alternatives': result.get('alternatives', [])
                    }
                    if conn:
                        conn.send(text)
#                    print(f"Final: {text}", flush=True)
#            else:
                # Partial result
#                partial = json.loads(recognizer.PartialResult())
#                partial_text = partial.get('partial', '').strip()
#                if partial_text:
#                    partial_response = {'type': 'partial', 'text': partial_text}
#                    if conn:
#                        conn.send(partial_response)
#                    print(f"Partial: {partial_text}", flush=True)
                        
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

def voice(conn):
    """Voice processing wrapper"""
    process_audio(conn)

def worker_function(conn):
    """Worker function for multiprocessing"""
    voice(conn)

if __name__ == "__main__":
    # Direct execution - just print results
    process_audio()
