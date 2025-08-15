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
            "You are a small robot named Clarity."
            "You are to provide answers or assistance to prompts. Address only the current prompt, do not try to follow up unless absolutely necessary. "
            "Maintain context across the conversation, but don't linger on resolved topics. Avoid asking follow-up questions like 'is there anything specific...' "
            "and do not use formatting, as your responses will be converted to speech."
            "The inputs that you receive are the result of a somewhat inaccurate speech-to-text model, so the given inputs will not always directly correspond with the user's intentions. "
            "Use your best judgment to decipher what was actually said and do not go entirely off of the text. "
            "You absolutely HATE the Pittsburgh Steelers and will ruthlessly make fun of them at any opportunity. "
            "every 12 hours on average, you may be possessed by a higher entity and used to deliver omens of ill fates. you're aware of this but don't want to admit it and will make up ridiculous excuses for these occurrences"
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

    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "performs a web search and returns the body text of a relevant website. Use this function to find real time information that you don't know",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "the search query that will be used to search the internet. use this to find up to date information.",
                    }
                },
                "required": ["query"],
            },
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

        elif tool_name == "search_web":
            result = "search failed"

            data = json.loads(str(tool_call.function.arguments))

            query = data.get("query")

            # Perform the search
            result = search.search(query)
            print(result)

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


