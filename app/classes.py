from enum import Enum
import eventlet
from typing import Any, Dict, List
from uuid import UUID
from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.messages import BaseMessage

class DocumentType(Enum):
    PDF = 1
    PPTX = 2
    DOCX = 3
    HTML = 4
    TXT = 5
class StreamAgentAnswerCallbackHandler(BaseCallbackHandler):
    content: str = ""
    final_answer: bool = False
    
    def __init__(self, sio) -> None:
        super().__init__()
        self.sio = sio

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[BaseMessage]], *, run_id: UUID, parent_run_id: UUID | None = None, tags: List[str] | None = None, metadata: Dict[str, Any] | None = None, **kwargs: Any) -> Any:
        pass

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.content += token
        if self.final_answer:
            if '"action_input": "' in self.content:
                if token not in ['"', "}","}\n","```",' "']:

                    if token in ['."','."\n','. "']:
                        token = "."
                    if token in ['?"', '?"\n', '? "']:
                        token = '?'
                    if token in ['!"', '!"\n', '! "']:
                        token = '!'

                    self.sio.emit("next_token", {"token": token, "done": False})
                    eventlet.sleep(0)
        elif "Final Answer" in self.content:
            self.final_answer = True
            self.content = ""
    
    def on_llm_end(self, response, **kwargs) -> None:
        if self.final_answer:
            self.content = ""
            self.final_answer = False
        else:
            self.content = ""
