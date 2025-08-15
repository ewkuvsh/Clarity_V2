from openai import OpenAI
import os
import sys
import json
from datetime import date
from dotenv import load_dotenv


load_dotenv()



def generate_warning():
	client = OpenAI()
	args = sys.argv
	GPT_MODEL = "gpt-4o-mini"


	messages = [
	    {
	        "role": "system",
	        "content": "You are Clarity, an omniscient entity that exists outside of time. You have briefly possessed a quadripedal robot for the purpose of providing a warning. This warning should be extremely cryptic and hard to understand"
	        ,
	    },
	    {"role": "user", "content": "what is your message?"},
	]

	completion = client.chat.completions.create(
	    model=GPT_MODEL, 
	    messages=messages,
	    temperature=0.9,
	    top_p=0.9
	)

	response_message = completion.choices[0].message
	messages.append(response_message)

	return completion.choices[0].message.content

	





