"""Pokedex RAG server — a standalone service that loads Pokemon data into
ChromaDB and answers questions using retrieval-augmented generation with Gemini.

All ChromaDB and Gemini calls are auto-instrumented by OpenLit and exported
to Oodle via the OpenTelemetry Collector.
"""

import os
from pathlib import Path

import chromadb
import openlit
import pandas as pd
from flask import Flask, jsonify, request
from google import genai
from google.genai import types
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor

app = Flask(__name__)
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

openlit.init(
    otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"),
    application_name="pokedex-rag",
)
FlaskInstrumentor().instrument_app(app)

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
tracer = trace.get_tracer("pokedex-rag")


# ---------------------------------------------------------------------------
# ChromaDB setup — load Pokemon dataset into a vector collection
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
CSV_PATH = DATA_DIR / "pokemon_complete.csv"

chroma_client = chromadb.Client()
pokedex_collection = chroma_client.create_collection(name="pokedex")


def _load_pokemon_data(csv_path: Path) -> list[dict]:
    """Parse the Pokemon CSV into documents suitable for vector search.

    Each Pokemon becomes a rich text document combining its name, types, stats,
    abilities, physical attributes, and flavor text so that semantic search
    can find relevant Pokemon for any natural-language query.
    """
    df = pd.read_csv(csv_path)

    docs = []
    for _, row in df.iterrows():
        name = row["name"]
        type1 = row["type_1"]
        type2 = row["type_2"]
        types_str = f"{type1}/{type2}" if pd.notna(type2) else str(type1)

        legendary_str = ""
        if row.get("is_legendary") is True or str(row.get("is_legendary")).lower() == "true":
            legendary_str = " It is a legendary Pokemon."
        elif row.get("is_mythical") is True or str(row.get("is_mythical")).lower() == "true":
            legendary_str = " It is a mythical Pokemon."

        abilities = row.get("abilities", "")
        abilities_str = f" Abilities: {abilities}." if pd.notna(abilities) else ""

        flavor = row.get("flavor_text", "")
        flavor_str = f" {flavor}" if pd.notna(flavor) else ""

        height = row.get("height_m", "")
        weight = row.get("weight_kg", "")
        size_str = ""
        if pd.notna(height) and pd.notna(weight):
            size_str = f" Height: {height}m, Weight: {weight}kg."

        text = (
            f"{name} (#{row['pokedex_number']}) is a {types_str}-type Pokemon "
            f"from {row['generation']}. "
            f"Stats: HP {row['hp']}, Attack {row['attack']}, Defense {row['defense']}, "
            f"Sp. Atk {row['sp_attack']}, Sp. Def {row['sp_defense']}, Speed {row['speed']} "
            f"(Total: {row['base_stat_total']}).{size_str}{abilities_str}{legendary_str}{flavor_str}"
        )

        doc_id = f"{row['pokedex_number']}-{str(name).lower().replace(' ', '-')}"
        docs.append({"id": doc_id, "text": text})

    return docs


print("Loading Pokemon dataset into ChromaDB...")
pokemon_docs = _load_pokemon_data(CSV_PATH)

pokedex_collection.add(
    ids=[doc["id"] for doc in pokemon_docs],
    documents=[doc["text"] for doc in pokemon_docs],
)
print(f"Loaded {len(pokemon_docs)} Pokemon into the Pokedex collection.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_content(text: str) -> list[types.Content]:
    return [types.Content(role="user", parts=[types.Part(text=text)])]


def _gemini_call(model: str, contents: list[types.Content], system_instruction: str) -> str:
    with tracer.start_as_current_span(f"rag {model}", kind=trace.SpanKind.CLIENT) as span:
        span.set_attribute("gen_ai.system", "gemini")
        span.set_attribute("gen_ai.request.model", model)
        span.set_attribute("gen_ai.operation.name", "rag")
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config={"system_instruction": system_instruction},
        )
        return response.text


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a Pokedex assistant. Answer questions about Pokemon using ONLY "
    "the provided context from the Pokedex database. Include relevant stats "
    "and type information. If the context doesn't contain enough information, say so."
)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "pokedex-rag", "pokemon_count": len(pokemon_docs)})


@app.route("/query", methods=["POST"])
def query():
    """Ask the Pokedex a question.

    Request body: {"query": "Which fire-type Pokemon has the highest attack?", "n_results": 5}
    """
    body = request.get_json(force=True)
    user_query = body.get("query", "")
    n_results = body.get("n_results", 5)

    if not user_query:
        return jsonify({"error": "query is required"}), 400

    results = pokedex_collection.query(query_texts=[user_query], n_results=n_results)
    documents = results["documents"][0] if results["documents"] else []
    doc_ids = results["ids"][0] if results["ids"] else []

    context = "\n\n".join(documents)
    prompt = (
        f"Answer the following question using ONLY the provided Pokedex data.\n\n"
        f"Pokedex Data:\n{context}\n\n"
        f"Question: {user_query}"
    )

    try:
        answer = _gemini_call(DEFAULT_MODEL, _user_content(prompt), SYSTEM_PROMPT)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    return jsonify({
        "answer": answer,
        "sources": doc_ids,
        "context_documents": documents,
    })


@app.route("/search", methods=["POST"])
def search():
    """Search the Pokedex without LLM synthesis — returns raw vector matches.

    Request body: {"query": "water type legendary", "n_results": 5}
    """
    body = request.get_json(force=True)
    user_query = body.get("query", "")
    n_results = body.get("n_results", 5)

    if not user_query:
        return jsonify({"error": "query is required"}), 400

    results = pokedex_collection.query(query_texts=[user_query], n_results=n_results)
    documents = results["documents"][0] if results["documents"] else []
    doc_ids = results["ids"][0] if results["ids"] else []

    return jsonify({"results": [{"id": id_, "text": doc} for id_, doc in zip(doc_ids, documents)]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8091"))
    app.run(host="0.0.0.0", port=port)
