"""
AI tool definitions and handlers.

Two phases where the AI uses tools:
  - Synthesis: processes new highlights → creates concepts + edges
  - Review:    selects due concepts, evaluates answers, records results
"""

import uuid
from datetime import datetime
from typing import Any
from notemaster.db import Database, _initial_weight
from notemaster.models import Concept, ConceptEdge, RelationType, Highlight


# ---------------------------------------------------------------------------
# Tool JSON schemas (passed to the LLM as `tools=`)
# ---------------------------------------------------------------------------

SYNTHESIS_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_highlights",
            "description": (
                "List highlights for a book. Use unprocessed_only=true to see "
                "highlights not yet assigned to any concept."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {"type": "string", "description": "Filter by book ID"},
                    "unprocessed_only": {
                        "type": "boolean",
                        "description": "Return only highlights with no concept yet",
                        "default": False,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_concepts",
            "description": "List existing concepts, optionally filtered by book.",
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {"type": "string", "description": "Filter by book ID"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_concept",
            "description": (
                "Create a new concept node in the knowledge graph from one or more highlights. "
                "Initial weight is computed automatically from the highlights' colors."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short, precise name for the concept (e.g. 'Attention Mechanism')",
                    },
                    "summary": {
                        "type": "string",
                        "description": (
                            "Complete explanation of the concept. Should go beyond the raw "
                            "highlight text and fill in any missing context."
                        ),
                    },
                    "highlight_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of highlights that belong to this concept",
                    },
                    "book_id": {"type": "string", "description": "ID of the source book"},
                    "questions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "3 varied review questions about this concept — "
                            "different angles: definition, example, trade-off, contrast, application."
                        ),
                    },
                },
                "required": ["title", "summary", "highlight_ids", "book_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_concept",
            "description": (
                "Update an existing concept: refine its summary, rename it, or add more highlights. "
                "Adding highlights recalculates the concept's weight."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "concept_id": {"type": "string"},
                    "title": {"type": "string", "description": "New title (optional)"},
                    "summary": {"type": "string", "description": "Updated summary (optional)"},
                    "add_highlight_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Additional highlight IDs to associate (optional)",
                    },
                },
                "required": ["concept_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "link_concepts",
            "description": (
                "Create a directed edge between two concepts in the knowledge graph. "
                "Relation types: depends_on, contrasts_with, part_of, example_of."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_concept_id": {"type": "string"},
                    "to_concept_id": {"type": "string"},
                    "relation": {
                        "type": "string",
                        "enum": ["depends_on", "contrasts_with", "part_of", "example_of"],
                        "description": (
                            "depends_on: from requires understanding of to; "
                            "contrasts_with: the two concepts differ in a meaningful way; "
                            "part_of: from is a component of to; "
                            "example_of: from is a concrete instance of to"
                        ),
                    },
                },
                "required": ["from_concept_id", "to_concept_id", "relation"],
            },
        },
    },
]

