#!/usr/bin/env python3
"""
Timer-based VAD - records when you start speaking, adds 1s chunks while speaking continues
"""
import pyaudio
import numpy as np
import time
import queue
import threading
from collections import deque

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
        return energy > dynamic_threshold

class TimerBasedVADProcessor:
    def __init__(self, model_size="base"):
        self.model_size = model_size
        self.model = None
        self.sample_rate = 16000
        
        # VAD settings
        self.non_speech_threshold = 0.005
        self.speech_timeout = 2.0  # Stop recording after 2s of no speech
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
        
    def load_model(self):
        """Load faster-whisper model"""
        try:
            from faster_whisper import WhisperModel
            
            print(f"Loading faster-whisper {self.model_size}...")
            start_time = time.time()
            
            self.model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
                num_workers=1,
            )
            
            print(f"✓ Model loaded in {time.time() - start_time:.1f}s")
            return True
            
        except Exception as e:
            print(f"✗ Error loading model: {e}")
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
                print("🔴 Started recording...")
            
            # Add this chunk to recording
            self.audio_chunks.append(chunk_data)
            print(f"📝 Added 1s chunk (total: {len(self.audio_chunks)}s)")
            
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
                    print(f"🛑 Stopped recording ({len(self.audio_chunks)}s total)")
                    self._queue_for_transcription()
                else:
                    print("🛑 Stopped recording (no audio collected)")
                
                return "stopped"
            else:
                # Still in timeout period, add silent chunk
                self.audio_chunks.append(chunk_data)
                print(f"🔇 Added silent chunk (timeout in {self.speech_timeout - time_since_speech:.1f}s)")
                return "recording_silent"
        
        return "listening"
    
    def _queue_for_transcription(self):
        """Queue accumulated audio chunks for transcription"""
        if not self.audio_chunks:
            return
            
        # Concatenate all chunks
        full_audio = np.concatenate(self.audio_chunks)
        duration = len(full_audio) / self.sample_rate
        
        print(f"📤 Queuing {duration:.1f}s for transcription")
        
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
                
            print(f"🔄 Transcribing {duration:.1f}s...")
            process_start = time.time()
            
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
                
                process_time = (time.time() - process_start) * 1000
                return full_text, process_time, duration
                
        except Exception as e:
            print(f"Transcription error: {e}")
        
        return None
    
    def audio_capture_thread(self):
        """Audio capture with 1-second chunk processing"""
        device_index = 0  # ReSpeaker Lite
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
            print("🎤 Timer-based VAD capture started")
            print(f"⏱️  Checks every 1 second, stops after {self.speech_timeout}s silence")
            
            last_status_time = time.time()
            
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
                        status = self.process_one_second_chunk(chunk_data)
                        
                        # Status updates every 5 seconds
                        current_time = time.time()
                        if current_time - last_status_time > 5.0:
                            if status == "listening":
                                energy = np.sqrt(np.mean(chunk_data**2))
                                threshold = max(self.non_speech_threshold, self.vad.background_energy * 2.5)
                                print(f"👂 Listening... (energy: {energy:.4f}, threshold: {threshold:.4f})")
                            
                            last_status_time = current_time
                
                except Exception as e:
                    print(f"Audio capture error: {e}")
                    time.sleep(0.1)
                    
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
                
                if result:
                    text, process_time, duration = result
                    print(f"🎯 RESULT: '{text}'")
                    print(f"   └─ {duration:.1f}s audio, {process_time:.0f}ms processing")
                    
                    if conn:
                        conn.send(text)
                else:
                    print("❌ No transcription result")
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Transcription thread error: {e}")
    
    def process_audio(self, conn):
        """Main processing entry point"""
        if not self.load_model():
            return
            
        print("🧠 Timer-based VAD processor")
        print(f"⚙️  Settings:")
        print(f"   • 1-second chunks")
        print(f"   • Stop after {self.speech_timeout}s silence")
        print(f"   • Max recording: {self.max_recording_duration}s")
        print(f"   • VAD threshold: {self.non_speech_threshold}")
        print("💡 Speak naturally - records complete thoughts")
        print("-" * 60)
        
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
            print("\n🛑 Stopping...")
        finally:
            self.running = False

def voice(conn):
    processor = TimerBasedVADProcessor("base")
    processor.process_audio(conn)

def worker_function(conn):
    voice(conn)

if __name__ == "__main__":
    import sys
    
    model_size = "base"
    if len(sys.argv) > 1:
        model_size = sys.argv[1]
    
    print("Timer-based VAD Processor")
    processor = TimerBasedVADProcessor(model_size)
    processor.process_audio(None)
