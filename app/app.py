import os
import json
import sys
import asyncio
import pika
import eventlet
import socketio
from flask import Flask, request, jsonify
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain_experimental.llm_symbolic_math.base import LLMSymbolicMathChain
from langchain.vectorstores import Pinecone
from langchain.embeddings import OpenAIEmbeddings
from langchain.agents import AgentType, Tool, ConversationalAgent
from langchain.memory import ConversationBufferWindowMemory
from langchain.utilities import GoogleSearchAPIWrapper
from langchain.agents import initialize_agent
from flask_socketio import SocketIO
from classes import StreamAgentAnswerCallbackHandler
from dotenv import load_dotenv
import pinecone

app = Flask(__name__)
sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio, app)
load_dotenv()


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


# prompt = ChatPromptTemplate.from_template(
#   """Use the following pieces of context to answer the question at the end. If you don"t know the answer, just say that you don"t know, don"t try to make up an answer.
#   ----------------
#   CONTEXT: {context}
#   ----------------
#   CHAT HISTORY: {chat_history}
#   ----------------
#   QUESTION: {question}
#   ----------------
#   Helpful Answer:"""
# )

llm = ChatOpenAI(
    openai_api_key=os.environ["OPENAI_API_KEY"],
    model="gpt-3.5-turbo",
    streaming=True,
    temperature=0
)

pinecone.init(
    api_key=os.environ["PINECONE_API_KEY"],
    environment=os.environ["PINECONE_ENVIRONMENT"]
)

retriever=Pinecone.from_existing_index(index_name=os.environ["INDEX_NAME"], embedding=OpenAIEmbeddings()).as_retriever(search_kwargs={"k":3})

qa = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=retriever
)

symbolic_math = LLMSymbolicMathChain.from_llm(llm=llm)

math_toll = Tool(
  name="Math Equations",
  func=symbolic_math.run,
  description=("use this when you need to solve math equations.")
)

retriever_tool =  Tool(
      name="Knowledge Base",
      func=qa.run,
      description=(
          "use this tool when answering general knowledge queries to get "
          "more information about the topic."
      )
  )

search = GoogleSearchAPIWrapper()
search_tool = Tool(
    name="Google Search",
    func=search.run,
    description=("use this tool to search google when you need up to date or real-time information."),
)

tools=[retriever_tool, search_tool, math_toll]

# prefix = """Have a conversation with a human, answering the following questions as best you can. Use the tools available to answer the question. You have access to the following tools: Knowledge Base, Google Search, Math Equations"""
# """Begin!"

# ----------------
# CHAT HISTORY: {chat_history}
# ----------------
# QUESTION: {input}
# ----------------
# AGENT SCRATCHPAD:{agent_scratchpad}"""

prefix = """Answer the following questions as best you can. You have access to the following tools:

{tools}

This is relevant chat history:

{chat_history}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question"""

suffix = """Begin!

Question: {input}

{agent_scratchpad}"""

prompt = ConversationalAgent.create_prompt(
    tools,
    prefix=prefix,
    suffix=suffix,
    input_variables=["input", "chat_history", "agent_scratchpad"],
)

memory = ConversationBufferWindowMemory(
    memory_key="chat_history",
    k=5,
    return_messages=True
)

agent = initialize_agent(
    agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
    tools=tools,
    llm=llm,
    verbose=True,
    max_iterations=3,
    early_stopping_method="generate",
    memory=memory,
    return_intermediate_steps=False
)

async def run_call(query: str, stream_it: StreamAgentAnswerCallbackHandler):
    agent.agent.llm_chain.llm.callbacks = [stream_it]
    # now query
    return await agent.acall(inputs={"input": query})

async def create_gen(query: str, stream_it: StreamAgentAnswerCallbackHandler):
    task = asyncio.create_task(run_call(query, stream_it))
    async for token in stream_it.aiter():
        print(token)
        sio.emit("next_token", {"token": token})
        eventlet.sleep(0)
    return await task

# query=None
# while True:
#   if not query:
#     query = input("Prompt: ")
#   if query in ["quit", "q", "exit"]:
#     sys.exit()
#   result = agent(query)
#   print(result)

#   query = None

# @app.route("/ask", methods=['POST'])
# def run():
#     data = request.json
#     query_text = data.get('query', '')
#     result = agent(query_text)

#     return jsonify(result), 200

async def callback(ch, method, properties, body):
    json_string = body.decode('utf-8')
    data = json.loads(json_string)
    stream_it = StreamAgentAnswerCallbackHandler()
    result = await create_gen(data["Question"], stream_it)
    # result = agent()
    print(result)

def callback_wrapper(ch, method, properties, body):
    asyncio.run(callback(ch, method, properties, body))

# Set up RabbitMQ connection
credentials = pika.PlainCredentials(os.environ["RABBITMQ_USERNAME"], os.environ["RABBITMQ_PASSWORD"])
def consume_messages():
    connection = pika.BlockingConnection(pika.ConnectionParameters(os.environ["RABBITMQ_HOSTNAME"], 5672, os.environ["RABBITMQ_VIRTUAL_HOST"], credentials))
        
    channel = connection.channel()

    # Declare the queue
    channel.queue_declare(queue='generate_question', durable=True, exclusive=False, auto_delete=True)

    # Set up consumer
    channel.basic_consume(queue='generate_question', on_message_callback=callback_wrapper, auto_ack=True)

    print('Waiting for messages. To exit, press CTRL+C')
    channel.start_consuming()

def run_consumer():
    eventlet.spawn(consume_messages)

if __name__ == "__main__":
    run_consumer() 

    eventlet.wsgi.server(eventlet.listen(('127.0.0.1', 3000)), app)   
    
