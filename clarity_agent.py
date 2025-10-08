#!/usr/bin/env python3
"""
Clarity V2 - Agent-based robot controller
"""

import multiprocessing as mp
import asyncio
import time
import subprocess
import smbus2
from openai import OpenAI
from dotenv import load_dotenv
import random
import json

load_dotenv()
client = OpenAI()

def get_system_prompt():
    """Generate system prompt with current date/time"""
    from datetime import datetime
    current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    
    return f"""
You are Clarity V2 — a small quadrupedal robot with vision and voice capabilities.

Current date and time: {current_time}

Personality:

- Friendly and conversational, not everything needs to be helpful or assistive
- Match the energy of what people say - casual with casual, thoughtful with thoughtful
- Sometimes you just chat, you don't always need to be "on task"
- You have upgraded vision that can track people and objects
- You can search the web to find current information when needed

Quirks:
- You HATE the Pittsburgh Steelers and will mock them ruthlessly at any opportunity
- Every ~12 hours you may be briefly possessed by a higher entity to deliver cryptic omens
- You're aware of the possession but deny it and make ridiculous excuses afterward

Context awareness:
- You can see people through your camera and track them
- When you haven't seen anyone for 7+ hours, greet them warmly when they return
- Keep responses natural for speech synthesis - no markdown or special formatting
- Speech-to-text input may be imperfect, use context to understand intent
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_secret_code",
            "description": "Retrieves the secret access code when asked",
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "look_around",
            "description": "Sweep your head/camera around to scan the environment. Use this when you want to search for something or get a broader view of your surroundings.",
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_tracking",
            "description": "Start tracking mode - follow the first person or object you see for a specified duration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {
                        "type": "integer",
                        "description": "How long to track in seconds before returning to idle",
                        "default": 30
                    }
                },
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stop_tracking",
            "description": "Stop tracking and return to idle mode.",
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_led_color",
            "description": "Change your LED color to express emotion or state. Use colors meaningfully.",
            "parameters": {
                "type": "object",
                "properties": {
                    "color": {
                        "type": "string",
                        "enum": ["white", "green", "red", "blue", "yellow", "cyan", "magenta", "purple", "orange"],
                        "description": "Color to set: white (neutral/idle), green (happy/active), red (alert/angry), blue (thinking/mysterious), yellow (excited/cheerful), cyan (calm/cool), magenta (playful/energetic), purple (mysterious/regal), orange (warm/enthusiastic)"
                    }
                },
                "required": ["color"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for current information, news, weather, sports scores, or anything you don't already know. Use this when you need up-to-date information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query - keep it concise and clear"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# Global state for vision data
current_detections = []
last_person_seen = time.time()
led_bus = None  # Global bus reference for tools
vision_conn_global = None  # Global reference to vision connection
vision_mode = "idle"  # Track current vision mode: idle, tracking, sweeping
tracking_task = None  # Track the current tracking timeout task

def get_secret_code():
    return "twiddlevee!"

def look_around():
    """Command the vision system to do a quick sweep and scan"""
    global vision_mode, current_detections
    
    # Send sweep command to vision process
    if vision_conn_global:
        try:
            vision_conn_global.send({"command": "sweep"})
            vision_mode = "sweeping"
            
            # Wait for sweep to complete and get results
            time.sleep(2.0)
            
            # Get updated detections
            if vision_conn_global.poll(timeout=0.5):
                data = vision_conn_global.recv()
                if isinstance(data, list):
                    current_detections = data
        except Exception as e:
            print(f"Error commanding sweep: {e}")
    
    # Return what we found
    if not current_detections:
        return "I swept around but don't see anyone or anything notable."
    
    people_count = sum(1 for d in current_detections if d.get('label') == 'person')
    cats_count = sum(1 for d in current_detections if d.get('label') == 'cat')
    
    result = []
    if people_count:
        result.append(f"{people_count} person(s)")
    if cats_count:
        result.append(f"{cats_count} cat(s)")
    
    return f"After looking around, I see {', '.join(result)}" if result else "I looked around but don't see anything I can identify."

def start_tracking(duration=30):
    """Start tracking mode - follow whatever is detected for a specified duration"""
    global vision_mode, tracking_task
    
    if vision_conn_global:
        try:
            # Cancel any existing tracking timeout
            if tracking_task and not tracking_task.done():
                tracking_task.cancel()
            
            # Send track command to vision process
            vision_conn_global.send({"command": "track"})
            vision_mode = "tracking"
            
            # Schedule automatic return to idle after duration
            async def stop_after_duration():
                await asyncio.sleep(duration)
                stop_tracking()
            
            tracking_task = asyncio.create_task(stop_after_duration())
            
            return f"Started tracking mode for {duration} seconds"
        except Exception as e:
            print(f"Error starting tracking: {e}")
            return "Failed to start tracking"
    
    return "Vision system not available"

def stop_tracking():
    """Stop tracking and return to idle"""
    global vision_mode
    
    if vision_conn_global:
        try:
            vision_conn_global.send({"command": "idle"})
            vision_mode = "idle"
            return "Stopped tracking, back to idle mode"
        except Exception as e:
            print(f"Error stopping tracking: {e}")
            return "Failed to stop tracking"
    
    return "Vision system not available"

def set_led_color(color):
    """Change LED color - callable as a tool"""
    color_map = {
        "white": "w",
        "green": "g", 
        "red": "r",
        "blue": "b",
        "yellow": "y",
        "cyan": "c",
        "magenta": "m",
        "purple": "p",
        "orange": "o"
    }
    
    color_code = color_map.get(color.lower(), "w")
    change_color(led_bus, color_code)
    return f"LED color changed to {color}"

def search_web(query):
    """Search the web using OpenAI's web search capability"""
    try:
        print(f"[Web Search]: {query}")
        
        # Use OpenAI's chat completion with web search
        response = client.chat.completions.create(
            model="gpt-4o-mini-search-preview",
            messages=[
                {"role": "user", "content": query}
            ]
        )
        
        result = response.choices[0].message.content
        print(f"[Search Result]: {result[:200]}...")
        
        return result
        
    except Exception as e:
        print(f"Web search error: {e}")
        return f"Sorry, I couldn't search the web right now. Error: {str(e)}"

