import os
import ast
import json
import pika
import eventlet
import socketio
from flask import Flask
from rabbitmq import consume_generate_question_messages, publish_generate_answer_messages
from rag import ask_agent, init_pinecone
from dotenv import load_dotenv

app = Flask(__name__)
sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio, app)
load_dotenv()
eventlet.monkey_patch()

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
os.environ["GOOGLE_CSE_ID"] = os.getenv("GOOGLE_CSE_ID")
os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
os.environ["PINECONE_API_KEY"] = os.getenv("PINECONE_API_KEY")
os.environ["PINECONE_ENVIRONMENT"] = os.getenv("PINECONE_ENVIRONMENT")
os.environ["INDEX_NAME"] = os.getenv("INDEX_NAME")
os.environ["RABBITMQ_HOSTNAME"] = os.getenv("RABBITMQ_HOSTNAME")
os.environ["RABBITMQ_USERNAME"] = os.getenv("RABBITMQ_USERNAME")
os.environ["RABBITMQ_PASSWORD"] = os.getenv("RABBITMQ_PASSWORD")
os.environ["RABBITMQ_VIRTUAL_HOST"] = os.getenv("RABBITMQ_VIRTUAL_HOST")

init_pinecone()

credentials = pika.PlainCredentials(os.environ["RABBITMQ_USERNAME"], os.environ["RABBITMQ_PASSWORD"])

def consume_messages():
    connection = pika.BlockingConnection(pika.ConnectionParameters(os.environ["RABBITMQ_HOSTNAME"], 5672, os.environ["RABBITMQ_VIRTUAL_HOST"], credentials))
        
    channel = connection.channel()

    def ask_agent_callback(ch, method, properties, body):
        sio.emit("add_entry")
        eventlet.sleep(0)

        json_string = body.decode('utf-8')
        data = json.loads(json_string)

        agent_output = ask_agent(question=data["Question"], sio=sio, messages=data["ChatHistory"])
        print(agent_output["chat_history"])

        message = {
            "UserId": data["UserId"],
            "ConversationId": data["ConversationId"],
            "Question": agent_output["response"]["input"],
            "Answer": agent_output["response"]["output"],
            "ChatHistory": agent_output["chat_history"]
        }
        publish_generate_answer_messages(channel=channel, message=json.dumps(message))

    consume_generate_question_messages(channel=channel, callback=ask_agent_callback)
    
    channel.start_consuming()

def run_consumer():
    eventlet.spawn(consume_messages)

if __name__ == "__main__":
    run_consumer() 
    eventlet.wsgi.server(eventlet.listen(('127.0.0.1', 3000)), app)   
    
