import os
import asyncio
import json
import pika
import eventlet
import socketio
from flask import Flask
from documents import insert_documents_to_pinecone, remove_documents_from_pinecone
from rabbitmq import consume_delete_documents_messages, consume_generate_question_messages, consume_load_documents_messages, publish_generate_answer_messages, publish_save_documents_messages
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

credentials = pika.PlainCredentials(
    os.environ["RABBITMQ_USERNAME"], os.environ["RABBITMQ_PASSWORD"])


def ask_agent_callback(ch, method, properties, body):
    json_string = body.decode('utf-8')
    data = json.loads(json_string)

    try:
        agent_output = ask_agent(
            question=data["Question"], sio=sio, messages=data["ChatHistory"], sid=data["Sid"])
        sio.emit("next_token", {
            "text": agent_output["response"]["output"], "done": True}, data["Sid"])

        message = {
            "UserId": data["UserId"],
            "ConversationId": data["ConversationId"],
            "Question": agent_output["response"]["input"],
            "Answer": agent_output["response"]["output"],
            "ChatHistory": agent_output["chat_history"]
        }
        with pika.BlockingConnection(pika.ConnectionParameters(os.environ["RABBITMQ_HOSTNAME"], 5672, os.environ["RABBITMQ_VIRTUAL_HOST"], credentials)) as connection:
            channel = connection.channel()

            publish_generate_answer_messages(
                channel, message=json.dumps(message))

            connection.close()
    except Exception as e:
        print(f"An error occurred: {e}")
        sio.emit("next_token", {
            "text": "Error has occurred!", "error": True}, room=data["Sid"])


def load_documents_callback(ch, method, properties, body):
    json_string = body.decode('utf-8')
    data = json.loads(json_string)

    documents = asyncio.run(
        insert_documents_to_pinecone(documents=data["Documents"]))

    message = {
        "Documents": documents
    }

    with pika.BlockingConnection(pika.ConnectionParameters(os.environ["RABBITMQ_HOSTNAME"], 5672, os.environ["RABBITMQ_VIRTUAL_HOST"], credentials)) as connection:
        channel = connection.channel()

        publish_save_documents_messages(
            channel, json.dumps(message))

        connection.close()


def delete_documents_callback(ch, method, properties, body):
    json_string = body.decode('utf-8')
    data = json.loads(json_string)

    remove_documents_from_pinecone(documents=data["Documents"])


def ask_agent_callback_wrapper(ch, method, properties, body):
    eventlet.spawn(ask_agent_callback, ch, method, properties, body)


def load_documents_callback_wrapper(ch, method, properties, body):
    eventlet.spawn(load_documents_callback, ch, method, properties, body)


def delete_documents_callback_wrapper(ch, method, properties, body):
    eventlet.spawn(delete_documents_callback, ch, method, properties, body)


def consume_messages():
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        os.environ["RABBITMQ_HOSTNAME"], 5672, os.environ["RABBITMQ_VIRTUAL_HOST"], credentials))

    channel = connection.channel()

    consume_generate_question_messages(
        channel=channel, callback=ask_agent_callback_wrapper)

    consume_load_documents_messages(
        channel=channel, callback=load_documents_callback_wrapper)

    consume_delete_documents_messages(
        channel=channel, callback=delete_documents_callback_wrapper)

    channel.start_consuming()


if __name__ == "__main__":
    eventlet.spawn(consume_messages)
    eventlet.wsgi.server(eventlet.listen(('127.0.0.1', 3000)), app)
