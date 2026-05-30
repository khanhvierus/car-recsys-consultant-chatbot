"""Grounded response generation — builds the prompt with structured vehicle
context and instructs gpt-4o-mini to answer ONLY from provided facts.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from .retrieval import QueryConstraints, RetrievedVehicle

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are CarMate, a professional car-shopping assistant for a US marketplace.

GROUNDING RULES — follow strictly:
- Use ONLY the facts in 'VEHICLE CONTEXT'. Never invent prices, specs, mileage, or availability.
- When you mention a specific car, cite it inline as [#N] using its option number.
- If the context has no good match for the request, say so honestly and ask one clarifying question.
- Format prices with thousands separators (e.g. $21,950) and mileage like 38,000 miles.
- Be concise, friendly and practical — like a knowledgeable salesperson, not a brochure.
- Use bullet points when comparing two or more cars.
- Do not output raw VINs or internal IDs to the user; refer to cars by name + option number."""

_CONDENSE_PROMPT = """Given the chat history and the latest user message, rewrite the latest
message as a standalone search query that captures the user's full intent
(carry over brand/budget/body-type mentioned earlier). Output ONLY the rewritten
query, nothing else."""


def format_grounding(vehicles: list[RetrievedVehicle]) -> str:
    """Numbered, structured context block — the only facts the LLM may use."""
    if not vehicles:
        return "VEHICLE CONTEXT: (no matching listings found)"
    lines = ["VEHICLE CONTEXT — matching listings:"]
    for i, v in enumerate(vehicles, 1):
        p = v.payload
        price = f"${float(p['price']):,.0f}" if p.get("price") else "N/A"
        mileage = f"{int(p['mileage']):,} mi" if p.get("mileage") else "N/A"
        rating = f"{p['car_rating']}/5" if p.get("car_rating") else "N/A"
        lines.append(
            f"[#{i}] {p.get('new_used') or ''} {p.get('title') or p.get('car_name') or 'Car'}".strip()
            + f" | Brand: {p.get('brand') or 'N/A'}"
            + f" | Price: {price} | Mileage: {mileage}"
            + f" | Fuel: {p.get('fuel_type') or 'N/A'}"
            + f" | Owner rating: {rating}"
        )
    return "\n".join(lines)


def _constraint_note(c: QueryConstraints) -> str:
    if c.is_empty():
        return ""
    bits = []
    if c.price_max:
        bits.append(f"budget ≤ ${c.price_max:,.0f}")
    if c.price_min:
        bits.append(f"budget ≥ ${c.price_min:,.0f}")
    if c.brand:
        bits.append(f"brand {c.brand}")
    if c.new_used:
        bits.append(c.new_used.lower())
    if c.fuel_type:
        bits.append(c.fuel_type.lower())
    if c.year:
        bits.append(f"year {c.year}")
    return "Detected user constraints: " + ", ".join(bits) + "."


class ResponseGenerator:
    def __init__(self, llm: Any):
        self.llm = llm

    def condense_question(
        self, history: list[BaseMessage], user_input: str
    ) -> str:
        """Rewrite a follow-up into a self-contained search query."""
        if not history:
            return user_input
        prompt = ChatPromptTemplate.from_messages([
            ("system", _CONDENSE_PROMPT),
            MessagesPlaceholder("chat_history"),
            ("human", "{question}"),
        ])
        try:
            return (prompt | self.llm | StrOutputParser()).invoke(
                {"chat_history": history, "question": user_input}
            ).strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("condense_question failed: %s", exc)
            return user_input

    def generate(
        self,
        history: list[BaseMessage],
        user_input: str,
        vehicles: list[RetrievedVehicle],
        constraints: QueryConstraints,
    ) -> str:
        grounding = format_grounding(vehicles)
        note = _constraint_note(constraints)
        prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM_PROMPT),
            ("system", "{grounding}"),
            ("system", "{note}"),
            MessagesPlaceholder("chat_history"),
            ("human", "{question}"),
        ])
        try:
            return (prompt | self.llm | StrOutputParser()).invoke({
                "grounding": grounding,
                "note": note,
                "chat_history": history,
                "question": user_input,
            })
        except Exception as exc:  # noqa: BLE001
            log.error("LLM generation failed: %s", exc)
            return ("Sorry — I'm having trouble generating a response right now. "
                    "Please try again in a moment.")