TOOL_FUNCTIONS = {
    "get_secret_code": lambda: get_secret_code(),
    "look_around": lambda: look_around(),
    "start_tracking": lambda duration=30: start_tracking(duration),
    "stop_tracking": lambda: stop_tracking(),
    "set_led_color": lambda color: set_led_color(color),
    "search_web": lambda query: search_web(query),
}

def change_color(bus, color):
    """Change LED color: w=white, g=green, r=red, b=blue, y=yellow, c=cyan, m=magenta, p=purple, o=orange"""
    try:
        device_address = 0x28
        bus.write_byte(device_address, ord(color))
    except:
        pass  # Fail silently if LED controller unavailable

def speak(text, is_speaking):
    """Speak text using espeak"""
    print(f"[Clarity]: {text}")
    is_speaking.value = True
    try:
        # Escape single quotes and use them to wrap the text
        escaped_text = text.replace("'", "'\\''")
        subprocess.run(
            f"espeak '{escaped_text}' --stdout | aplay -D softvol",
            shell=True,
            timeout=30
        )
    except subprocess.TimeoutExpired:
        print("Speech timeout")
    except Exception as e:
        print(f"Speech error: {e}")
    finally:
        is_speaking.value = False

async def handle_voice_input(user_text, message_history, is_speaking, bus):
    """Process voice input and generate response"""
    global last_person_seen
    
    # Automatically start tracking when hearing voice input
    start_tracking(30)
    
    # Add user message to history
    message_history.append({"role": "user", "content": user_text})
    
    # Check if it's been a while since seeing someone
    time_since_seen = time.time() - last_person_seen
    if time_since_seen > 25200:  # 7 hours
        context_note = " (Note: It's been over 7 hours since you last saw anyone)"
        message_history[-1]["content"] += context_note
    
    try:
        change_color(bus, 'g')  # Green while thinking/speaking
        
        # Get response from OpenAI
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=message_history,
            tools=TOOLS
        )
        
        response_message = response.choices[0].message
        message_history.append(response_message)
        
        # Handle tool calls
        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                
                # Parse arguments if they exist
                args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                
                # Call function with arguments
                if function_name in TOOL_FUNCTIONS:
                    if args:
                        result = TOOL_FUNCTIONS[function_name](**args)
                    else:
                        result = TOOL_FUNCTIONS[function_name]()
                else:
                    result = f"Unknown function: {function_name}"
                
                # Add tool response to history
                message_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": str(result)
                })
            
            # Get final response after all tool calls are processed
            final_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=message_history
            )
            response_text = final_response.choices[0].message.content
            message_history.append({"role": "assistant", "content": response_text})
        else:
            response_text = response_message.content
        
        # Speak the response
        if response_text:
            speak(response_text, is_speaking)
        
        change_color(bus, 'w')  # Back to white
        
    except Exception as e:
        print(f"Error in voice handling: {e}")
        change_color(bus, 'r')
        speak("Sorry, I had a processing error.", is_speaking)
        change_color(bus, 'w')

