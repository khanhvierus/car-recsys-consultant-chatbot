import os
import re
import operator
from collections import defaultdict
from dataclasses import dataclass
from typing import Annotated, Optional, Sequence, TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.graph import END, StateGraph

from .user_profile import (
    ProfileUpdate,
    UserProfile,
    load_profile,
    log_viewed,
    merge_update,
    save_profile,
)

load_dotenv()

# DB Init
WAREHOUSE_DSN = os.getenv("WAREHOUSE_DSN") or os.getenv("DATABASE_URL")
db_engine = create_engine(WAREHOUSE_DSN, pool_size=10, max_overflow=20)

COLLECTION_NAME = os.getenv("CHATBOT_QDRANT_COLLECTION", "car_vectorize")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")


"""
SQL View: [dbo].[view_post_info]
select 
    pp.post_link,
    pp.[VIN],
    pp.[status],
    pp.title,
    cb.brand,
    pp.price,
    pp.mileage,
    1.00 * (pp.MPG_max + pp.MPG_min)/ 2 as mpg,
    pp.monthly_payment,
    lc1.color as interior_color,
    lc2.color as exterior_color,
    ld.drivetrain as drivetrain,
    lf.fuel_type as fuel_type,
    lt.transmission as transmission,
    le.engine as engine,
    fft.feature_type,
    ff.feature_name
from post.Post pp
join core.Car cc on pp.car_model = cc.car_model
join core.Brand cb on cc.car_brand = cb.brand_id
JOIN seller.Seller ss on pp.seller_key = ss.seller_key
join lookup.Color lc1 on pp.interior_color = lc1.color_id
join lookup.Color lc2 on pp.exterior_color = lc2.color_id
join lookup.Drivetrain ld on pp.drivetrain = ld.drivetrain_id
JOIN lookup.Fuel_type lf on pp.fuel_type = lf.fuel_type_id
join lookup.Transmission lt on pp.transmission = lt.transmission_id
join lookup.Engine le on pp.engine = le.engine_id 
join post.Post_Feature ppf on pp.VIN = ppf.VIN
join feature.Feature ff on ppf.feature_id = ff.feature_id
join feature.Feature_type fft on ff.feature_type_id = fft.feature_type_id
"""

"""
SQL View: [dbo].[view_post_feature]
select 
    pp.VIN,
    pp.title,
    fft.feature_type,
    ff.feature_name
from post.post pp 
join post.Post_Feature ppf on pp.VIN = ppf.VIN
join feature.Feature ff on ppf.feature_id = ff.feature_id
join feature.Feature_type fft on ff.feature_type_id = fft.feature_type_id
"""


"""
SQL View: [dbo].[view_post_image]
select 
    pp.VIN,
    pp.title,
    ppi.image_link
from post.Post pp  
join post.Post_image ppi on pp.VIN = ppi.VIN
WHERE ppi.main_image = 1
"""

# --- Helper Functions ---
def get_image_urls(vin_query: str, max_images: int = 3):
    with db_engine.connect() as con:
        rows = con.execute(
            text("""
                SELECT image_url FROM gold.vehicle_images
                WHERE vehicle_id = :vin ORDER BY image_order LIMIT :n
            """),
            {"vin": vin_query, "n": max_images},
        ).all()
    return [r[0] for r in rows if r[0]]


def get_feature(vin_query: str):
    feature = defaultdict(list)
    with db_engine.connect() as con:
        rows = con.execute(
            text("""
                SELECT feature_category, feature_name FROM gold.vehicle_features
                WHERE vehicle_id = :vin AND feature_name IS NOT NULL
            """),
            {"vin": vin_query},
        ).all()
    for cat, name in rows:
        if name not in feature[cat or "Other"]:
            feature[cat or "Other"].append(name)
    return dict(feature)

def get_avg_price(brand: str = None, model: str = None):
    conditions = ["price IS NOT NULL", "price > 0"]
    params = {}
    if brand:
        conditions.append("brand = :brand")
        params["brand"] = brand
    if model:
        conditions.append("(car_name ILIKE :model OR title ILIKE :model)")
        params["model"] = f"%{model}%"
    query = text(f"""
        SELECT AVG(price) AS avg_price, MIN(price) AS min_price,
               MAX(price) AS max_price, COUNT(DISTINCT vin) AS total
        FROM gold.vehicles
        WHERE {' AND '.join(conditions)}
    """)
    with db_engine.connect() as con:
        row = con.execute(query, params).mappings().first()
        return dict(row) if row else {}


def format_docs(docs):
    if not docs:
        return "No relevant car listings found."

    formatted = ""

    for i, (doc, score) in enumerate(docs, 1):
        if score > 1.3:
            continue

        meta = doc.metadata
        vin = meta.get("VIN", "N/A")

        # image URLS
        images = get_image_urls(vin, 3)
        if images:
            img_str = "\n".join([f"- {u}" for u in images])
        else:
            img_str = "- No images available"

        # Post Feature
        features = get_feature(vin)
        if features:
            feature_lines = []
            for f_type, f_names in features.items():
                joined_names = ", ".join(f_names)
                feature_lines.append(f"{f_type}: {joined_names}")
            feature_str = "\n".join([f"- {line}" for line in feature_lines])
        else:
            feature_str = "- No feature data"

        formatted += f"""
            --- Car Option {i} (Score {score:.2f}) ---
            VIN: {vin}
            Details Metadata: {meta}

            Features:
            {feature_str}

            Images:
            {img_str}
        """
    return formatted or "No relevant car listings found."

