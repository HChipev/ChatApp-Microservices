import os
import json
import pika
import eventlet
import socketio
from flask import Flask
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain_experimental.llm_symbolic_math.base import LLMSymbolicMathChain
from langchain.vectorstores import Pinecone
from langchain.embeddings import OpenAIEmbeddings
from langchain.agents import AgentType, Tool, ConversationalChatAgent, AgentExecutor
from langchain.memory import ConversationBufferWindowMemory
from langchain.utilities import GoogleSearchAPIWrapper
from langchain.agents import initialize_agent
from classes import StreamAgentAnswerCallbackHandler
from dotenv import load_dotenv
import pinecone

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

llm = ChatOpenAI(
    openai_api_key=os.environ["OPENAI_API_KEY"],
    model="gpt-4-1106-preview",
    # model="gpt-3.5-turbo",
    streaming=True,
    temperature=0,
    callbacks=[StreamAgentAnswerCallbackHandler(sio=sio)]
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

math_tool = Tool(
    name="Math Equations",
    func=symbolic_math.run,
    description=(
        "Use this tool when you encounter math equations that need solving. "
        "It employs symbolic math to provide accurate solutions."
    )
)

retriever_tool = Tool(
    name="Knowledge Base",
    func=qa.run,
    description=(
        "Leverage this tool when responding to general knowledge queries. "
        "It taps into a comprehensive knowledge base, enhancing your responses."
    )
)

search = GoogleSearchAPIWrapper()
search_tool = Tool(
    name="Google Search",
    func=search.run,
    description=(
        "Activate this tool to perform Google searches and obtain up-to-date, real-time information. "
        "Ideal for staying current on the latest developments."
    )
)

tools=[retriever_tool, search_tool, math_tool]

# system_message = """Answer the following questions as best you can like you have a conversation. You have access to the following tools:

# Use the following format:

# Question: the input question you must answer
# Thought: you should always think about what to do
# Action: the action to take
# Action Input: the input to the action
# Observation: the result of the action
# ... (this Thought/Action/Action Input/Observation can repeat N times)
# Thought: I now know the final answer
# Final Answer: the final answer to the original input question

# Begin!

# Question: {input}

# {agent_scratchpad}"""

# prompt = ConversationalChatAgent.create_prompt(
#     tools,
#     system_message=system_message,
#     input_variables=["input", "agent_scratchpad"],
# )

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
    handle_parsing_errors=True,
    return_intermediate_steps=False,
    agent_kwargs={
        # 'system_message': system_message, 
        # 'input_variables': ["input", "agent_scratchpad",]
        # 'format_instructions': format_instructions,
        # 'suffix': suffix
    }
)

def callback(ch, method, properties, body):
    sio.emit("add_entry")
    eventlet.sleep(0)

    json_string = body.decode('utf-8')
    data = json.loads(json_string)

    result = agent({"input": data["Question"]})
    print(result)

credentials = pika.PlainCredentials(os.environ["RABBITMQ_USERNAME"], os.environ["RABBITMQ_PASSWORD"])

def consume_messages():
    connection = pika.BlockingConnection(pika.ConnectionParameters(os.environ["RABBITMQ_HOSTNAME"], 5672, os.environ["RABBITMQ_VIRTUAL_HOST"], credentials))
        
    channel = connection.channel()

    channel.queue_declare(queue='generate_question', durable=True, exclusive=False, auto_delete=True)

    channel.basic_consume(queue='generate_question', on_message_callback=callback, auto_ack=True)

    print('Waiting for messages. To exit, press CTRL+C')
    channel.start_consuming()

def run_consumer():
    eventlet.spawn(consume_messages)

if __name__ == "__main__":
    run_consumer() 
    eventlet.wsgi.server(eventlet.listen(('127.0.0.1', 3000)), app)   
    