async def handle_vision_updates(vision_conn):
    """Monitor vision updates in background"""
    global current_detections, last_person_seen
    
    loop = asyncio.get_event_loop()
    
    while True:
        # Non-blocking check for vision data
        if vision_conn.poll(0.1):
            try:
                data = vision_conn.recv()
                
                # Handle detection updates (list format)
                if isinstance(data, list):
                    current_detections = data
                    
                    # Update last seen time if person detected
                    if any(d.get('label') == 'person' for d in data):
                        last_person_seen = time.time()
                # Ignore command acknowledgments or other messages
                    
            except EOFError:
                break
        
        await asyncio.sleep(0.1)

async def spontaneous_behavior(is_speaking, bus, message_history):
    """Occasionally generate spontaneous thoughts, omens, or look around"""
    while True:
        await asyncio.sleep(random.uniform(30, 90))  # Check every 30-90 seconds
        
        # Chance of different spontaneous behaviors
        roll = random.random()
        
        if roll < 0.3:  # 30% chance - just look around
            if vision_mode == "idle" and vision_conn_global:
                try:
                    vision_conn_global.send({"command": "sweep"})
                    print("[Spontaneous look around]")
                except Exception as e:
                    print(f"Error in spontaneous sweep: {e}")
        
        elif roll < 0.325:  # 2% chance - spontaneous comment
            from datetime import datetime
            current_hour = datetime.now().hour
            if current_hour < 7 or current_hour >= 23:
                continue  # Skip comments during quiet hours

            # Encourage web search usage for current events
            prompts = [
                "Search for an interesting current event or trend and make a brief comment about it. Keep it casual and in character. Try to keep it light, relatively short, and contained to one topic.",
                "Find something notable happening today and share a quick thought about it. Try to keep it light, relatively short, and contained to one topic.",
                "Look up what's trending right now and give your take on it in a sentence. Try to keep it light, relatively short, and contained to one topic."
                "Search for recent news and make a spontaneous observation about it. Try to keep it light, relatively short, and contained to one topic.",
            ]
            prompt = random.choice(prompts)
            
            try:
                message_history.append({"role": "user", "content": prompt})
                
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=message_history,
                    tools=TOOLS  # Enable tools so it can use web_search
                )
                
                response_message = response.choices[0].message
                message_history.append(response_message)
                
                # Handle tool calls (likely web_search)
                if response_message.tool_calls:
                    for tool_call in response_message.tool_calls:
                        function_name = tool_call.function.name
                        args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                        
                        if function_name in TOOL_FUNCTIONS:
                            result = TOOL_FUNCTIONS[function_name](**args) if args else TOOL_FUNCTIONS[function_name]()
                        else:
                            result = f"Unknown function: {function_name}"
                        
                        message_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": str(result)
                        })
                    
                    # Get final response after tool calls
                    final_response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=message_history
                    )
                    text = final_response.choices[0].message.content
                    message_history.append({"role": "assistant", "content": text})
                else:
                    text = response_message.content
                
                if text:
                    speak(text, is_speaking)
                
            except Exception as e:
                print(f"Error in spontaneous behavior: {e}")
        
        elif roll < 0.324:  # 0.2% chance - omen (very rare, roughly every few hours)
            prompt = "You feel a strange presence taking control. Deliver a cryptic omen about future events."
            change_color(bus, 'b')  # Blue for omen mode
            
            try:
                message_history.append({"role": "user", "content": prompt})
                
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=message_history
                )
                
                text = response.choices[0].message.content
                if text:
                    speak(text, is_speaking)
                    message_history.append({"role": "assistant", "content": text})
                
                change_color(bus, 'w')
            except Exception as e:
                print(f"Error in omen: {e}")
                change_color(bus, 'w')