REVIEW_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_due_concepts",
            "description": (
                "Return concepts due for review, sorted by priority "
                "(weight × days_overdue). Higher weight and more overdue = higher priority."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of concepts to return (default 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_concept",
            "description": (
                "Retrieve full details of a concept including its highlights and graph edges. "
                "Use this before presenting a concept for review."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "concept_id": {"type": "string"},
                },
                "required": ["concept_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_review",
            "description": (
                "Record the result of a review session for a concept. "
                "Updates the concept's weight and schedules the next review via SM-2. "
                "mastery_score: 1=no recall, 2=hard, 3=okay, 4=good, 5=perfect."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "concept_id": {"type": "string"},
                    "mastery_score": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "description": "1–5 mastery rating from the review",
                    },
                },
                "required": ["concept_id", "mastery_score"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers (called when the LLM emits a tool_call)
# ---------------------------------------------------------------------------

class ToolHandler:
    def __init__(self, db: Database):
        self.db = db

    def dispatch(self, name: str, args: dict[str, Any]) -> Any:
        handler = getattr(self, f"handle_{name}", None)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        return handler(**args)

    # --- Synthesis handlers ---

    def handle_list_highlights(
        self, book_id: str | None = None, unprocessed_only: bool = False
    ) -> list[dict]:
        highlights = self.db.get_highlights(book_id=book_id, unprocessed_only=unprocessed_only)
        return [_highlight_to_dict(h) for h in highlights]

    def handle_list_concepts(self, book_id: str | None = None) -> list[dict]:
        concepts = self.db.get_concepts(book_id=book_id)
        return [_concept_to_dict(c) for c in concepts]

    def handle_create_concept(
        self,
        title: str,
        summary: str,
        highlight_ids: list[str],
        book_id: str,
        questions: list[str] | None = None,
    ) -> dict:
        highlights = self.db.get_highlights(book_id=book_id)
        color_map = {h.id: h.color.value for h in highlights}
        colors = [color_map[hid] for hid in highlight_ids if hid in color_map]
        weight = _initial_weight(colors)

        now = datetime.now()
        concept = Concept(
            id=str(uuid.uuid4()),
            title=title,
            summary=summary,
            book_id=book_id,
            highlight_ids=highlight_ids,
            weight=weight,
            questions=questions or [],
            created_at=now,
            updated_at=now,
        )
        self.db.create_concept(concept)
        return _concept_to_dict(concept)

    def handle_update_concept(
        self,
        concept_id: str,
        title: str | None = None,
        summary: str | None = None,
        add_highlight_ids: list[str] | None = None,
    ) -> dict | None:
        concept = self.db.update_concept(
            concept_id,
            title=title,
            summary=summary,
            add_highlight_ids=add_highlight_ids,
        )
        return _concept_to_dict(concept) if concept else None

    def handle_link_concepts(
        self,
        from_concept_id: str,
        to_concept_id: str,
        relation: str,
    ) -> dict:
        edge = ConceptEdge(
            from_concept_id=from_concept_id,
            to_concept_id=to_concept_id,
            relation=RelationType(relation),
        )
        self.db.create_edge(edge)
        return {"from": from_concept_id, "to": to_concept_id, "relation": relation}

    # --- Review handlers ---

    def handle_get_due_concepts(self, limit: int = 20) -> list[dict]:
        items = self.db.get_due_concepts(limit=limit)
        return [
            {
                "concept": _concept_to_dict(item.concept),
                "priority": round(item.priority, 3),
                "days_overdue": round(item.days_overdue, 1),
                "last_mastery": item.last_mastery,
            }
            for item in items
        ]

    def handle_get_concept(self, concept_id: str) -> dict | None:
        concept = self.db.get_concept(concept_id)
        if concept is None:
            return None

        highlights = self.db.get_highlights(book_id=concept.book_id)
        h_map = {h.id: h for h in highlights}
        concept_highlights = [
            _highlight_to_dict(h_map[hid])
            for hid in concept.highlight_ids
            if hid in h_map
        ]
        edges = self.db.get_edges(concept_id=concept_id)

        return {
            **_concept_to_dict(concept),
            "highlights": concept_highlights,
            "edges": [
                {
                    "from": e.from_concept_id,
                    "to": e.to_concept_id,
                    "relation": e.relation.value,
                }
                for e in edges
            ],
        }

    def handle_record_review(self, concept_id: str, mastery_score: int) -> dict:
        record = self.db.record_review(concept_id, mastery_score)
        concept = self.db.get_concept(concept_id)
        return {
            "concept_id": concept_id,
            "mastery_score": mastery_score,
            "new_weight": round(concept.weight, 3) if concept else None,
            "next_review_at": record.next_review_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _highlight_to_dict(h: Highlight) -> dict:
    return {
        "id": h.id,
        "text": h.text,
        "color": h.color.value,
        "book_id": h.book_id,
        "book_title": h.book_title,
        "chapter": h.chapter,
    }


def _concept_to_dict(c: Concept) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "summary": c.summary,
        "book_id": c.book_id,
        "highlight_ids": c.highlight_ids,
        "weight": round(c.weight, 3),
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }
