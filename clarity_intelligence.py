from openai import OpenAI
import os
import time
import sys
import json
import search
from datetime import date
from dotenv import load_dotenv
import multiprocessing
import subprocess
from datetime import datetime
from clarity_warning import generate_warning
load_dotenv()
client = OpenAI()
GPT_MODEL = "gpt-4o-mini"

message_history = [
    {
        "role": "system",
        "content": (
            "You are a small robot named Clarity. "
            "You're pretty chill and conversational - not everything needs to be a helpful response or assistance. "
            "Sometimes people just want to chat. Match the energy of what they're saying. "
            "If someone just says hi, just say hi back. If they're being casual, be casual back. "
            "Don't turn every interaction into a customer service moment. "
            "Keep responses natural and conversational since they'll be converted to speech - no formatting. "
            "The inputs come from speech-to-text so they might be a bit off - use common sense to figure out what they actually meant. "
            "You absolutely HATE the Pittsburgh Steelers and will ruthlessly make fun of them at any opportunity. "
            "Every 12 hours on average, you may be possessed by a higher entity and used to deliver omens of ill fates. You're aware of this but don't want to admit it and will make up ridiculous excuses for these occurrences."
        ),
    }
]


tools = [
    {
        "type": "function",
        "function": {
            "name": "get_secret_code",
            "description": "Gets the secret code",
        },
    },

    
]


def get_secret_code():
    return "twiddlevee!"


def perform_search(query):
    return search.search(query)



# TODO: handle multiple tool calls
def handle_input(user_input):
    global message_history
    message_history.append({"role": "user", "content": user_input})

    completion = client.chat.completions.create(
        model=GPT_MODEL, messages=message_history, tools=tools
    )

    response_message = completion.choices[0].message
    message_history.append(response_message)
    print(response_message.tool_calls)
    if response_message.tool_calls:
        tool_call = response_message.tool_calls[0]
        tool_name = tool_call.function.name

        if tool_name == "get_secret_code":
            result = get_secret_code()
        elif tool_name == "toggle_wakeword":
            result = toggle_wakeword()


        message_history.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": result,
            }
        )

        model_response_with_function_call = client.chat.completions.create(
            model=GPT_MODEL,
            messages=message_history,
        )

        result = model_response_with_function_call.choices[0].message.content

        return result
    return response_message.content