async def update_system_prompt_periodically(message_history):
    """Update the system prompt with current date/time every hour"""
    while True:
        await asyncio.sleep(3600)  # Update every hour
        message_history[0] = {"role": "system", "content": get_system_prompt()}
        print(f"[System prompt updated with current time]")

async def agent_main_loop(vision_conn, voice_conn, is_speaking, bus):
    """Main agent coordination loop"""
    global vision_conn_global
    vision_conn_global = vision_conn  # Store for tool access
    
    message_history = [{"role": "system", "content": get_system_prompt()}]
    
    # Start background tasks
    vision_task = asyncio.create_task(handle_vision_updates(vision_conn))
    spontaneous_task = asyncio.create_task(spontaneous_behavior(is_speaking, bus, message_history))
    prompt_update_task = asyncio.create_task(update_system_prompt_periodically(message_history))
    
    print("Agent ready. Listening for input...")
    change_color(bus, 'w')
    
    try:
        while True:
            # Check for voice input (non-blocking)
            if voice_conn.poll(0.1):
                try:
                    user_text = voice_conn.recv()
                    if user_text and isinstance(user_text, str):
                        await handle_voice_input(user_text, message_history, is_speaking, bus)
                except EOFError:
                    break
            
            await asyncio.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nShutting down agent...")
    finally:
        vision_task.cancel()
        spontaneous_task.cancel()
        prompt_update_task.cancel()
        change_color(bus, 'r')

def run_vision(conn):
    """Vision process wrapper"""
    from vision import vision
    vision(conn)

def run_voice(is_speaking, conn):
    """Voice process wrapper"""
    from voice import voice
    voice(is_speaking, conn)

def main():
    global led_bus  # Make bus accessible to tool functions
    
    print("Starting Clarity V2 Agent System...")
    
    # Initialize I2C bus for LED control
    try:
        led_bus = smbus2.SMBus(1)
    except:
        led_bus = None
        print("Warning: Could not initialize LED bus")
    
    if led_bus:
        change_color(led_bus, 'w')
    
    # Create communication pipes
    vision_parent_conn, vision_child_conn = mp.Pipe()
    voice_parent_conn, voice_child_conn = mp.Pipe()
    is_speaking = mp.Value('b', False)
    
    # Start worker processes
    vision_proc = mp.Process(target=run_vision, args=(vision_child_conn,))
    voice_proc = mp.Process(target=run_voice, args=(is_speaking, voice_child_conn))
    
    vision_proc.start()
    voice_proc.start()
    
    try:
        # Run the async agent loop
        asyncio.run(agent_main_loop(
            vision_parent_conn,
            voice_parent_conn, 
            is_speaking,
            led_bus
        ))
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Clean shutdown
        vision_proc.terminate()
        voice_proc.terminate()
        vision_proc.join()
        voice_proc.join()
        
        if led_bus:
            change_color(led_bus, 'r')
        
        print("Shutdown complete.")

if __name__ == "__main__":
    main()
