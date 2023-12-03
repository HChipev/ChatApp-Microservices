from enum import Enum
from typing import Any, Coroutine, Dict, List, Optional
from uuid import UUID
from langchain.callbacks.streaming_aiter import AsyncIteratorCallbackHandler
from langchain_core.messages import BaseMessage


class FileType(Enum):
    PDF = 1
    PPTX = 2
    DOCX = 3
    HTML = 4
    TXT = 5

# class StreamAgentAnswerCallbackHandler(AsyncFinalIteratorCallbackHandler):
#     def __init__(
#         self,
#         socket
#     ):
#         self.socket = socket
        
#     async def on_chat_model_start(
#         self
#     ):
#         await self.socket.emit("new_entry")

#     async def on_llm_new_token(self, token: str):
#         await self.socket.emit('next_token', {'token': token})

class StreamAgentAnswerCallbackHandler(AsyncIteratorCallbackHandler):
    content: str = ""
    final_answer: bool = False
    
    def __init__(self) -> None:
        super().__init__()

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[BaseMessage]], *, run_id: UUID, parent_run_id: UUID | None = None, tags: List[str] | None = None, metadata: Dict[str, Any] | None = None, **kwargs: Any) -> Coroutine[Any, Any, Any]:
        pass

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.content += token
        # if we passed the final answer, we put tokens in queue
        if self.final_answer:
            if '"action_input": "' in self.content:
                if token not in ['"', "}"]:
                    self.queue.put_nowait(token)
        elif "Final Answer" in self.content:
            self.final_answer = True
            self.content = ""
    
    async def on_llm_end(self, response, **kwargs) -> None:
        if self.final_answer:
            self.content = ""
            self.final_answer = False
            self.done.set()
        else:
            self.content = ""
