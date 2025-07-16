import os, json, logging, datetime
from typing import List, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from ddgs import DDGS
from dateutil.parser import parse as dt_parse
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

# ───────────────────────────
# 1. ENV & LOGGING
# ───────────────────────────
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
NEWS_MAX_RESULTS = int(os.getenv("NEWS_MAX_RESULTS", "8"))
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY missing (see .env)")

logger = logging.getLogger("chatbot")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
logger.addHandler(handler)
logger.debug("Environment and logging configured")

# ───────────────────────────
# 2. FASTAPI APP & CORS CONFIGURATION
# ───────────────────────────
app = FastAPI(title="Chat-Duck-LLM")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.debug("FastAPI app and CORS configured")

# ───────────────────────────
# 3. OPENROUTER CLIENT
# ───────────────────────────
class OpenRouterClient:
    """Wrapper around OpenRouter chat completions with exponential back‑off."""

    def __init__(self, model_id: str = "qwen/qwen2.5-vl-32b-instruct:free") -> None:
        self.model = model_id
        self.url = f"{OPENROUTER_BASE}/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://your-domain.com",
            "X-Title": "Chat-Duck-LLM",
        }
        logger.debug(f"OpenRouterClient initialized with model {self.model}")

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
    )
    async def chat(self, messages: List[Dict[str, str]]) -> str:
        logger.info("LLM request: sending messages to OpenRouter")
        logger.debug(f"Payload to LLM: {json.dumps(messages, ensure_ascii=False)}")
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(
                self.url,
                headers=self.headers,
                json={"model": self.model, "messages": messages, "stream": False},
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            logger.info("LLM response received")
            logger.debug(f"LLM output: {content}")
            return content


llm_client = OpenRouterClient()

# ───────────────────────────
# 4. FREE NEWS SEARCH TOOL (DuckDuckGo)
# ───────────────────────────
ONE_WEEK_AGO = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)


def _parse_date(raw: str | None):
    if not raw:
        return None
    try:
        return dt_parse(raw)
    except Exception:
        return None


def _link(hit: Dict[str, Any]) -> str:
    """Return best‐effort link key (href or url) or placeholder."""
    return hit.get("href") or hit.get("url") or "(lien indisponible)"


def search_recent_news(query: str, max_results: int = NEWS_MAX_RESULTS) -> List[Dict[str, str]]:
    logger.info(f"Search node: querying DDG‑news for '{query}' (max {max_results})")
    with DDGS() as ddgs:
        hits = list(
            ddgs.news(
                query,
                region="fr-fr",
                safesearch="Moderate",
                timelimit="w",
                max_results=max_results,
            )
        )

    fresh_hits: List[Dict[str, str]] = []
    for hit in hits:
        hit_date = _parse_date(hit.get("date"))
        if hit_date:
            if hit_date.tzinfo is None:
                hit_date = hit_date.replace(tzinfo=datetime.timezone.utc)
            else:
                hit_date = hit_date.astimezone(datetime.timezone.utc)
        if hit_date and hit_date >= ONE_WEEK_AGO:
            fresh_hits.append(hit)

    logger.info(f"Search node: DDG‑news returned {len(fresh_hits)} fresh results")

    if not fresh_hits:
        logger.warning("No fresh news via DDG‑news; falling back to DDG.text")
        with DDGS() as ddgs:
            text_hits = list(
                ddgs.text(
                    f"{query} past week",
                    region="fr-fr",
                    safesearch="Moderate",
                    max_results=max_results,
                )
            )
        fresh_hits.extend(text_hits)
        logger.info(f"Fallback DDG.text yielded {len(fresh_hits)} hits")

    for i, hit in enumerate(fresh_hits, 1):
        logger.debug(
            f"Search result {i}: title={hit['title']}, link={_link(hit)}, date={hit.get('date')}"
        )
    return fresh_hits[:max_results]

# ───────────────────────────
# 5. LANGGRAPH NODES & STATE
# ───────────────────────────
class ChatState(TypedDict):
    messages: List[Dict[str, str]]

SYSTEM_PROMPT = (
    "Vous êtes un assistant IA francophone. Votre réponse **doit se baser exclusivement** sur les "
    "informations fournies dans les blocs [WEB] qui précèdent. Si les informations sont insuffisantes "
    "pour répondre correctement, dites : ‘Information insuffisante dans les sources web fournies.’ "
    "Citez vos sources en précisant le site ou le titre entre parenthèses."
)


def _strip_leading_assistant(msgs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    while msgs and msgs[0]["role"] == "assistant":
        msgs.pop(0)
    return msgs


def run_search(state: ChatState) -> ChatState:
    logger.info("Node 'search': start")
    last_user = next((m for m in reversed(state["messages"]) if m["role"] == "user"), None)
    if not last_user:
        logger.warning("No user message found; skipping search")
        return state

    hits = search_recent_news(last_user["content"])
    if not hits:
        snippet = "Aucun résultat web pertinent dans la dernière semaine."
    else:
        snippet = "\n".join(
            f"- {h['title']} ({_link(h)})" + (f" – {h.get('date')[:10]}" if h.get('date') else "")
            for h in hits
        )
    state["messages"].append(
        {"role": "system", "content": f"[WEB] Résultats de recherche récents:\n{snippet}"}
    )
    logger.info("Node 'search': end")
    return state


async def run_llm(state: ChatState) -> ChatState:
    logger.info("Node 'llm': start")
    history = _strip_leading_assistant(state["messages"].copy())
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-12:]
    reply = await llm_client.chat(messages)
    state["messages"].append({"role": "assistant", "content": reply})
    logger.info("Node 'llm': end")
    return state


graph = StateGraph(ChatState)
graph.add_node("search", run_search)
graph.add_node("llm", run_llm)
graph.set_entry_point("search")
graph.add_edge("search", "llm")
graph.add_edge("llm", END)
executor = graph.compile()
logger.debug("LangGraph executor compiled")

# ───────────────────────────
# 6. API ROUTES
# ───────────────────────────
@app.post("/chat")
async def chat_route(payload: Dict[str, Any]):
    logger.info("HTTP /chat received")
    if "messages" not in payload:
        raise HTTPException(status_code=422, detail="messages field required")
    initial_state: ChatState = {"messages": payload["messages"].copy()}
    final_state = await executor.ainvoke(initial_state)
    return {"messages": final_state["messages"]}