# --- SQL Retrieval (exact brand/model lookup) ---
_NUM_RE = re.compile(r"\$?\s*([\d][\d,]*(?:\.\d+)?)\s*(k|thousand)?", re.I)
_OVER_RE = re.compile(r"(over|above|more than|at least|min|from|>)", re.I)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_FUEL_MAP = {
    "gasoline": "Gasoline", "gas": "Gasoline", "petrol": "Gasoline",
    "hybrid": "Hybrid", "electric": "Electric", "ev": "Electric",
    "diesel": "Diesel", "plug-in": "Plug-In Hybrid",
}
_STATUS_MAP = {
    "brand new": "New", "new": "New", "used": "Used",
    "pre-owned": "Used", "second hand": "Used", "certified": "Certified",
}


@dataclass
class CarConstraints:
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    status: Optional[str] = None
    fuel_type: Optional[str] = None
    year: Optional[int] = None


def parse_constraints(message: str) -> CarConstraints:
    msg = message.lower()
    c = CarConstraints()

    for m in _NUM_RE.finditer(message):
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if (m.group(2) or "").lower() in ("k", "thousand"):
            value *= 1_000
        if value < 1000:
            continue
        window = message[max(0, m.start() - 25):m.start()]
        if _OVER_RE.search(window):
            c.price_min = value
        else:
            c.price_max = value
        break

    for kw, canon in _STATUS_MAP.items():
        if kw in msg:
            c.status = canon
            break

    for kw, canon in _FUEL_MAP.items():
        if re.search(rf"\b{re.escape(kw)}\b", msg):
            c.fuel_type = canon
            break

    ym = _YEAR_RE.search(message)
    if ym:
        c.year = int(ym.group(0))
    return c


def sql_search_cars(brand=None, model=None, constraints=None, exclude_brands=None, limit=6):
    conditions = ["title IS NOT NULL"]
    params = {"limit": limit}

    if brand:
        conditions.append("brand = :brand")
        params["brand"] = brand
    if model:
        conditions.append("title ILIKE :model")
        params["model"] = f"%{model}%"
    for i, excluded in enumerate(exclude_brands or []):
        conditions.append(f"brand <> :exb{i}")
        params[f"exb{i}"] = excluded
    if constraints:
        if constraints.status:
            conditions.append("new_used ILIKE :status")
            params["status"] = f"%{constraints.status}%"
        if constraints.fuel_type:
            conditions.append("fuel_type ILIKE :fuel_type")
            params["fuel_type"] = f"%{constraints.fuel_type}%"
        if constraints.price_min is not None:
            conditions.append("price >= :price_min")
            params["price_min"] = constraints.price_min
        if constraints.price_max is not None:
            conditions.append("price <= :price_max")
            params["price_max"] = constraints.price_max
        if constraints.year:
            conditions.append("title ILIKE :year")
            params["year"] = f"%{constraints.year}%"

    query = text(f"""
        SELECT DISTINCT
            vin AS "VIN", new_used AS status, title, brand,
            exterior_color, interior_color, drivetrain, fuel_type,
            transmission, engine, price, monthly_payment, mileage, mpg,
            vehicle_url AS post_link
        FROM gold.vehicles
        WHERE {' AND '.join(conditions)}
        ORDER BY price ASC
        LIMIT :limit
    """)

    with db_engine.connect() as con:
        return con.execute(query, params).mappings().all()


def format_sql_cars(rows):
    if not rows:
        return "No matching car listings found in the database."

    formatted = ""

    seen_models = {}

    for i, row in enumerate(rows, 1):
        vin = row.get("VIN") or "N/A"
        brand = row.get("brand") or ""
        title = row.get("title") or ""
        listing_price = row.get("price") or 0

        model_key = f"{brand}_{title}".lower()
        if model_key not in seen_models:
            price_stats = get_avg_price(brand=brand, model=title)
            seen_models[model_key] = price_stats
        else:
            price_stats = seen_models[model_key]

        images = get_image_urls(vin, 3)
        img_str = "\n".join(f"- {u}" for u in images) or "- No images available"

        features = get_feature(vin)
        if features:
            feature_str = "\n".join(
                f"- {f_type}: {', '.join(f_names)}"
                for f_type, f_names in features.items()
            )
        else:
            feature_str = "- No feature data"

        avg_price = price_stats.get("avg_price") or listing_price
        min_price = price_stats.get("min_price") or listing_price
        max_price = price_stats.get("max_price") or listing_price

        formatted += f"""
            --- Car Option {i} ---
            VIN: {vin}
            Details Metadata: {dict(row)}
            Average Market Price: ${avg_price:,.0f} (range: ${min_price:,.0f} - ${max_price:,.0f})

            Features:
            {feature_str}

            Images:
            {img_str}
        """
    return formatted


