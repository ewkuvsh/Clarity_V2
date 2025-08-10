#!/usr/bin/env python3
"""
Timer-based VAD - records when you start speaking, adds 1s chunks while speaking continues
Configured for ReSpeaker Lite USB device
"""
import pyaudio
import numpy as np
import time
import queue
import threading
from collections import deque
import subprocess
class SimpleVAD:
    """Simple Voice Activity Detection"""
    def __init__(self, threshold=0.005, window_size=10):
        self.threshold = threshold
        self.window_size = window_size
        self.energy_buffer = deque(maxlen=window_size)
        self.background_energy = 0.001
        
    def is_speech(self, audio_data):
        """Determine if audio contains speech"""
        energy = np.sqrt(np.mean(audio_data**2))
        
        # Update background energy estimate
        self.energy_buffer.append(energy)
        if len(self.energy_buffer) >= self.window_size:
            sorted_energies = sorted(self.energy_buffer)
            self.background_energy = sorted_energies[int(len(sorted_energies) * 0.3)]
        
        # Adaptive threshold
        dynamic_threshold = max(self.threshold, self.background_energy * 2.5)
        print("Energy detected is ", energy, " the background energy threshold is ", dynamic_threshold)
        return energy > dynamic_threshold

class TimerBasedVADProcessor:
    def __init__(self):
        self.model_size = "tiny"
        self.model = None
        self.sample_rate = 16000
        
        # VAD settings
        self.non_speech_threshold = 0.005
        self.speech_timeout = 1.0  # Stop recording after 2s of no speech
        self.max_recording_duration = 20.0  # Max 20s total recording
        
        # Timer-based recording
        self.vad = SimpleVAD(self.non_speech_threshold)
        self.recording = False
        self.audio_chunks = []  # Store 1-second chunks
        self.last_speech_time = None
        self.recording_start_time = None
        
        # Audio processing
        self.audio_queue = queue.Queue(maxsize=5)
        self.running = False
        
        # 1-second chunk size
        self.chunk_duration = 1.0  # 1 second
        self.frames_per_chunk = int(self.sample_rate * self.chunk_duration)
        self.current_chunk_buffer = []
        
    def find_respeaker_device(self):
        """Find ReSpeaker Lite device index"""
        p = pyaudio.PyAudio()
        respeaker_index = None
        
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            # Look for ReSpeaker Lite in the device name
            if info['maxInputChannels'] > 0:
                name = info['name'].lower()
                if 'respeaker' in name or ('usb audio' in name and 'lite' in str(info)):
                    respeaker_index = i
                    break
        
        # If not found by name, try to match by known characteristics
        if respeaker_index is None:
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if (info['maxInputChannels'] > 0 and 
                    'USB Audio' in info['name'] and
                    info['hostApi'] == 0):  # ALSA
                    respeaker_index = i
                    break
        
        p.terminate()
        
        if respeaker_index is None:
            # Try to use index 2 as fallback (based on your card 2 info)
            return 2
            
        return respeaker_index
        
    def load_model(self):
        """Load faster-whisper model"""
        try:
            from faster_whisper import WhisperModel
            
            self.model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
                num_workers=1,
            )
            
            return True
            
        except Exception as e:
            return False
    
    def process_one_second_chunk(self, chunk_data):
        """Process a complete 1-second chunk"""
        current_time = time.time()
        has_speech = self.vad.is_speech(chunk_data)
        
        if has_speech:
            self.last_speech_time = current_time
            
            if not self.recording:
                # Start recording
                self.recording = True
                self.recording_start_time = current_time
                self.audio_chunks = []
            
            # Add this chunk to recording
            print("added talking chunk")
            self.audio_chunks.append(chunk_data)
            
            return "recording"
        
        elif self.recording:
            # We're recording but this chunk has no speech
            time_since_speech = current_time - self.last_speech_time if self.last_speech_time else 0
            recording_duration = current_time - self.recording_start_time if self.recording_start_time else 0
            
            # Check if we should stop recording
            if (time_since_speech > self.speech_timeout or 
                recording_duration > self.max_recording_duration):
                
                # Stop recording and process
                self.recording = False
                if len(self.audio_chunks) > 0:
                    self._queue_for_transcription()
                print("stopped")
                return "stopped"
            else:
                # Still in timeout period, add silent chunk
                print("adding silent chunk")
                self.audio_chunks.append(chunk_data)
                return "recording_silent"
        
        return "listening"
    
    def _queue_for_transcription(self):
        """Queue accumulated audio chunks for transcription"""
        if not self.audio_chunks:
            return
            
        # Concatenate all chunks
        full_audio = np.concatenate(self.audio_chunks)
        
        try:
            self.audio_queue.put_nowait(full_audio)
        except queue.Full:
            # Drop oldest and try again
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.put_nowait(full_audio)
            except queue.Empty:
                pass
        
        # Clear for next recording
        self.audio_chunks = []
    
    def transcribe_audio_segment(self, audio_data):
        """Transcribe complete audio segment"""
        try:
            duration = len(audio_data) / self.sample_rate
            if duration < 0.5:
                return None
            print("processing")
            segments, info = self.model.transcribe(
                audio_data,
                language="en",
                vad_filter=False,  # We handle VAD ourselves
                beam_size=2,
                best_of=2,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            
            # Extract text
            text_segments = []
            for segment in segments:
                if segment.text.strip():
                    text_segments.append(segment.text.strip())
            
            if text_segments:
                full_text = " ".join(text_segments).strip()
                
                # Clean up
                if full_text.endswith('.'):
                    full_text = full_text[:-1]
                if full_text:
                    full_text = full_text[0].upper() + full_text[1:]
                subprocess.run(f'espeak "{full_text}" --stdout | aplay -D softvol', shell=True)
                print(full_text)
                return full_text
                
        except Exception as e:
            print("transcriptoin exception ",e)
            pass
        
        return None
    
    def audio_capture_thread(self):
        """Audio capture with 1-second chunk processing"""
        # Find ReSpeaker Lite device
        device_index = self.find_respeaker_device()
        frames_per_buffer = 1600  # 0.1 seconds
        
        p = pyaudio.PyAudio()
        
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=frames_per_buffer,
            )
            
            stream.start_stream()
            
            while self.running:
                try:
                    # Read audio frame
                    data = stream.read(frames_per_buffer, exception_on_overflow=False)
                    audio_frame = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    
                    # Add to current chunk buffer
                    self.current_chunk_buffer.extend(audio_frame)
                    
                    # Check if we have a complete 1-second chunk
                    if len(self.current_chunk_buffer) >= self.frames_per_chunk:
                        # Extract exactly 1 second
                        chunk_data = np.array(self.current_chunk_buffer[:self.frames_per_chunk])
                        
                        # Remove processed samples (keep remainder for next chunk)
                        self.current_chunk_buffer = self.current_chunk_buffer[self.frames_per_chunk:]
                        
                        # Process the 1-second chunk
                        self.process_one_second_chunk(chunk_data)
                
                except Exception as e:
                    print("audio capture thread while loop exception")
                    time.sleep(0.1)
                    
        except Exception as e:
            print("audio capture thread exception")
            pass
            
        finally:
            if 'stream' in locals():
                stream.stop_stream()
                stream.close()
            p.terminate()
    
    def transcription_thread(self, conn):
        """Handle transcription of queued audio"""
        while self.running:
            try:
                # Get audio data from queue
                audio_data = self.audio_queue.get(timeout=2.0)
                
                # Transcribe
                result = self.transcribe_audio_segment(audio_data)
                
                if result and conn:
                    conn.send(result)
                    
            except queue.Empty:
                continue
            except Exception as e:
                pass
    
    def process_audio(self, conn):
        """Main processing entry point"""
        if not self.load_model():
            return
        
        self.running = True
        
        # Start threads
        audio_thread = threading.Thread(target=self.audio_capture_thread, daemon=True)
        transcription_thread = threading.Thread(target=self.transcription_thread, args=(conn,), daemon=True)
        
        audio_thread.start()
        transcription_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False

def voice(conn):
    processor = TimerBasedVADProcessor()
    processor.process_audio(conn)

def worker_function(conn):
    voice(conn)

if __name__ == "__main__":
    processor = TimerBasedVADProcessor()
    processor.process_audio(None)
