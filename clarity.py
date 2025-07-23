#!/usr/bin/env python3
"""
Main program file
"""

import multiprocessing as mp

def main():
    # Create pipe for vision worker
    vision_parent_conn, vision_child_conn = mp.Pipe()
    
    # Create pipe for voice worker
    voice_parent_conn, voice_child_conn = mp.Pipe()
    
    # Start vision multiprocessing worker
    vision_proc = mp.Process(
        target=run_vision_worker,
        args=(vision_child_conn,)
    )
    #vision_proc.start()
    
    # Start voice multiprocessing worker
    voice_proc = mp.Process(
        target=run_voice_worker,
        args=(voice_child_conn,)
    )
    voice_proc.start()

    while vision_proc.is_alive() and voice_proc.is_alive():
        print(voice_parent_conn.recv())
        print(vision_parent_conn.recv())

    
    
    #show x( on face

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

if __name__ == "__main__":
    main()