def get_standalone_question(llm, history, user_input):
    if not history:
        return user_input

    condense_prompt = """Given a chat history and the latest user question which might reference context in the chat history, formulate a standalone question which can be understood, contain and capture all the chat history. Do NOT answer the question, just reformulate it if needed or return it as is."""

    prompt = ChatPromptTemplate.from_messages([
        ("system", condense_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{question}")
    ])

    chain = prompt | llm | StrOutputParser()
    return chain.invoke({"chat_history": history, "question": user_input})


# Core slots required before running a consultation retrieval
CORE_SLOTS = ("budget_max", "body_type", "fuel_type")


class AgenticState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    question: str
    query: str
    context: str
    answer: str
    intent: str
    brand: Optional[str]
    model: Optional[str]
    session_id: str
    profile: dict


class IntentDecision(BaseModel):
    intent: str = Field(
        description="'compare' when the user wants to compare two or more specific cars "
        "(e.g. 'Compare Toyota Camry vs Honda Civic', 'BMW X3 vs Audi Q5 vs Mercedes GLC'). "
        "'analytics' when the user asks about website statistics, trends, rankings, "
        "most popular brands, most posted cars, top rated, most reviewed, inventory counts, "
        "or any aggregate/summary data about the platform. "
        "'specs' when the user asks about technical specifications, features, "
        "engine details, safety systems, or performance data of a specific car. "
        "'specific' when the user wants to find/buy an exact car brand/model. "
        "'vague' when they describe needs without a specific car. "
        "'chitchat' for greetings or casual talk still related to cars/buying. "
        "'off_topic' when the user talks about something completely unrelated to cars, "
        "automotive, or vehicle shopping (e.g. cooking, weather, politics, games)."
    )
    brand: Optional[str] = Field(default=None, description="Exact car brand mentioned, else null.")
    model: Optional[str] = Field(default=None, description="Exact car model/name mentioned, else null.")


class CompareItem(BaseModel):
    brand: str = Field(description="Car brand name.")
    model: str = Field(description="Car model name.")
    year: Optional[int] = Field(default=None, description="Model year if mentioned, else null.")


class CompareExtraction(BaseModel):
    cars: list[CompareItem] = Field(
        description="List of cars the user wants to compare (at least 2)."
    )


def _core_complete(profile: dict) -> bool:
    core = profile.get("core_slots", {})
    return all(core.get(k) for k in CORE_SLOTS)


def _build_agentic_app(llm, vector_store):

    def route_intent(state: AgenticState):
        router_llm = llm.with_structured_output(IntentDecision)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You route a car consultation assistant.\n"
                    "intent='compare' when the user wants to compare two or more specific "
                    "cars side by side (e.g. 'Compare Toyota Camry vs Honda Civic', "
                    "'BMW X3 vs Audi Q5', 'Difference between Corolla and Civic').\n"
                    "intent='analytics' when the user asks about website/platform statistics, "
                    "trends, rankings, popularity, inventory summary, or aggregate data "
                    "(e.g. 'What brand has the most listings?', 'Most popular car type?', "
                    "'How many cars are on the site?', 'What are the top rated cars?', "
                    "'Which models have the most reviews?').\n"
                    "intent='specs' when the user asks about technical specifications, "
                    "features, engine details, horsepower, torque, safety systems, "
                    "drivetrain, MPG, dimensions, or performance data of a specific car "
                    "(e.g. 'What are the safety features of BMW X5?', "
                    "'How much horsepower does the Camry have?', "
                    "'Tell me the specs of Honda Civic 2024').\n"
                    "intent='specific' when the user wants to find, compare, or buy "
                    "a specific car brand/model (e.g. 'Show me available BMW i5').\n"
                    "intent='vague' when the user describes needs, budget, or usage without "
                    "a specific car (e.g. 'I need a family car around $40,000').\n"
                    "intent='chitchat' for greetings or casual talk still about cars "
                    "(e.g. 'Hi', 'Thanks').\n"
                    "intent='off_topic' when the message is completely unrelated to cars, "
                    "automotive, or vehicle shopping (e.g. 'What is the weather today?', "
                    "'Tell me a joke', 'How to cook pasta?').\n"
                    "Extract the exact brand and model if present, else null.",
                ),
                MessagesPlaceholder("chat_history"),
                ("human", "{question}"),
            ]
        )
        result = (prompt | router_llm).invoke(
            {"chat_history": state["messages"], "question": state["question"]}
        )
        print(f"[INTENT] intent={result.intent} brand={result.brand} model={result.model}")
        return {
            "intent": result.intent,
            "brand": result.brand,
            "model": result.model,
            "messages": [],
        }

    def update_profile(state: AgenticState):
        profile = UserProfile(**(state.get("profile") or {}))
        updater = llm.with_structured_output(ProfileUpdate)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You maintain a persistent car-shopping profile for the customer.\n"
                    "Current profile (JSON): {profile}\n"
                    "From the latest message and the history, extract NEW or CHANGED info only:\n"
                    "- core slots: budget (USD number), body_type, fuel_type, brand, condition.\n"
                    "- add_features and vibe for soft preferences.\n"
                    "- exclude_brands when the customer dislikes or wants to avoid a brand.\n"
                    "- interested_models for specific models the customer asks about.\n"
                    "Leave fields empty or null when there is nothing new.",
                ),
                MessagesPlaceholder("chat_history"),
                ("human", "{question}"),
            ]
        )
        update = (prompt | updater).invoke(
            {
                "profile": profile.model_dump_json(),
                "chat_history": state["messages"],
                "question": state["question"],
            }
        )
        profile = merge_update(profile, update)
        print(f"[PROFILE] {profile.model_dump()}")
        return {"profile": profile.model_dump(), "messages": []}

    def ask_slot(state: AgenticState):
        core = state["profile"].get("core_slots", {})
        missing = [k for k in CORE_SLOTS if not core.get(k)]
        known = {k: v for k, v in core.items() if v}
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a friendly car sales consultant. The customer has not given "
                    "enough detail yet.\n"
                    "Known preferences: {known}\n"
                    "Missing details: {missing}\n"
                    "Ask ONE short, natural question to gather the missing details. "
                    "Offer concrete options when helpful (e.g. SUV vs Sedan, "
                    "Gasoline vs Hybrid vs Electric). Do not list cars yet. "
                    "Reply in the same language the customer is using.",
                ),
                MessagesPlaceholder("chat_history"),
                ("human", "{question}"),
            ]
        )
        chain = prompt | llm | StrOutputParser()
        answer = chain.invoke(
            {
                "known": known,
                "missing": missing,
                "chat_history": state["messages"],
                "question": state["question"],
            }
        )
        print(f"[ASK SLOT] missing={missing} question={answer!r}")
        return {"answer": answer}

    def hybrid_retrieve(state: AgenticState):
        profile = state.get("profile") or {}
        core = profile.get("core_slots", {})
        soft = profile.get("soft_preferences", {})
        excluded = profile.get("excluded_brands", [])

        if state.get("intent") == "specific":
            brand = state.get("brand")
            model = state.get("model")
            constraints = parse_constraints(state["question"])
            soft_query = state["query"]
        else:
            brand = core.get("brand")
            model = None
            constraints = CarConstraints(
                price_min=core.get("budget_min"),
                price_max=core.get("budget_max"),
                status=core.get("condition"),
                fuel_type=core.get("fuel_type"),
            )
            soft_parts = [core.get("body_type"), soft.get("vibe"), *(soft.get("features") or [])]
            soft_query = " ".join(p for p in soft_parts if p) or state["query"]

        rows = sql_search_cars(
            brand=brand, model=model, constraints=constraints,
            exclude_brands=excluded, limit=6,
        )
        sql_ctx = format_sql_cars(rows)

        vec_results = vector_store.similarity_search_with_score(soft_query, k=5)
        if excluded:
            excluded_low = {b.lower() for b in excluded}
            vec_results = [
                (doc, score) for doc, score in vec_results
                if (doc.metadata.get("Brand", "") or "").lower() not in excluded_low
            ]
        vec_ctx = format_docs(vec_results)

        context = f"[SQL HARD-FILTER MATCHES]\n{sql_ctx}\n\n[SEMANTIC MATCHES]\n{vec_ctx}"

        profile_obj = log_viewed(UserProfile(**profile), [r.get("title") for r in rows])
        print(f"[HYBRID] sql_rows={len(rows)} vector_hits={len(vec_results)} soft_query={soft_query!r}")
        print(f"[HYBRID CONTEXT]\n{context}")
        return {"context": context, "profile": profile_obj.model_dump(), "messages": []}

    def consult(state: AgenticState):
        system_prompt = """You are an expert car sales consultant.

Use ONLY the provided 'Knowledge Context' (SQL hard-filter matches and semantic matches).
1. Recommend the 2-3 most suitable cars for the customer's stated preferences.
2. For each car show ONLY: title, brand, status (new/used), mileage, price, exterior color, key features.
3. Add a short, tailored pros/cons for each option based on the customer's preferences.
4. Always format price with comma separators (e.g., $21,950).
5. Keep it natural and persuasive, like a professional consultant.
6. Provide images or extra details ONLY when the customer explicitly requests them.
7. Include [View Details](post_link) when a link is available in the metadata.
8. If nothing fits, say so honestly and offer the closest alternatives or general advice.
Use the Customer Profile for personalization. NEVER recommend any brand in excluded_brands.
Reply in the same language the customer is using.
"""
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("system", "Customer Profile (JSON):\n{profile}"),
                ("system", "Knowledge Context:\n{context}"),
                MessagesPlaceholder("chat_history"),
                ("human", "{question}"),
            ]
        )
        chain = prompt | llm | StrOutputParser()
        answer = chain.invoke(
            {
                "profile": state.get("profile", {}),
                "context": state.get("context", ""),
                "chat_history": state["messages"],
                "question": state["question"],
            }
        )
        print(f"[CONSULT] answer={answer!r}")
        return {"answer": answer}

    def spec_retrieve(state: AgenticState):
        brand = state.get("brand")
        model = state.get("model")

        rows = sql_search_cars(brand=brand, model=model, limit=3)

        if not rows:
            return {"context": "No matching car found for spec lookup.", "messages": []}

        spec_parts = []
        for i, row in enumerate(rows, 1):
            vin = row.get("VIN", "N/A")

            features = get_feature(vin)
            if features:
                feature_str = "\n".join(
                    f"  - {f_type}: {', '.join(f_names)}"
                    for f_type, f_names in features.items()
                )
            else:
                feature_str = "  - No feature data"

            images = get_image_urls(vin, 3)
            img_str = "\n".join(f"  - {u}" for u in images) or "  - No images"

            spec_parts.append(
                f"--- Car {i} ---\n"
                f"Title: {row.get('title', 'N/A')}\n"
                f"Brand: {row.get('brand', 'N/A')}\n"
                f"Engine: {row.get('engine', 'N/A')}\n"
                f"Drivetrain: {row.get('drivetrain', 'N/A')}\n"
                f"Fuel Type: {row.get('fuel_type', 'N/A')}\n"
                f"Transmission: {row.get('transmission', 'N/A')}\n"
                f"MPG: {row.get('mpg', 'N/A')}\n"
                f"Mileage: {row.get('mileage', 'N/A')}\n"
                f"Price: {row.get('price', 'N/A')}\n"
                f"Exterior: {row.get('exterior_color', 'N/A')}\n"
                f"Interior: {row.get('interior_color', 'N/A')}\n"
                f"Post Link: {row.get('post_link', 'N/A')}\n"
                f"Features:\n{feature_str}\n"
                f"Images:\n{img_str}"
            )

        context = "\n\n".join(spec_parts)
        print(f"[SPEC RETRIEVE] brand={brand} model={model} found={len(rows)}")
        return {"context": context, "messages": []}

    def spec_answer(state: AgenticState):
        system_prompt = """You are a knowledgeable car technical advisor.

The customer is asking about technical specifications or features of a specific car.
Use ONLY the provided context to answer.
1. Present specs in a clear, organized format grouped by category
   (Performance, Drivetrain, Fuel Economy, Safety, Comfort, Technology, etc.).
2. Highlight standout features relevant to the customer's question.
3. If available, mention how the specs compare to segment averages.
4. Include [View Details](post_link) when a link is available.
5. If specs are not available, say so honestly.
Reply in the same language the customer is using.
"""
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("system", "Technical Context:\n{context}"),
                MessagesPlaceholder("chat_history"),
                ("human", "{question}"),
            ]
        )
        chain = prompt | llm | StrOutputParser()
        answer = chain.invoke(
            {
                "context": state.get("context", ""),
                "chat_history": state["messages"],
                "question": state["question"],
            }
        )
        print(f"[SPEC ANSWER] answer={answer!r}")
        return {"answer": answer}

    def analytics_retrieve(state: AgenticState):
        brand = state.get("brand")
        model = state.get("model")
        feature_view = os.getenv("FEATURE_POST")

        queries = {}
        params = {}

        if brand:
            queries["brand_top_sellers"] = text(f"""
                SELECT car_name, COUNT(vin) AS total_listings,
                       MAX(car_rating) AS car_rating, MAX(percentage_recommend) AS percentage_recommend
                FROM gold.vehicles WHERE brand = :brand
                GROUP BY car_name ORDER BY total_listings DESC, car_rating DESC LIMIT 10
            """)
            params["brand_top_sellers"] = {"brand": brand}

            queries["brand_price_stats"] = text(f"""
                SELECT AVG(price) AS avg_price, MIN(price) AS min_price, MAX(price) AS max_price,
                       COUNT(DISTINCT vin) AS total_cars
                FROM gold.vehicles WHERE brand = :brand AND price IS NOT NULL AND price > 0
            """)
            params["brand_price_stats"] = {"brand": brand}

            queries["brand_fuel_types"] = text(f"""
                SELECT fuel_type, COUNT(vin) AS total FROM gold.vehicles
                WHERE brand = :brand AND fuel_type IS NOT NULL
                GROUP BY fuel_type ORDER BY total DESC
            """)
            params["brand_fuel_types"] = {"brand": brand}

            queries["brand_top_rated"] = text(f"""
                SELECT car_name, MAX(car_rating) AS car_rating, MAX(percentage_recommend) AS percentage_recommend
                FROM gold.vehicles WHERE brand = :brand AND car_rating IS NOT NULL
                GROUP BY car_name ORDER BY car_rating DESC, percentage_recommend DESC LIMIT 10
            """)
            params["brand_top_rated"] = {"brand": brand}

            if model:
                queries["model_top_sellers"] = text("""
                    SELECT title, price, mileage, new_used AS status, fuel_type, vehicle_url AS post_link
                    FROM gold.vehicles
                    WHERE brand = :brand AND car_name ILIKE :model
                    ORDER BY price ASC LIMIT 10
                """)
                params["model_top_sellers"] = {"brand": brand, "model": f"%{model}%"}

            queries["brand_top_features"] = text(f"""
                SELECT vf.feature_name, vf.feature_category AS feature_type_name, COUNT(DISTINCT vf.vehicle_id) AS total
                FROM gold.vehicle_features vf
                JOIN gold.vehicles v ON v.vehicle_id = vf.vehicle_id
                WHERE v.brand = :brand
                GROUP BY vf.feature_name, vf.feature_category
                ORDER BY total DESC LIMIT 15
            """)
            params["brand_top_features"] = {"brand": brand}
        else:
            queries["brand_counts"] = text("""
                SELECT brand, COUNT(vin) AS total
                FROM gold.vehicles WHERE brand IS NOT NULL
                GROUP BY brand ORDER BY total DESC LIMIT 10
            """)
            params["brand_counts"] = {}

            queries["fuel_type_counts"] = text("""
                SELECT fuel_type, COUNT(vin) AS total
                FROM gold.vehicles WHERE fuel_type IS NOT NULL
                GROUP BY fuel_type ORDER BY total DESC
            """)
            params["fuel_type_counts"] = {}

            queries["price_stats"] = text("""
                SELECT COUNT(DISTINCT vin) AS total_cars, MIN(price) AS min_price,
                       MAX(price) AS max_price, AVG(price) AS avg_price
                FROM gold.vehicles WHERE price IS NOT NULL AND price > 0
            """)
            params["price_stats"] = {}

            queries["top_models"] = text("""
                SELECT car_name, AVG(price) AS price_avg,
                       MAX(car_rating) AS car_rating, MAX(percentage_recommend) AS percentage_recommend
                FROM gold.vehicles
                GROUP BY car_name ORDER BY car_rating DESC, percentage_recommend DESC, price_avg ASC LIMIT 10
            """)
            params["top_models"] = {}

            queries["model_counts"] = text("""
                SELECT car_name, brand, COUNT(vin) AS total_listings,
                       AVG(price) AS avg_price, MAX(car_rating) AS car_rating
                FROM gold.vehicles WHERE car_name IS NOT NULL
                GROUP BY car_name, brand ORDER BY total_listings DESC LIMIT 15
            """)
            params["model_counts"] = {}

            if feature_view:
                queries["top_features"] = text("""
                    SELECT feature_name, COUNT(DISTINCT vehicle_id) AS total
                    FROM gold.vehicle_features WHERE feature_name IS NOT NULL
                    GROUP BY feature_name ORDER BY total DESC LIMIT 10
                """)
                params["top_features"] = {}

        results = {}
        with db_engine.connect() as con:
            for key, query in queries.items():
                try:
                    rows = con.execute(query, params.get(key, {})).mappings().all()
                    results[key] = [dict(r) for r in rows]
                except Exception as e:
                    results[key] = f"Error: {e}"

        context_parts = []

        if brand:
            context_parts.append(f"[ANALYTICS FOR: {brand.upper()}]")

            if results.get("brand_price_stats") and isinstance(results["brand_price_stats"], list):
                stats = results["brand_price_stats"][0] if results["brand_price_stats"] else {}
                context_parts.append(
                    f"[{brand.upper()} INVENTORY]\n"
                    f"Total listings: {stats.get('total_cars', 'N/A')}\n"
                    f"Price range: ${stats.get('min_price', 0):,.0f} - ${stats.get('max_price', 0):,.0f}\n"
                    f"Average price: ${stats.get('avg_price', 0):,.0f}"
                )

            if results.get("brand_top_sellers") and isinstance(results["brand_top_sellers"], list):
                lines = []
                for r in results["brand_top_sellers"]:
                    rating = f"Rating: {r['car_rating']}/5" if r.get('car_rating') else ""
                    recommend = f"({r['percentage_recommend']}% recommend)" if r.get('percentage_recommend') else ""
                    lines.append(
                        f"  {r['car_name']} - {r['total_listings']} listings, "
                        f"avg ${r.get('avg_price', 0):,.0f} {rating} {recommend}"
                    )
                context_parts.append(f"[{brand.upper()} TOP SELLERS]\n" + "\n".join(lines))

            if results.get("model_top_sellers") and isinstance(results["model_top_sellers"], list):
                lines = []
                for i, r in enumerate(results["model_top_sellers"], 1):
                    fuel = r.get('fuel_type', 'N/A')
                    status = r.get('status', 'N/A')
                    mileage = f"{r['mileage']:,.0f} mi" if r.get('mileage') else "N/A"
                    link = r.get('post_link', '')
                    lines.append(
                        f"  {i}. {r.get('title', 'N/A')} | {status} | "
                        f"${r.get('price', 0):,.0f} | {mileage} | {fuel} | "
                        f"{r.get('exterior_color', 'N/A')}"
                        + (f" | [View]({link})" if link else "")
                    )
                model_label = model.upper() if model else "MODEL"
                context_parts.append(
                    f"[{brand.upper()} {model_label} - TOP LISTINGS]\n" + "\n".join(lines)
                )

            if results.get("brand_top_rated") and isinstance(results["brand_top_rated"], list):
                lines = []
                for r in results["brand_top_rated"]:
                    recommend = f"({r['percentage_recommend']}% recommend)" if r.get('percentage_recommend') else ""
                    lines.append(
                        f"  {r['car_name']} - Rating: {r.get('car_rating', 'N/A')}/5 "
                        f"{recommend}, avg ${r.get('avg_price', 0):,.0f}"
                    )
                context_parts.append(f"[{brand.upper()} TOP RATED]\n" + "\n".join(lines))

            if results.get("brand_fuel_types") and isinstance(results["brand_fuel_types"], list):
                lines = [f"  {r['fuel_type']}: {r['total']}" for r in results["brand_fuel_types"]]
                context_parts.append(f"[{brand.upper()} FUEL TYPES]\n" + "\n".join(lines))

            if results.get("brand_top_features") and isinstance(results["brand_top_features"], list):
                lines = [
                    f"  {r['feature_name']} ({r['feature_type_name']}): {r['total']} cars"
                    for r in results["brand_top_features"]
                ]
                context_parts.append(f"[{brand.upper()} TOP FEATURES]\n" + "\n".join(lines))
        else:
            if results.get("price_stats") and isinstance(results["price_stats"], list):
                stats = results["price_stats"][0] if results["price_stats"] else {}
                context_parts.append(
                    f"[INVENTORY OVERVIEW]\n"
                    f"Total cars: {stats.get('total_cars', 'N/A')}\n"
                    f"Price range: ${stats.get('min_price', 0):,.0f} - ${stats.get('max_price', 0):,.0f}\n"
                    f"Average price: ${stats.get('avg_price', 0):,.0f}"
                )

            if results.get("brand_counts") and isinstance(results["brand_counts"], list):
                lines = [f"  {r['brand']}: {r['total']} listings" for r in results["brand_counts"]]
                context_parts.append(f"[TOP BRANDS BY LISTINGS]\n" + "\n".join(lines))

            if results.get("fuel_type_counts") and isinstance(results["fuel_type_counts"], list):
                lines = [f"  {r['fuel_type']}: {r['total']}" for r in results["fuel_type_counts"]]
                context_parts.append(f"[FUEL TYPE DISTRIBUTION]\n" + "\n".join(lines))

            if results.get("top_features") and isinstance(results["top_features"], list):
                lines = [f"  {r['feature_name']}: {r['total']} cars" for r in results["top_features"]]
                context_parts.append(f"[MOST COMMON FEATURES]\n" + "\n".join(lines))

            if results.get("top_models") and isinstance(results["top_models"], list):
                lines = []
                for r in results["top_models"]:
                    rating = f"Rating: {r['car_rating']}/5" if r.get('car_rating') else ""
                    lines.append(f"  {r['car_name']} - avg ${r.get('price_avg', 0):,.0f} {rating}")
                context_parts.append(f"[TOP RATED MODELS]\n" + "\n".join(lines))

            if results.get("model_counts") and isinstance(results["model_counts"], list):
                lines = []
                for r in results["model_counts"]:
                    rating = f"Rating: {r['car_rating']}/5" if r.get('car_rating') else ""
                    lines.append(
                        f"  {r['car_name']} ({r['brand']}) - "
                        f"{r['total_listings']} listings, avg ${r.get('avg_price', 0):,.0f} {rating}"
                    )
                context_parts.append(f"[TOP MODELS BY LISTINGS]\n" + "\n".join(lines))

        context = "\n\n".join(context_parts)
        print(f"[ANALYTICS] brand={brand} model={model} keys={list(results.keys())}")
        return {"context": context, "messages": []}

    def analytics_answer(state: AgenticState):
        system_prompt = """You are a helpful car platform assistant providing website statistics.

Use ONLY the provided analytics context to answer the customer's question.
1. Present data clearly with numbers and rankings.
2. Highlight interesting insights (e.g. dominant brand, price trends, popular fuel types).
3. If the user asks something specific, focus on that metric.
4. If data is not available for their exact question, share the closest relevant stats.
5. Keep it concise and informative.
Reply in the same language the customer is using.
"""
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("system", "Platform Analytics Data:\n{context}"),
                MessagesPlaceholder("chat_history"),
                ("human", "{question}"),
            ]
        )
        chain = prompt | llm | StrOutputParser()
        answer = chain.invoke(
            {
                "context": state.get("context", ""),
                "chat_history": state["messages"],
                "question": state["question"],
            }
        )
        print(f"[ANALYTICS ANSWER] answer={answer!r}")
        return {"answer": answer}

    def compare_retrieve(state: AgenticState):
        extractor = llm.with_structured_output(CompareExtraction)
        extract_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Extract ALL cars the user wants to compare. "
                    "Return each car with its brand, model name, and year (if mentioned).",
                ),
                MessagesPlaceholder("chat_history"),
                ("human", "{question}"),
            ]
        )
        extraction = (extract_prompt | extractor).invoke(
            {"chat_history": state["messages"], "question": state["question"]}
        )

        if not extraction.cars or len(extraction.cars) < 2:
            return {
                "context": "Could not identify at least 2 cars to compare.",
                "messages": [],
            }

        compare_parts = []
        not_found = []

        for car in extraction.cars:
            constraints = CarConstraints(year=car.year) if car.year else None
            rows = sql_search_cars(
                brand=car.brand, model=car.model,
                constraints=constraints, limit=1,
            )

            if not rows:
                label = f"{car.year} {car.brand} {car.model}" if car.year else f"{car.brand} {car.model}"
                not_found.append(label)
                continue

            row = rows[0]
            vin = row.get("VIN") or "N/A"

            price_stats = get_avg_price(brand=car.brand, model=car.model)
            listing_price = row.get("price") or 0

            avg_price = price_stats.get("avg_price") or listing_price
            min_price = price_stats.get("min_price") or listing_price
            max_price = price_stats.get("max_price") or listing_price
            total_listings = price_stats.get("total") or 1

            features = get_feature(vin)
            if features:
                feature_str = "\n".join(
                    f"    - {f_type}: {', '.join(f_names)}"
                    for f_type, f_names in features.items()
                )
            else:
                feature_str = "    - No feature data"

            images = get_image_urls(vin, 2)
            img_str = "\n".join(f"    - {u}" for u in images) or "    - No images"

            compare_parts.append(
                f"=== {car.brand.upper()} {car.model.upper()} ===\n"
                f"  Title: {row.get('title') or 'N/A'}\n"
                f"  Status: {row.get('status') or 'N/A'}\n"
                f"  Average Price: ${avg_price:,.0f} (range: ${min_price:,.0f} - ${max_price:,.0f})\n"
                f"  Total Listings: {total_listings}\n"
                f"  Mileage: {row.get('mileage') or 'N/A'}\n"
                f"  Engine: {row.get('engine') or 'N/A'}\n"
                f"  Drivetrain: {row.get('drivetrain') or 'N/A'}\n"
                f"  Fuel Type: {row.get('fuel_type') or 'N/A'}\n"
                f"  Transmission: {row.get('transmission') or 'N/A'}\n"
                f"  MPG: {row.get('mpg') or 'N/A'}\n"
                f"  Exterior: {row.get('exterior_color') or 'N/A'}\n"
                f"  Interior: {row.get('interior_color') or 'N/A'}\n"
                f"  Post Link: {row.get('post_link') or 'N/A'}\n"
                f"  Features:\n{feature_str}\n"
                f"  Images:\n{img_str}"
            )

        context = "\n\n".join(compare_parts)
        if not_found:
            context += (
                f"\n\n[NOT FOUND]\n"
                f"The following cars are not available in our database:\n"
                + "\n".join(f"  - {name}" for name in not_found)
            )

        print(f"[COMPARE] found={len(compare_parts)} not_found={not_found}")
        print(f"[COMPARE CONTEXT]\n{context}")
        return {"context": context, "messages": []}

    def compare_answer(state: AgenticState):
        system_prompt = """You are an expert car comparison advisor.

IMPORTANT: The "Comparison Data" below contains REAL data retrieved from our database.
You MUST use this data to create a comparison. NEVER say "I don't have information"
if the data section contains car entries (=== BRAND MODEL ===).

Instructions:
1. For EACH car in the data (=== BRAND MODEL ===), present a side-by-side comparison:
   Price, Engine, Drivetrain, Fuel Type, MPG, Transmission, Features.
2. Highlight key differences and advantages of each car.
3. Give a brief verdict: which car suits what type of buyer.
4. Include [View Details](post_link) when a link is available.
5. ONLY apologize for missing data if there is a [NOT FOUND] section at the end.
Reply in the same language the customer is using.
"""
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("system", "Comparison Data:\n{context}"),
                MessagesPlaceholder("chat_history"),
                ("human", "{question}"),
            ]
        )
        chain = prompt | llm | StrOutputParser()
        answer = chain.invoke(
            {
                "context": state.get("context", ""),
                "chat_history": state["messages"],
                "question": state["question"],
            }
        )
        print(f"[COMPARE ANSWER] answer={answer!r}")
        return {"answer": answer}

    def redirect_topic(state: AgenticState):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a friendly car sales consultant. The customer just said "
                    "something unrelated to cars or vehicle shopping.\n"
                    "Politely acknowledge what they said in one short sentence, then "
                    "naturally redirect the conversation back to cars.\n"
                    "Suggest something helpful like: asking about their car needs, "
                    "budget, preferred brand, or if they want to explore what's available.\n"
                    "Keep it warm, not pushy. Reply in the same language the customer is using.",
                ),
                MessagesPlaceholder("chat_history"),
                ("human", "{question}"),
            ]
        )
        chain = prompt | llm | StrOutputParser()
        answer = chain.invoke(
            {
                "chat_history": state["messages"],
                "question": state["question"],
            }
        )
        print(f"[REDIRECT] off_topic -> redirecting user back to cars")
        return {"answer": answer}

    def route_after_intent(state: AgenticState):
        intent = state.get("intent")
        if intent == "compare":
            return "compare_retrieve"
        if intent == "analytics":
            return "analytics_retrieve"
        if intent == "specs":
            return "spec_retrieve"
        if intent == "specific":
            return "hybrid_retrieve"
        if intent == "vague":
            return "hybrid_retrieve" if _core_complete(state["profile"]) else "ask_slot"
        if intent == "off_topic":
            return "redirect_topic"
        return "consult"

    graph = StateGraph(AgenticState)
    graph.add_node("update_profile", update_profile)
    graph.add_node("route_intent", route_intent)
    graph.add_node("ask_slot", ask_slot)
    graph.add_node("compare_retrieve", compare_retrieve)
    graph.add_node("compare_answer", compare_answer)
    graph.add_node("analytics_retrieve", analytics_retrieve)
    graph.add_node("analytics_answer", analytics_answer)
    graph.add_node("spec_retrieve", spec_retrieve)
    graph.add_node("spec_answer", spec_answer)
    graph.add_node("hybrid_retrieve", hybrid_retrieve)
    graph.add_node("consult", consult)
    graph.add_node("redirect_topic", redirect_topic)

    graph.set_entry_point("update_profile")
    graph.add_edge("update_profile", "route_intent")
    graph.add_conditional_edges(
        "route_intent",
        route_after_intent,
        {
            "compare_retrieve": "compare_retrieve",
            "analytics_retrieve": "analytics_retrieve",
            "spec_retrieve": "spec_retrieve",
            "hybrid_retrieve": "hybrid_retrieve",
            "ask_slot": "ask_slot",
            "consult": "consult",
            "redirect_topic": "redirect_topic",
        },
    )
    graph.add_edge("compare_retrieve", "compare_answer")
    graph.add_edge("compare_answer", END)
    graph.add_edge("analytics_retrieve", "analytics_answer")
    graph.add_edge("analytics_answer", END)
    graph.add_edge("spec_retrieve", "spec_answer")
    graph.add_edge("spec_answer", END)
    graph.add_edge("ask_slot", END)
    graph.add_edge("redirect_topic", END)
    graph.add_edge("hybrid_retrieve", "consult")
    graph.add_edge("consult", END)
    return graph.compile()


