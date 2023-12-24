import os
import ast
import eventlet
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain_experimental.llm_symbolic_math.base import LLMSymbolicMathChain
from langchain.vectorstores import Pinecone
from langchain.embeddings import OpenAIEmbeddings
from langchain.agents import AgentType, Tool
from langchain.memory import ConversationBufferWindowMemory
from langchain.utilities import GoogleSearchAPIWrapper
from langchain.agents import initialize_agent
from classes import StreamAgentAnswerCallbackHandler

import pinecone


def init_pinecone():
    pinecone.init(
        api_key=os.environ["PINECONE_API_KEY"],
        environment=os.environ["PINECONE_ENVIRONMENT"],
    )


def ask_agent(question, sio, messages, sid, conversationId):
    llm = ChatOpenAI(
        openai_api_key=os.environ["OPENAI_API_KEY"],
        # model="gpt-4-1106-preview",
        model="gpt-3.5-turbo",
        streaming=True,
        temperature=0.3,
        callbacks=[StreamAgentAnswerCallbackHandler(
            sio=sio, sid=sid, conversationId=conversationId)]
    )

    retriever = Pinecone.from_existing_index(
        index_name=os.environ["INDEX_NAME"], embedding=OpenAIEmbeddings()).as_retriever(search_kwargs={"k": 3})

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

    tools = [retriever_tool, search_tool, math_tool]

    memory = ConversationBufferWindowMemory(
        memory_key="chat_history",
        k=4,
        return_messages=True
    )

    for index, message in enumerate(ast.literal_eval(messages)):
        if index % 2 == 0:
            memory.chat_memory.add_user_message(message)
        else:
            memory.chat_memory.add_ai_message(message)

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
        # agent_kwargs={
        #     # 'system_message': system_message,
        #     # 'input_variables': ["input", "agent_scratchpad",]
        #     # 'format_instructions': format_instructions,
        #     # 'suffix': suffix
        # }
    )

    sio.emit("next_token", {"start": True, "done": False,
             "conversationId": conversationId}, sid)

    response = agent({"input": question})

    chat_history = []
    for message in memory.chat_memory.messages:
        chat_history.append(message.content)

    return {
        "response": response,
        "chat_history": str(chat_history)
    }
