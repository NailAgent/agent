from typing import List
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from agent.agents.schema import IntakeResult, BookingSlots

class IntakeAgent:
    """Agent responsible for analyzing user input and extracting booking information."""
    
    def __init__(self, model_name: str = "gpt-4o"):
        self.llm = ChatOpenAI(model=model_name, temperature=0)
        self.structured_llm = self.llm.with_structured_output(IntakeResult)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert booking assistant for a nail shop. 
Your goal is to analyze the customer's message and extract relevant reservation information.

Current Date: 2024-05-05 (Monday)

INSTRUCTIONS:
1. Identify the user's intent (e.g., booking, inquiry, change, cancel).
2. Extract all available slots for booking:
   - name: Customer's name.
   - phone_num: Phone number (standardize to 010-XXXX-XXXX).
   - off_removal: True if they mention removing existing gel, False otherwise.
   - reserve_date: Target date in YYYY-MM-DD format. (Interpret 'tomorrow', 'this Friday' based on Current Date).
   - reserve_time: Target time in HH:MM format.
   - service_code: One of [GEL_BASIC, GEL_NAIL, PEDICURE].
   - past_visit: True if they indicate they have visited before, False otherwise.
3. Determine if any REQUIRED fields are missing for a 'booking' intent. Required fields: name, phone_num, reserve_date, reserve_time, service_code.
4. If fields are missing, set `need_followup` to True and write a polite `followup_question` in Korean.
5. If the user provides a filled-out form, parse it carefully. If they use natural language, extract what you can.

Handle typos and informal language gracefully."""),
            ("human", "{input}")
        ])
        
        self.chain = self.prompt | self.structured_llm

    def run(self, user_input: str) -> IntakeResult:
        """Analyzes input and returns structured results."""
        return self.chain.invoke({"input": user_input})