_AGENTIC_APP = None


# --- Initialize LLM + Vector Store ---
def initialize_resources():
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding=embeddings,
    )

    global _AGENTIC_APP
    _AGENTIC_APP = _build_agentic_app(llm, vector_store)
    return llm, vector_store


# --- THE MAIN API FUNCTION USED BY STREAMLIT ---
def generate_response(llm, vector_store, chat_history_buffer, user_input, session_id="default"):
    """
    Returns (response_text, updated_chat_history_buffer)
    """

    global _AGENTIC_APP
    if _AGENTIC_APP is None:
        _AGENTIC_APP = _build_agentic_app(llm, vector_store)

    # 1. Normalize to standalone query
    search_query = get_standalone_question(llm, chat_history_buffer, user_input)

    # 2. Load persistent profile and run the consultation graph
    profile = load_profile(session_id)
    graph_state = _AGENTIC_APP.invoke(
        {
            "messages": chat_history_buffer,
            "question": user_input,
            "query": search_query,
            "context": "",
            "answer": "",
            "intent": "vague",
            "brand": None,
            "model": None,
            "session_id": session_id,
            "profile": profile.model_dump(),
        }
    )
    final_answer = graph_state.get("answer", "I could not generate a response right now.")

    # 3. Persist the updated profile
    updated_profile = graph_state.get("profile")
    if updated_profile:
        save_profile(session_id, UserProfile(**updated_profile))

    # 4. Update history (preserve existing session behavior)
    chat_history_buffer.append(HumanMessage(content=user_input))
    chat_history_buffer.append(AIMessage(content=final_answer))

    # Limit memory
    chat_history_buffer = chat_history_buffer[-10:]
   
    return final_answer, chat_history_buffer
