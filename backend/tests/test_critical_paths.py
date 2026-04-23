"""
Critical-path tests covering the bugs fixed in this session.

Organised by subsystem:
  1. Hybrid retrieval — normalization, domain gate, abstention
  2. Vector store     — partial-embedding safety, parallel embed, count verify
  3. QA agent         — MC no-context guard, stem-only retrieval
  4. Documents route  — raw_text saved before chunking, N+1 fix, has_summary
  5. Vision fallback  — truncation logging
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# 1. Hybrid retrieval
# ---------------------------------------------------------------------------

from app.services.hybrid_qa_retrieval import (
    _normalize_scores,
    _lexical_score,
    _distance_to_sim,
    domain_terms_in_question,
    hybrid_retrieve_for_qa,
    ABSTAIN_MESSAGE_HE,
)


class TestNormalizeScores:
    def test_all_zeros_returns_zeros(self):
        """FIX: all-zero lexical scores must NOT become 1.0 (old bug gave every
        vector candidate a free +0.52 lexical bonus)."""
        result = _normalize_scores([0.0, 0.0, 0.0])
        assert result == [0.0, 0.0, 0.0]

    def test_empty_input_returns_empty(self):
        assert _normalize_scores([]) == []

    def test_mixed_values_normalized_to_unit_range(self):
        result = _normalize_scores([0.0, 2.0, 4.0])
        assert result[0] == pytest.approx(0.0)
        assert result[1] == pytest.approx(0.5)
        assert result[2] == pytest.approx(1.0)

    def test_single_nonzero_becomes_zero(self):
        # hi == lo (all same value, but non-zero) → all get 0.0
        result = _normalize_scores([3.0, 3.0])
        assert result == [0.0, 0.0]


class TestLexicalScore:
    def test_phrase_match_outscores_token_match(self):
        tokens = {"דירקטוריון", "סמכויות"}
        phrases = ["דירקטוריון"]
        high = _lexical_score("סמכויות הדירקטוריון כוללות...", tokens, phrases)
        low = _lexical_score("מנהל כללי ועובדים", tokens, phrases)
        assert high > low

    def test_zero_score_for_no_match(self):
        score = _lexical_score("תוכן לא רלוונטי בכלל", {"דירקטוריון"}, [])
        assert score == 0.0

    def test_empty_text_returns_zero(self):
        assert _lexical_score("", {"token"}, ["phrase"]) == 0.0


class TestDistanceToSim:
    def test_zero_distance_is_one(self):
        assert _distance_to_sim(0.0) == pytest.approx(1.0)

    def test_large_distance_approaches_zero(self):
        assert _distance_to_sim(999.0) < 0.01

    def test_none_distance_returns_default(self):
        assert _distance_to_sim(None) == pytest.approx(0.5)


class TestDomainTermsInQuestion:
    def test_no_terms_when_gate_disabled(self, monkeypatch):
        """Domain gate is off by default (DOMAIN_GATE_ENABLED not set)."""
        import app.services.hybrid_qa_retrieval as mod
        monkeypatch.setattr(mod, "_DOMAIN_GATE_ENABLED", False)
        assert domain_terms_in_question("מה סמכויות הדירקטוריון?") == []

    def test_terms_detected_when_gate_enabled(self, monkeypatch):
        import app.services.hybrid_qa_retrieval as mod
        monkeypatch.setattr(mod, "_DOMAIN_GATE_ENABLED", True)
        terms = domain_terms_in_question("מה סמכויות הדירקטוריון?")
        assert "דירקטוריון" in terms


class TestHybridRetrieveForQA:
    def test_no_chunks_anywhere_returns_abstain(self, mock_vector_store):
        chunks, abstain, reason = hybrid_retrieve_for_qa(
            mock_vector_store, "מה זה?", course_id="c1", lecture_id=None
        )
        assert abstain is True
        assert reason == "no_candidates"
        assert chunks == []

    def test_vec_exception_falls_back_gracefully(self, mock_vector_store):
        mock_vector_store.search_with_distances.side_effect = RuntimeError("chroma down")
        chunks, abstain, reason = hybrid_retrieve_for_qa(
            mock_vector_store, "מה זה?", course_id="c1", lecture_id=None
        )
        assert abstain is True  # no candidates from either path
        assert chunks == []

    def test_good_chunks_returned_without_abstain(self, mock_vector_store):
        mock_vector_store.search_with_distances.return_value = [
            {
                "text": "הדירקטוריון מפקח על המנכ\"ל ומאשר את התוכנית האסטרטגית.",
                "snippet": "הדירקטוריון מפקח",
                "document_id": "d1",
                "chunk_index": 0,
                "course_id": "c1",
                "lecture_id": None,
                "_distance": 0.15,
            }
        ]
        chunks, abstain, reason = hybrid_retrieve_for_qa(
            mock_vector_store, "מה תפקיד הדירקטוריון?", course_id="c1", lecture_id=None
        )
        assert abstain is False
        assert len(chunks) == 1
        assert chunks[0]["document_id"] == "d1"

    def test_lex_fetch_at_limit_warns(self, mock_vector_store, caplog):
        import logging
        # Return exactly _LEX_MAX_FETCH rows to trigger the warning.
        from app.services.hybrid_qa_retrieval import _LEX_MAX_FETCH
        rows = [
            {"text": f"chunk {i}", "metadata": {"course_id": "c1", "document_id": "d1",
                                                  "chunk_index": i, "lecture_id": None}}
            for i in range(_LEX_MAX_FETCH)
        ]
        mock_vector_store.fetch_chunks_for_scope.return_value = rows
        mock_vector_store.search_with_distances.return_value = []

        with caplog.at_level(logging.WARNING, logger="app.services.hybrid_qa_retrieval"):
            hybrid_retrieve_for_qa(mock_vector_store, "שאלה", course_id="c1", lecture_id=None)

        assert any("lex_fetch_at_limit" in r.message for r in caplog.records)

    def test_global_mode_skips_lexical(self, mock_vector_store):
        hybrid_retrieve_for_qa(
            mock_vector_store, "שאלה כלשהי", course_id=None, lecture_id=None
        )
        mock_vector_store.fetch_chunks_for_scope.assert_not_called()

    def test_return_scores_flag_preserves_internal_keys(self, mock_vector_store):
        mock_vector_store.search_with_distances.return_value = [
            {
                "text": "content",
                "snippet": "content",
                "document_id": "d1",
                "chunk_index": 0,
                "course_id": "c1",
                "lecture_id": None,
                "_distance": 0.2,
            }
        ]
        chunks, abstain, _ = hybrid_retrieve_for_qa(
            mock_vector_store, "question", course_id="c1", lecture_id=None,
            return_scores=True
        )
        assert not abstain
        assert "_rerank_score" in chunks[0]


# ---------------------------------------------------------------------------
# 2. Vector store
# ---------------------------------------------------------------------------

from app.services.vector_store import (
    VectorStoreService,
    EmbeddingError,
    VectorStoreWriteError,
    _EMBED_WORKERS,
    _EMBED_SINGLE_TIMEOUT_S,
)


class TestVectorStoreAddChunks:
    def _make_vs(self):
        with patch("app.services.vector_store.chromadb.PersistentClient"):
            vs = VectorStoreService()
        vs.collection = MagicMock()
        return vs

    def test_empty_chunks_returns_zero(self):
        vs = self._make_vs()
        result = vs.add_chunks("doc-1", "course-1", None, [])
        assert result == 0
        vs.collection.add.assert_not_called()

    def test_embed_failure_does_not_delete_existing_chunks(self):
        """
        FIX: if embedding fails, delete_by_document_id must NOT have been called
        (old bug deleted first, then failed to embed, leaving Chroma empty).
        """
        vs = self._make_vs()
        vs._embed_parallel = MagicMock(side_effect=EmbeddingError("ollama down"))
        vs.delete_by_document_id = MagicMock()

        with pytest.raises(EmbeddingError):
            vs.add_chunks("doc-1", "c1", None, ["chunk one", "chunk two"])

        vs.delete_by_document_id.assert_not_called()

    def test_write_failure_raises_vector_store_write_error(self):
        vs = self._make_vs()
        vs._embed_parallel = MagicMock(return_value=[[0.1, 0.2], [0.3, 0.4]])
        vs.delete_by_document_id = MagicMock()
        vs.collection.add.side_effect = RuntimeError("chroma write error")

        with pytest.raises(VectorStoreWriteError):
            vs.add_chunks("doc-1", "c1", None, ["a", "b"])

    def test_write_verification_raises_on_mismatch(self):
        vs = self._make_vs()
        vs._embed_parallel = MagicMock(return_value=[[0.1]])
        vs.delete_by_document_id = MagicMock()
        vs.collection.add = MagicMock()
        # Simulate Chroma reporting fewer chunks than written.
        vs.count_chunks_for_document = MagicMock(return_value=0)

        with pytest.raises(VectorStoreWriteError, match="Write verification failed"):
            vs.add_chunks("doc-1", "c1", None, ["only one chunk"])

    def test_successful_write_returns_chunk_count(self):
        vs = self._make_vs()
        vs._embed_parallel = MagicMock(return_value=[[0.1, 0.2], [0.3, 0.4]])
        vs.delete_by_document_id = MagicMock()
        vs.collection.add = MagicMock()
        vs.count_chunks_for_document = MagicMock(return_value=2)

        result = vs.add_chunks("doc-1", "c1", None, ["chunk a", "chunk b"])
        assert result == 2

    def test_delete_called_after_embed_not_before(self):
        """Verify embed → delete → write order."""
        call_order = []

        vs = self._make_vs()
        vs._embed_parallel = MagicMock(side_effect=lambda *a, **k: call_order.append("embed") or [[0.1]])
        vs.delete_by_document_id = MagicMock(side_effect=lambda *a: call_order.append("delete"))
        vs.collection.add = MagicMock(side_effect=lambda **k: call_order.append("write"))
        vs.count_chunks_for_document = MagicMock(return_value=1)

        vs.add_chunks("doc-1", "c1", None, ["one chunk"])
        assert call_order == ["embed", "delete", "write"]

    def test_fetch_at_limit_logs_warning(self, caplog):
        import logging
        vs = self._make_vs()
        # Return exactly `limit` rows.
        limit = 10
        vs.collection.get = MagicMock(return_value={
            "documents": [f"text {i}" for i in range(limit)],
            "metadatas": [{"course_id": "c1"} for _ in range(limit)],
        })
        with caplog.at_level(logging.WARNING, logger="app.services.vector_store"):
            vs.fetch_chunks_for_scope("c1", limit=limit)

        assert any("fetch_at_limit" in r.message for r in caplog.records)


class TestOllamaEmbeddingAPI:
    def _make_vs(self):
        with patch("app.services.vector_store.chromadb.PersistentClient"):
            vs = VectorStoreService()
        return vs

    def test_embed_once_uses_current_ollama_embed_endpoint_and_payload(self):
        vs = self._make_vs()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
        response.raise_for_status = MagicMock()

        with patch("app.services.vector_store.requests.post", return_value=response) as post:
            embedding = vs._embed_once("hello")

        assert embedding == [0.1, 0.2, 0.3]
        post.assert_called_once_with(
            "http://localhost:11434/api/embed",
            json={"model": "nomic-embed-text", "input": "hello"},
            timeout=_EMBED_SINGLE_TIMEOUT_S,
        )

    def test_parse_embedding_response_accepts_legacy_shape(self):
        vs = self._make_vs()
        assert vs._parse_embedding_response({"embedding": [0.4, 0.5]}) == [0.4, 0.5]

    def test_legacy_endpoint_env_logs_error_and_uses_current_endpoint(self, monkeypatch, caplog):
        import logging
        monkeypatch.setenv("OLLAMA_EMBEDDING_ENDPOINT", "/api/embeddings")

        with caplog.at_level(logging.ERROR, logger="app.services.vector_store"):
            vs = self._make_vs()

        assert vs.embedding_endpoint == "/api/embed"
        assert any("embedding_endpoint_legacy_configured" in r.message for r in caplog.records)

    def test_embed_once_logs_status_and_short_error_body(self, caplog):
        import logging
        vs = self._make_vs()
        response = MagicMock()
        response.status_code = 404
        response.text = "not found " * 80
        response.json.return_value = {}
        response.raise_for_status.side_effect = RuntimeError("404")

        with patch("app.services.vector_store.requests.post", return_value=response):
            with caplog.at_level(logging.INFO, logger="app.services.vector_store"):
                with pytest.raises(RuntimeError):
                    vs._embed_once("hello")

        assert any("status_code=404" in r.message for r in caplog.records)
        assert any("ollama.embedding_failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# 2b. Embedding concurrency and timeout budget
# ---------------------------------------------------------------------------

import app.services.vector_store as _vs_mod


class TestEmbedWorkerDefaults:
    def test_workers_default_to_one(self):
        """
        FIX: _EMBED_WORKERS must default to 1 so that CPU-only Ollama requests
        are sent serially.  Workers=4 with a single CPU runner creates a queue
        where chunk_3 waits behind chunk_0..2, easily exceeding a 60s stage
        timeout for 4-chunk documents.
        """
        assert _EMBED_WORKERS == 1, (
            f"Expected EMBED_WORKERS=1 (serial, safe for CPU Ollama), got {_EMBED_WORKERS}. "
            "Set EMBED_WORKERS env var to override for GPU/API backends."
        )

    def test_single_timeout_default_is_generous_for_cpu(self):
        """Per-request timeout must be large enough for cold-start CPU Ollama."""
        assert _EMBED_SINGLE_TIMEOUT_S >= 60, (
            f"Per-request timeout should be ≥60 s for CPU Ollama cold starts; got {_EMBED_SINGLE_TIMEOUT_S}"
        )


class TestEmbedNoStageTimeout:
    """
    Regression: embedding must NOT have a stage-level wall-clock timeout.
    The old design wrapped embed+write in _run_with_timeout(60s), which fired
    'Stage timeout: embedding exceeded 60s' for any file whose chunks took
    longer than 60s total — including valid small DOCX files on slow CPUs.

    The fix: call add_chunks directly with only per-request timeouts.
    """

    def _make_vs(self):
        with patch("app.services.vector_store.chromadb.PersistentClient"):
            vs = VectorStoreService()
        vs.collection = MagicMock()
        return vs

    def test_slow_embedding_succeeds_without_stage_timeout(self, tmp_path):
        """
        Simulate a slow-but-successful Ollama: each embed call sleeps briefly
        (representing real latency).  The document must finish as 'ready', not
        'failed' — proving there is no outer wall-clock timeout killing the stage.
        """
        import time as _time
        from app.routes.documents import _process_existing_document
        from app.models.document import Document
        from app.db.database import Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()

        f = tmp_path / "slow.txt"
        f.write_text("Hello world. " * 30)  # small file → few chunks

        doc = Document(
            id="slow-embed-test",
            course_id="c1",
            file_name="slow.txt",
            file_path=str(f),
            file_type="txt",
        )
        db.add(doc)
        db.commit()

        call_count = [0]

        def slow_embed(text, max_attempts=3, timeout_s=90):
            call_count[0] += 1
            _time.sleep(0.05)  # 50 ms simulates real latency per chunk
            return [0.1, 0.2, 0.3]

        with patch("app.routes.documents.VectorStoreService") as MockVS, \
             patch("app.routes.documents.SummaryAgent") as MockSA, \
             patch("app.routes.documents.CourseSummaryAgent"), \
             patch("app.routes.documents.KnowledgeMapAgent"), \
             patch("app.routes.documents._refresh_course_aggregates"):
            mock_vs_instance = MockVS.return_value
            mock_vs_instance.delete_by_document_id = MagicMock()
            mock_vs_instance._embed = MagicMock(side_effect=slow_embed)
            mock_vs_instance.add_chunks = MagicMock(return_value=3)
            MockSA.return_value.summarize.return_value = "summary"

            result = _process_existing_document(db, doc)

        assert result.get("processing_status") == "ready", (
            f"Document should be 'ready' after slow-but-successful embedding, got: {result}"
        )
        # No StageTimeoutError should have been raised
        db.close()

    def test_embedding_error_marks_document_failed(self, tmp_path):
        """
        A genuine EmbeddingError (all retries exhausted) must still mark the
        document as failed.  Removing the stage timeout must not swallow errors.
        """
        from app.routes.documents import _process_existing_document
        from app.models.document import Document
        from app.db.database import Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.services.vector_store import EmbeddingError

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()

        f = tmp_path / "err.txt"
        f.write_text("Test content for embedding failure.")

        doc = Document(
            id="embed-fail-test",
            course_id="c1",
            file_name="err.txt",
            file_path=str(f),
            file_type="txt",
        )
        db.add(doc)
        db.commit()

        with patch("app.routes.documents.VectorStoreService") as MockVS, \
             patch("app.routes.documents.SummaryAgent"):
            mock_vs_instance = MockVS.return_value
            mock_vs_instance.delete_by_document_id = MagicMock()
            mock_vs_instance.add_chunks.side_effect = EmbeddingError("ollama unreachable")

            from app.routes.documents import ProcessingStageError
            with pytest.raises(ProcessingStageError) as exc_info:
                _process_existing_document(db, doc)

        assert exc_info.value.stage == "embedding"
        assert exc_info.value.retriable is True
        db.close()


class TestEmbedProgressLogging:
    def _make_vs(self):
        with patch("app.services.vector_store.chromadb.PersistentClient"):
            vs = VectorStoreService()
        return vs

    def test_progress_logged_per_chunk(self, caplog):
        """_embed_parallel must log progress after each chunk completes."""
        import logging
        vs = self._make_vs()

        def fake_embed(text, max_attempts=3, timeout_s=30):
            return [0.1, 0.2, 0.3]

        vs._embed = MagicMock(side_effect=fake_embed)

        with caplog.at_level(logging.INFO, logger="app.services.vector_store"):
            vs._embed_parallel(["chunk a", "chunk b", "chunk c"])

        progress_logs = [r for r in caplog.records if "embed_progress" in r.message]
        assert len(progress_logs) == 3, (
            f"Expected 3 progress log entries (one per chunk), got {len(progress_logs)}"
        )

    def test_parallel_start_logged_with_worker_count(self, caplog):
        """embed_parallel must log worker count at start so operators can confirm serial mode."""
        import logging
        vs = self._make_vs()
        vs._embed = MagicMock(return_value=[0.1])

        with caplog.at_level(logging.INFO, logger="app.services.vector_store"):
            vs._embed_parallel(["one chunk"])

        start_logs = [r for r in caplog.records if "embed_parallel_start" in r.message]
        assert start_logs, "embed_parallel_start log missing"
        assert f"workers={_EMBED_WORKERS}" in start_logs[0].message


# ---------------------------------------------------------------------------
# 3. QA agent
# ---------------------------------------------------------------------------

from app.agents.qa_agent import QAAgent
from app.services.hybrid_qa_retrieval import ABSTAIN_MESSAGE_HE
from app.services.mc_response_normalizer import (
    _semantic_select_letter,
    _MC_SEMANTIC_MIN_SUPPORT,
    _MC_SEMANTIC_CLEAR_MARGIN,
    _MC_SEMANTIC_AMBIGUOUS_MARGIN,
)


class TestQAAgentMCNoContext:
    def _make_agent(self, mock_vs):
        with patch("app.agents.qa_agent.VectorStoreService", return_value=mock_vs):
            agent = QAAgent()
        return agent

    def _mc_parsed(self):
        return {
            "stem": "מי מוסמך לאשר עסקאות?",
            "option_script": "hebrew",
            "options": [
                {"letter": "א", "text": "הדירקטוריון"},
                {"letter": "ב", "text": "המנכ\"ל"},
            ],
            "retrieval_query": "מי מוסמך לאשר עסקאות הדירקטוריון המנכ\"ל",
        }

    def test_mc_with_no_context_returns_unknown_without_llm_call(self, mock_vector_store, db):
        """
        FIX: MC with no relevant context must return UNKNOWN immediately —
        the old code called the LLM with empty context, causing hallucination.
        """
        agent = self._make_agent(mock_vector_store)
        mock_http = MagicMock()
        # Ensure Ollama is NOT called.
        with patch("app.agents.qa_agent.requests.post", mock_http):
            result = agent.answer(
                question=self._mc_parsed()["stem"],
                db=db,
                course_id="course-with-no-docs",
                lecture_id=None,
                qa_mode="multiple_choice",
                mc_parsed=self._mc_parsed(),
            )

        mock_http.assert_not_called()
        assert result["multiple_choice"]["correct_letter"] == "UNKNOWN"
        assert result["multiple_choice"]["explanation"] == ABSTAIN_MESSAGE_HE

    def test_open_qa_with_no_context_returns_abstain_without_llm(self, mock_vector_store, db):
        agent = self._make_agent(mock_vector_store)
        mock_http = MagicMock()
        with patch("app.agents.qa_agent.requests.post", mock_http):
            result = agent.answer(
                question="מה תפקיד הדירקטוריון?",
                db=db,
                course_id="empty-course",
                lecture_id=None,
                qa_mode="open",
            )

        mock_http.assert_not_called()
        assert result["answer"] == ABSTAIN_MESSAGE_HE
        assert result["sources"] == []

    def test_mc_stem_used_for_retrieval_not_full_options(self, mock_vector_store, db):
        """
        FIX: retrieval_question for MC must use the stem, not the concatenation
        of all options (which dilutes the embedding with distractors).
        """
        agent = self._make_agent(mock_vector_store)
        mc = self._mc_parsed()
        stem = mc["stem"]

        mock_vector_store.search_with_distances.return_value = [
            {
                "text": "הדירקטוריון מאשר עסקאות בניגוד עניינים.",
                "snippet": "הדירקטוריון מאשר",
                "document_id": "d1",
                "chunk_index": 0,
                "course_id": "c1",
                "lecture_id": None,
                "_distance": 0.1,
            }
        ]

        ollama_resp = MagicMock()
        ollama_resp.json.return_value = {"response": "CORRECT: א\nEXPLANATION:\nהדירקטוריון מוסמך."}
        ollama_resp.raise_for_status = MagicMock()

        captured_prompts = []

        def capture_post(url, json=None, **kwargs):
            if "generate" in url:
                captured_prompts.append(json.get("prompt", ""))
            return ollama_resp

        with patch("app.agents.qa_agent.requests.post", side_effect=capture_post):
            agent.answer(
                question=mc["stem"],
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="multiple_choice",
                mc_parsed=mc,
            )

        # The vector store must have been queried with the stem, not the full retrieval_query.
        if mock_vector_store.search_with_distances.called:
            call_args = mock_vector_store.search_with_distances.call_args
            used_query = call_args[1].get("query") or call_args[0][0]
            assert used_query == stem, (
                f"Expected retrieval with stem={stem!r}, got {used_query!r}"
            )


class TestMCSemanticGrounding:
    def _mc_vuca(self):
        return {
            "stem": "מה אחד האתגרים המרכזיים של עולם VUCA?",
            "option_script": "hebrew",
            "options": [
                {"letter": "א", "text": "קושי בקבלת החלטות בתנאי אי-ודאות"},
                {"letter": "ב", "text": "יציבות מלאה בתהליכי עבודה"},
                {"letter": "ג", "text": "ירידה בצורך בגמישות ניהולית"},
            ],
        }

    def test_semantic_wording_difference_selects_supported_option(self):
        mc = self._mc_vuca()
        context = (
            "עולם VUCA מאופיין באי ודאות גבוהה, תנודתיות ועמימות. "
            "במצב כזה מנהלים מתקשים לקבל החלטות ומתקשים לתכנן קדימה."
        )
        result = _semantic_select_letter(
            model_letter="UNKNOWN",
            explanation="ההקשר מדגיש שקשה להחליט כשאין ודאות.",
            mc_parsed=mc,
            context=context,
        )

        assert result["correct_letter"] == "א"
        assert result["scores"]["א"] >= _MC_SEMANTIC_MIN_SUPPORT
        assert (result["scores"]["א"] - result["scores"]["ב"]) >= _MC_SEMANTIC_CLEAR_MARGIN

    def test_no_relevant_context_stays_unknown(self):
        mc = self._mc_vuca()
        context = "המסמך עוסק בהיסטוריה של הארגון ובמבנה המחלקות."
        result = _semantic_select_letter(
            model_letter="א",
            explanation="",
            mc_parsed=mc,
            context=context,
        )

        assert result["correct_letter"] == "UNKNOWN"

    def test_two_similar_supported_options_stay_unknown(self):
        mc = {
            "stem": "מה הקושי המרכזי המתואר?",
            "option_script": "hebrew",
            "options": [
                {"letter": "א", "text": "קושי בקבלת החלטות בתנאי אי-ודאות"},
                {"letter": "ב", "text": "קושי בתכנון לטווח ארוך בתנאי אי-ודאות"},
                {"letter": "ג", "text": "שיפור בוודאות הארגונית"},
            ],
        }
        context = (
            "החומר מתאר אי ודאות שמקשה גם על קבלת החלטות וגם על תכנון ארוך טווח, "
            "בלי להדגיש איזה משני הקשיים מרכזי יותר."
        )
        result = _semantic_select_letter(
            model_letter="UNKNOWN",
            explanation="",
            mc_parsed=mc,
            context=context,
        )

        assert result["correct_letter"] == "UNKNOWN"
        sorted_scores = sorted(result["scores"].values(), reverse=True)
        assert (sorted_scores[0] - sorted_scores[1]) < _MC_SEMANTIC_AMBIGUOUS_MARGIN

    def test_end_to_end_mc_unknown_from_model_is_rescued_by_clear_semantic_winner(self, mock_vector_store, db):
        mc = self._mc_vuca()
        chunk = make_chunk(
            text=(
                "עולם VUCA כולל תנודתיות, אי ודאות ועמימות, ולכן מנהלים מתקשים לקבל "
                "החלטות ולבחור כיוון פעולה ברור."
            ),
            distance=0.08,
        )
        mock_vector_store.fetch_chunks_for_scope.return_value = []
        mock_vector_store.search_with_distances.return_value = [chunk]

        with patch("app.agents.qa_agent.VectorStoreService", return_value=mock_vector_store):
            agent = QAAgent()

        def _fake_post(url, json=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                "response": "CORRECT: UNKNOWN\nEXPLANATION:\nהניסוח אינו מופיע במדויק בהקשר."
            }
            resp.raise_for_status.return_value = None
            return resp

        with patch("app.agents.qa_agent.requests.post", side_effect=_fake_post), \
             patch("app.agents.qa_agent.enrich_sources", return_value=[]):
            result = agent.answer(
                question=mc["stem"],
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="multiple_choice",
                mc_parsed=mc,
            )

        assert result["multiple_choice"]["correct_letter"] == "א"
        assert "הקשר" in result["multiple_choice"]["explanation"] or "context" in result["multiple_choice"]["explanation"].lower()


# ---------------------------------------------------------------------------
# 4. Documents route — raw_text persistence and has_summary fix
# ---------------------------------------------------------------------------

from app.routes.documents import _document_to_dict
from app.models.document import Document
from app.models.summary import Summary as SummaryModel


class TestDocumentToDict:
    def _make_doc(self):
        doc = Document(
            id="doc-1",
            course_id="c1",
            file_name="test.pdf",
            file_path="/tmp/test.pdf",
            file_type="pdf",
            raw_text="some extracted text",
        )
        return doc

    def test_has_summary_true_when_summary_passed(self):
        doc = self._make_doc()
        summary = MagicMock()
        summary.summary_text = "A good summary."
        result = _document_to_dict(doc, summary=summary)
        assert result["has_summary"] is True
        assert "good summary" in result["summary_preview"]

    def test_has_summary_false_when_no_summary(self):
        doc = self._make_doc()
        result = _document_to_dict(doc, summary=None)
        assert result["has_summary"] is False
        assert result["summary_preview"] == ""

    def test_has_summary_false_for_empty_summary_text(self):
        doc = self._make_doc()
        summary = MagicMock()
        summary.summary_text = "   "
        result = _document_to_dict(doc, summary=summary)
        assert result["has_summary"] is False

    def test_summary_preview_truncated_at_280_chars(self):
        doc = self._make_doc()
        summary = MagicMock()
        summary.summary_text = "A" * 400
        result = _document_to_dict(doc, summary=summary)
        assert result["summary_preview"].endswith("...")
        assert len(result["summary_preview"]) == 283  # 280 + "..."

    def test_raw_text_length_reported(self):
        doc = self._make_doc()
        result = _document_to_dict(doc, summary=None)
        assert result["raw_text_length"] == len("some extracted text")


# ---------------------------------------------------------------------------
# 5. Vision fallback — truncation logging
# ---------------------------------------------------------------------------

def _make_fitz_doc_mock(page_count: int) -> MagicMock:
    """Build a fitz.Document-like mock with the given number of pages."""
    page_mock = MagicMock()
    pix_mock = MagicMock()
    pix_mock.tobytes.return_value = b"fake-png"
    page_mock.get_pixmap.return_value = pix_mock

    doc_mock = MagicMock()
    doc_mock.__len__ = MagicMock(return_value=page_count)
    doc_mock.__getitem__ = MagicMock(return_value=page_mock)
    doc_mock.close = MagicMock()
    # Support context manager usage.
    doc_mock.__enter__ = MagicMock(return_value=doc_mock)
    doc_mock.__exit__ = MagicMock(return_value=False)
    return doc_mock


class TestVisionFallbackLogging:
    def test_truncation_warning_logged_for_long_pdf(self, caplog):
        import logging
        from app.services.pdf_vision_fallback_service import extract_pdf_text_via_vision

        doc_mock = _make_fitz_doc_mock(page_count=15)

        with patch("app.services.pdf_vision_fallback_service.fitz.open", return_value=doc_mock), \
             patch(
                 "app.services.pdf_vision_fallback_service._vision_single_page_png",
                 return_value=("page text", None),
             ), \
             caplog.at_level(logging.WARNING, logger="app.services.pdf_vision_fallback_service"):
            extract_pdf_text_via_vision("/fake/path.pdf")

        truncation_warnings = [r for r in caplog.records if "truncated" in r.message]
        assert truncation_warnings, (
            "Expected a truncation WARNING for a 15-page PDF when PDF_VISION_MAX_PAGES=10"
        )

    def test_no_truncation_warning_for_short_pdf(self, caplog):
        import logging
        from app.services.pdf_vision_fallback_service import extract_pdf_text_via_vision

        doc_mock = _make_fitz_doc_mock(page_count=3)

        with patch("app.services.pdf_vision_fallback_service.fitz.open", return_value=doc_mock), \
             patch(
                 "app.services.pdf_vision_fallback_service._vision_single_page_png",
                 return_value=("page text", None),
             ), \
             caplog.at_level(logging.WARNING, logger="app.services.pdf_vision_fallback_service"):
            extract_pdf_text_via_vision("/fake/path.pdf")

        truncation_warnings = [r for r in caplog.records if "truncated" in r.message]
        assert not truncation_warnings


# ---------------------------------------------------------------------------
# 6. Ingestion pipeline — raw_text saved before chunking (integration-style)
# ---------------------------------------------------------------------------

class TestDocumentProcessingOrder:
    """
    Verify that raw_text is committed to the DB before chunking begins.
    A chunking failure must not lose the already-extracted text.
    """

    def test_raw_text_saved_before_chunking_on_failure(self, db, tmp_path):
        from app.routes.documents import _process_existing_document
        from app.models.document import Document

        # Write a tiny real text file.
        f = tmp_path / "test.txt"
        f.write_text("Hello world. This is test content for ingestion.")

        doc = Document(
            id="test-doc-rawtext",
            course_id="c1",
            file_name="test.txt",
            file_path=str(f),
            file_type="txt",
        )
        db.add(doc)
        db.commit()

        # Patch ChunkingAgent to fail after extraction succeeds.
        with patch(
            "app.routes.documents.ChunkingAgent"
        ) as MockChunker, patch(
            "app.routes.documents.VectorStoreService"
        ):
            MockChunker.return_value.chunk_text.side_effect = RuntimeError("chunking boom")
            try:
                _process_existing_document(db, doc)
            except Exception:
                pass

        db.refresh(doc)
        # Even though chunking failed, raw_text should have been persisted.
        assert doc.raw_text is not None and len(doc.raw_text) > 0, (
            "raw_text was not saved before the chunking stage failed"
        )


# ---------------------------------------------------------------------------
# 7. Definition question detection + answer grounding
# ---------------------------------------------------------------------------

from app.agents.qa_agent import _is_definition_question, _is_acronym_question
from tests.conftest import make_chunk


class TestDefinitionQuestionDetection:
    """_is_definition_question must fire on standard patterns and not on others."""

    @pytest.mark.parametrize("q", [
        "מה זה VUCA?",
        "מה זה VUCA",
        "מה ה-VUCA?",
        "מה הוא VUCA?",
        "מה היא אגיליות?",
        "מה המשמעות של VUCA?",
        "מה פירוש VUCA?",
        "הגדר את VUCA",
        "What is VUCA?",
        "what is agility",
        "Define VUCA",
        "Explain the term VUCA",
    ])
    def test_detects_definition_pattern(self, q):
        assert _is_definition_question(q), f"should detect: {q!r}"

    @pytest.mark.parametrize("q", [
        "מה ההשלכות של VUCA?",
        "כיצד מתמודדים עם VUCA?",
        "מה עושים כאשר יש אי ודאות?",
        "How does VUCA affect organisations?",
        "Describe the impact of VUCA",
    ])
    def test_ignores_non_definition_pattern(self, q):
        assert not _is_definition_question(q), f"should not detect: {q!r}"


class TestVucaDefinitionGrounding:
    """
    Regression: 'מה זה VUCA?' must return an answer that mentions all four
    VUCA components when the definition chunk is present in context.
    """

    VUCA_DEFINITION_CHUNK = (
        "(המתאר עולם VUCA אבל בפועל, עוד הרבה לפני שהמושג\n"
        "; עם אי Volatility - תנודתי סוער\n"
        "; מורכבות Uncertainty - ודאות גבוהה\n"
        "; Complexity - ותהליכים כאוטיים\n"
        "ורמות הולכות וגדלות של עמימות\n"
        ") הפך לשגור ומעצב, Ambiguity -\n"
        " הדינמיקה בין כאוס וסדר הייתה חלק משגרת העולם"
    )

    def _make_agent(self, mock_vs):
        with patch("app.agents.qa_agent.VectorStoreService", return_value=mock_vs):
            agent = QAAgent()
        return agent

    def test_definition_chunk_not_truncated_for_definition_question(
        self, mock_vector_store, db
    ):
        """
        Top chunk for 'מה זה VUCA?' must NOT be truncated at QA_MAX_CHUNK_CHARS
        (400) — the full acronym definition (including Ambiguity) must reach the LLM.
        """
        # Build a chunk that is longer than 400 chars but contains the
        # Ambiguity entry at character position ~410.
        padding = "א" * 390  # Hebrew letter × 390 → pads to 390 chars
        long_text = padding + "; Ambiguity - עמימות\nmore text after definition"

        chunk = make_chunk(text=long_text, distance=0.1)
        mock_vector_store.fetch_chunks_for_scope.return_value = []
        mock_vector_store.search_with_distances.return_value = [chunk]

        agent = self._make_agent(mock_vector_store)

        llm_received_prompt: list[str] = []

        def _fake_post(url, json=None, timeout=None):
            llm_received_prompt.append(json.get("prompt", ""))
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"response": "VUCA הוא ראשי תיבות"}
            resp.raise_for_status.return_value = None
            return resp

        with patch("app.agents.qa_agent.requests.post", side_effect=_fake_post), \
             patch("app.services.source_enricher.enrich_sources", return_value=[]):
            agent.answer(
                question="מה זה VUCA?",
                db=db,
                course_id="course-1",
                lecture_id=None,
                qa_mode="open",
            )

        assert llm_received_prompt, "LLM was never called"
        prompt = llm_received_prompt[0]
        # "; Ambiguity - עמימות" must appear in prompt — it's beyond char 400
        assert "Ambiguity" in prompt, (
            "Ambiguity was truncated from the top chunk for a definition question. "
            "QA_DEFINITION_CHUNK_CHARS must be raised above QA_MAX_CHUNK_CHARS."
        )

    def test_definition_hint_injected_into_prompt(self, mock_vector_store, db):
        """
        For 'מה זה VUCA?' the prompt must contain the definition grounding hint
        so the LLM is directed to quote the acronym breakdown directly.
        """
        chunk = make_chunk(text=self.VUCA_DEFINITION_CHUNK, distance=0.1)
        mock_vector_store.fetch_chunks_for_scope.return_value = []
        mock_vector_store.search_with_distances.return_value = [chunk]

        agent = self._make_agent(mock_vector_store)
        captured: list[str] = []

        def _fake_post(url, json=None, timeout=None):
            captured.append(json.get("prompt", ""))
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"response": "תשובה"}
            resp.raise_for_status.return_value = None
            return resp

        with patch("app.agents.qa_agent.requests.post", side_effect=_fake_post), \
             patch("app.services.source_enricher.enrich_sources", return_value=[]):
            agent.answer(
                question="מה זה VUCA?",
                db=db,
                course_id="course-1",
                lecture_id=None,
                qa_mode="open",
            )

        assert captured, "LLM was never called"
        assert "definition questions" in captured[0] or "כללי מענה לשאלות הגדרה" in captured[0], (
            "Definition rules block missing from prompt for 'מה זה VUCA?'"
        )

    def test_vuca_answer_contains_all_four_components(self, mock_vector_store, db):
        """
        Regression: when the VUCA definition chunk is retrieved and the LLM returns a
        grounded answer, all four VUCA components must appear in the final response.

        This pins the full pipeline:
          correct retrieval → definition-aware prompt → answer returned unchanged.

        The LLM is mocked to return a grounded answer (what a working model should
        produce given the improved prompt + full context). If the pipeline post-processes
        or drops the answer incorrectly, this test catches it.
        """
        chunk = make_chunk(text=self.VUCA_DEFINITION_CHUNK, distance=0.05)
        mock_vector_store.search_with_distances.return_value = [chunk]
        mock_vector_store.fetch_chunks_for_scope.return_value = []

        agent = self._make_agent(mock_vector_store)

        grounded_answer = (
            "VUCA הוא ראשי תיבות של: "
            "Volatility (תנודתיות), "
            "Uncertainty (אי-ודאות), "
            "Complexity (מורכבות), "
            "Ambiguity (עמימות). "
            "המושג מתאר את הסביבה העסקית המאופיינת בחוסר יציבות ואי-ודאות."
        )

        def _fake_post(url, json=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"response": grounded_answer}
            resp.raise_for_status.return_value = None
            return resp

        with patch("app.agents.qa_agent.requests.post", side_effect=_fake_post), \
             patch("app.services.source_enricher.enrich_sources", return_value=[]):
            result = agent.answer(
                question="מה זה VUCA?",
                db=db,
                course_id="course-1",
                lecture_id=None,
                qa_mode="open",
            )

        answer = result["answer"]
        required = ["Volatility", "Uncertainty", "Complexity", "Ambiguity"]
        missing = [t for t in required if t not in answer]
        assert not missing, (
            f"VUCA answer missing components {missing}.\nFull answer: {answer!r}"
        )

    def test_prompt_instructs_model_not_to_use_own_knowledge(self, mock_vector_store, db):
        """
        The improved definition hint must explicitly tell the model to use Context,
        not its own knowledge — this is the key guard against qwen2:0.5b hallucinating
        the wrong acronym expansion.
        """
        chunk = make_chunk(text=self.VUCA_DEFINITION_CHUNK, distance=0.05)
        mock_vector_store.search_with_distances.return_value = [chunk]
        mock_vector_store.fetch_chunks_for_scope.return_value = []

        agent = self._make_agent(mock_vector_store)
        captured: list[str] = []

        def _fake_post(url, json=None, timeout=None):
            captured.append(json.get("prompt", ""))
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"response": "תשובה"}
            resp.raise_for_status.return_value = None
            return resp

        with patch("app.agents.qa_agent.requests.post", side_effect=_fake_post), \
             patch("app.services.source_enricher.enrich_sources", return_value=[]):
            agent.answer(
                question="מה זה VUCA?",
                db=db,
                course_id="course-1",
                lecture_id=None,
                qa_mode="open",
            )

        assert captured, "LLM was never called"
        prompt = captured[0]
        assert "own knowledge" in prompt or "ידע שלך" in prompt, (
            "Prompt must tell the model not to use its own knowledge. "
            "This prevents small models from hallucinating wrong acronym expansions."
        )
        assert "skip" in prompt or "כל הרכיבים" in prompt or "אל תדלג" in prompt, (
            "Prompt must instruct the model to include every acronym component."
        )

    def test_non_definition_question_does_not_get_hint(self, mock_vector_store, db):
        """
        The definition hint must NOT appear for non-definition questions.
        """
        chunk = make_chunk(text="כלשהו טקסט על VUCA", distance=0.1)
        mock_vector_store.fetch_chunks_for_scope.return_value = []
        mock_vector_store.search_with_distances.return_value = [chunk]

        agent = self._make_agent(mock_vector_store)
        captured: list[str] = []

        def _fake_post(url, json=None, timeout=None):
            captured.append(json.get("prompt", ""))
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"response": "תשובה"}
            resp.raise_for_status.return_value = None
            return resp

        with patch("app.agents.qa_agent.requests.post", side_effect=_fake_post), \
             patch("app.services.source_enricher.enrich_sources", return_value=[]):
            agent.answer(
                question="כיצד מתמודדים עם VUCA?",
                db=db,
                course_id="course-1",
                lecture_id=None,
                qa_mode="open",
            )

        if captured:
            assert "definition questions" not in captured[0] and "כללי מענה לשאלות הגדרה" not in captured[0], (
                "Definition rules block injected for a non-definition question"
            )


# ---------------------------------------------------------------------------
# 8. Dual-model provider routing
# ---------------------------------------------------------------------------

import app.agents.qa_agent as _qa_mod


class TestDualModelRouting:
    """
    Provider routing: definition/acronym → OpenAI, everything else → Ollama.
    Fallback: OpenAI failure → Ollama.
    """

    def _make_agent(self, mock_vs):
        with patch("app.agents.qa_agent.VectorStoreService", return_value=mock_vs):
            return QAAgent()

    def _chunk_with_text(self, text="context text about the topic"):
        return make_chunk(text=text, distance=0.1)

    def _setup_vs(self, mock_vs, text="context text"):
        chunk = self._chunk_with_text(text)
        mock_vs.fetch_chunks_for_scope.return_value = []
        mock_vs.search_with_distances.return_value = [chunk]

    def test_normal_question_uses_ollama_not_openai(self, mock_vector_store, db, monkeypatch):
        """A non-definition question must be routed to Ollama, not OpenAI."""
        monkeypatch.setattr(_qa_mod, "_QA_PROVIDER_DEFINITION", "openai")
        monkeypatch.setattr(_qa_mod, "_OPENAI_API_KEY", "sk-fake")
        self._setup_vs(mock_vector_store)

        agent = self._make_agent(mock_vector_store)
        openai_called = []

        def fake_ollama_post(url, json=None, timeout=None, **kw):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"response": "תשובה מ-Ollama"}
            resp.raise_for_status.return_value = None
            return resp

        with patch("app.agents.qa_agent._generate_with_openai", side_effect=lambda *a, **k: openai_called.append(1) or "openai answer") as mock_openai, \
             patch("app.agents.qa_agent.requests.post", side_effect=fake_ollama_post), \
             patch("app.services.source_enricher.enrich_sources", return_value=[]):
            result = agent.answer(
                question="כיצד מתמודדים עם לחץ בעבודה?",
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="open",
            )

        assert not openai_called, "OpenAI must not be called for a non-definition question"
        assert result["answer"] == "תשובה מ-Ollama"

    def test_definition_question_uses_openai(self, mock_vector_store, db, monkeypatch):
        """A definition question must be routed to OpenAI when configured."""
        monkeypatch.setattr(_qa_mod, "_QA_PROVIDER_DEFINITION", "openai")
        monkeypatch.setattr(_qa_mod, "_OPENAI_API_KEY", "sk-fake")
        monkeypatch.setattr(_qa_mod, "_OPENAI_MODEL", "gpt-4.1-mini")
        self._setup_vs(mock_vector_store)

        agent = self._make_agent(mock_vector_store)
        openai_calls = []

        def fake_openai(prompt, api_key, model, timeout):
            openai_calls.append({"model": model, "api_key": api_key})
            return "VUCA הוא ראשי תיבות"

        with patch("app.agents.qa_agent._generate_with_openai", side_effect=fake_openai), \
             patch("app.services.source_enricher.enrich_sources", return_value=[]):
            result = agent.answer(
                question="מה זה VUCA?",
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="open",
            )

        assert openai_calls, "OpenAI must be called for a definition question"
        assert openai_calls[0]["model"] == "gpt-4.1-mini"
        assert result["answer"] == "VUCA הוא ראשי תיבות"

    def test_acronym_question_uses_openai(self, mock_vector_store, db, monkeypatch):
        """An acronym question must also be routed to OpenAI."""
        monkeypatch.setattr(_qa_mod, "_QA_PROVIDER_DEFINITION", "openai")
        monkeypatch.setattr(_qa_mod, "_OPENAI_API_KEY", "sk-fake")
        self._setup_vs(mock_vector_store)

        agent = self._make_agent(mock_vector_store)
        openai_calls = []

        def fake_openai(prompt, api_key, model, timeout):
            openai_calls.append(True)
            return "VUCA stands for Volatility, Uncertainty, Complexity, Ambiguity"

        with patch("app.agents.qa_agent._generate_with_openai", side_effect=fake_openai), \
             patch("app.services.source_enricher.enrich_sources", return_value=[]):
            result = agent.answer(
                question="מה פירוש ראשי התיבות VUCA?",
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="open",
            )

        assert openai_calls, "OpenAI must be called for an acronym question"

    def test_openai_failure_falls_back_to_ollama(self, mock_vector_store, db, monkeypatch):
        """If OpenAI raises, the agent must fall back to Ollama silently."""
        monkeypatch.setattr(_qa_mod, "_QA_PROVIDER_DEFINITION", "openai")
        monkeypatch.setattr(_qa_mod, "_OPENAI_API_KEY", "sk-fake")
        self._setup_vs(mock_vector_store)

        agent = self._make_agent(mock_vector_store)
        ollama_calls = []

        def fail_openai(prompt, api_key, model, timeout):
            raise RuntimeError("OpenAI API unreachable")

        def fake_ollama_post(url, json=None, timeout=None, **kw):
            if "generate" in url:
                ollama_calls.append(True)
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"response": "תשובה מ-Ollama fallback"}
            resp.raise_for_status.return_value = None
            return resp

        with patch("app.agents.qa_agent._generate_with_openai", side_effect=fail_openai), \
             patch("app.agents.qa_agent.requests.post", side_effect=fake_ollama_post), \
             patch("app.services.source_enricher.enrich_sources", return_value=[]):
            result = agent.answer(
                question="מה זה VUCA?",
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="open",
            )

        assert ollama_calls, "Ollama must be called as fallback when OpenAI fails"
        assert result["answer"] == "תשובה מ-Ollama fallback"

    def test_provider_selection_logged(self, mock_vector_store, db, monkeypatch, caplog):
        """Provider selection must be logged with provider, reason, and model."""
        import logging
        monkeypatch.setattr(_qa_mod, "_QA_PROVIDER_DEFINITION", "openai")
        monkeypatch.setattr(_qa_mod, "_OPENAI_API_KEY", "sk-fake")
        monkeypatch.setattr(_qa_mod, "_OPENAI_MODEL", "gpt-4.1-mini")
        self._setup_vs(mock_vector_store)

        agent = self._make_agent(mock_vector_store)

        with patch("app.agents.qa_agent._generate_with_openai", return_value="answer"), \
             patch("app.services.source_enricher.enrich_sources", return_value=[]), \
             caplog.at_level(logging.INFO, logger="app.agents.qa_agent"):
            agent.answer(
                question="מה זה VUCA?",
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="open",
            )

        log_messages = " ".join(r.message for r in caplog.records)
        assert "qa.provider.selected" in log_messages
        assert "openai" in log_messages
        assert "definition_or_acronym" in log_messages

    def test_sources_preserved_after_openai_generation(self, mock_vector_store, db, monkeypatch):
        """Sources must be enriched and returned even when OpenAI generates the answer."""
        monkeypatch.setattr(_qa_mod, "_QA_PROVIDER_DEFINITION", "openai")
        monkeypatch.setattr(_qa_mod, "_OPENAI_API_KEY", "sk-fake")
        self._setup_vs(mock_vector_store)

        agent = self._make_agent(mock_vector_store)
        enriched_sources = [{"document_id": "d1", "title": "Lecture 1"}]

        with patch("app.agents.qa_agent._generate_with_openai", return_value="answer"), \
             patch("app.agents.qa_agent.enrich_sources", return_value=enriched_sources):
            result = agent.answer(
                question="מה זה VUCA?",
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="open",
            )

        assert result["sources"] == enriched_sources, (
            "sources must be returned even when the answer comes from OpenAI"
        )


# ---------------------------------------------------------------------------
# 9. Multilingual retrieval — English queries expand to Hebrew searches
# ---------------------------------------------------------------------------

from app.services.hybrid_qa_retrieval import (
    _is_english_dominant,
    _detect_question_language,
    _extract_key_term,
    _acronym_definition_bonus,
    _build_retrieval_queries,
    merge_and_rerank,
)


class TestLanguageDetection:
    @pytest.mark.parametrize("text,expected", [
        ("What does VUCA stand for?", True),
        ("Define agility in organisational context", True),
        ("VUCA stands for Volatility Uncertainty", True),
        ("מה זה VUCA?", False),            # Hebrew dominant
        ("VU", False),                     # fewer than 4 English chars
        ("", False),
    ])
    def test_is_english_dominant(self, text, expected):
        assert _is_english_dominant(text) == expected, f"failed for {text!r}"

    @pytest.mark.parametrize("text,expected", [
        ("What does VUCA stand for?", "en"),
        ("מה זה VUCA?", "he"),
        ("VUCA?", "en"),
    ])
    def test_detect_question_language(self, text, expected):
        assert _detect_question_language(text) == expected


class TestExtractKeyTerm:
    @pytest.mark.parametrize("question,expected", [
        ("What does VUCA stand for?", "VUCA"),
        ("What is agility?", "agility"),
        ("Define VUCA", "VUCA"),
        ("Explain the term VUCA", "VUCA"),
        ("What is the acronym for VUCA?", "VUCA"),
        ("What is the full acronym for VUCA?", "VUCA"),
        ("What does the term agility mean?", "term agility mean"),  # "the" consumed by optional article strip
    ])
    def test_extracts_key_term(self, question, expected):
        assert _extract_key_term(question) == expected, f"for {question!r}"


class TestAcronymDefinitionBonus:
    def test_bonus_given_when_acronym_plus_expansion_marker(self):
        text = "VUCA הוא ראשי תיבות של Volatility, Uncertainty, Complexity, Ambiguity"
        tokens = {"VUCA", "What", "does", "stand", "for"}
        bonus = _acronym_definition_bonus(text, tokens)
        assert bonus >= 3.0, "definition chunk with expansion marker must receive large bonus"

    def test_small_bonus_when_acronym_present_no_marker(self):
        text = "בעולם VUCA קיים אי-ודאות גבוה"
        tokens = {"VUCA"}
        bonus = _acronym_definition_bonus(text, tokens)
        assert 0 < bonus < 2.0, "chunk with acronym but no marker gets small bonus"

    def test_no_bonus_when_acronym_absent(self):
        text = "ראשי תיבות הם קיצורים שכיחים בשפה העברית"
        tokens = {"VUCA"}
        bonus = _acronym_definition_bonus(text, tokens)
        assert bonus == 0.0

    def test_no_bonus_for_lowercase_tokens(self):
        text = "vuca stands for volatility uncertainty complexity ambiguity"
        tokens = {"vuca"}  # lowercase — not treated as an acronym
        bonus = _acronym_definition_bonus(text, tokens)
        assert bonus == 0.0

    def test_extra_bonus_when_expansion_terms_present(self):
        text = "VUCA stands for Volatility, Uncertainty, Complexity, Ambiguity."
        tokens = {"VUCA"}
        expected_terms = {"volatility", "uncertainty", "complexity", "ambiguity"}
        bonus = _acronym_definition_bonus(text, tokens, expected_terms=expected_terms)
        assert bonus >= 8.0, "chunk with explicit expansion terms should receive a very large bonus"


class TestRetrievalQueryExpansion:
    def test_english_definition_query_adds_hebrew_variants(self):
        plan = _build_retrieval_queries("What does VUCA stand for?")
        assert plan["language"] == "en"
        assert plan["definition_mode"] is True
        assert "מה זה VUCA" in plan["queries"]
        assert "מה פירוש ראשי התיבות VUCA" in plan["queries"]
        assert "VUCA definition" in plan["queries"]
        assert "VUCA ראשי תיבות" in plan["queries"]

    def test_hebrew_definition_query_adds_english_variants(self):
        plan = _build_retrieval_queries("מה פירוש ראשי התיבות VUCA?")
        assert plan["language"] == "he"
        assert plan["definition_mode"] is True
        assert "What does VUCA stand for?" in plan["queries"]
        assert "Define VUCA" in plan["queries"]
        assert "VUCA definition" in plan["queries"]


class TestMultilingualRetrieval:
    def test_english_definition_question_triggers_hebrew_expansion(self, mock_vector_store):
        """
        An English-dominant question must issue additional Hebrew expansion
        searches so Hebrew course content is reachable.
        """
        mock_vector_store.fetch_chunks_for_scope.return_value = []
        mock_vector_store.search_with_distances.return_value = []

        hybrid_retrieve_for_qa(
            mock_vector_store,
            "What does VUCA stand for?",
            course_id="c1",
            lecture_id=None,
        )

        # Original + at least 2 Hebrew expansions = at least 3 calls
        call_count = mock_vector_store.search_with_distances.call_count
        assert call_count >= 3, (
            f"Expected ≥3 vector searches for English question (got {call_count})"
        )
        all_queries = [
            c.kwargs.get("query") or (c.args[0] if c.args else "")
            for c in mock_vector_store.search_with_distances.call_args_list
        ]
        hebrew_queries = [q for q in all_queries if any("\u0590" <= ch <= "\u05FF" for ch in q)]
        assert hebrew_queries, f"No Hebrew expansion queries issued. Queries were: {all_queries}"

    def test_hebrew_definition_question_triggers_english_expansion(self, mock_vector_store):
        mock_vector_store.fetch_chunks_for_scope.return_value = []
        mock_vector_store.search_with_distances.return_value = []

        hybrid_retrieve_for_qa(
            mock_vector_store,
            "מה פירוש ראשי התיבות VUCA?",
            course_id="c1",
            lecture_id=None,
        )

        all_queries = [
            c.kwargs.get("query") or (c.args[0] if c.args else "")
            for c in mock_vector_store.search_with_distances.call_args_list
        ]
        assert any("What does VUCA stand for?" == q for q in all_queries)
        assert any("Define VUCA" == q for q in all_queries)

    def test_non_definition_hebrew_question_does_not_trigger_cross_language_expansion(self, mock_vector_store):
        mock_vector_store.fetch_chunks_for_scope.return_value = []
        mock_vector_store.search_with_distances.return_value = []

        hybrid_retrieve_for_qa(
            mock_vector_store,
            "כיצד מתמודדים עם VUCA?",
            course_id="c1",
            lecture_id=None,
        )

        all_queries = [
            c.kwargs.get("query") or (c.args[0] if c.args else "")
            for c in mock_vector_store.search_with_distances.call_args_list
        ]
        assert all_queries == ["כיצד מתמודדים עם VUCA?"]

    def test_definition_chunk_outranks_mention_chunk(self):
        """
        A chunk containing the VUCA acronym expansion must rank above a chunk
        that merely mentions VUCA in passing.
        """
        definition_chunk = {
            "text": "VUCA הוא ראשי תיבות של Volatility, Uncertainty, Complexity, Ambiguity",
            "snippet": "VUCA הוא ראשי תיבות",
            "document_id": "d1", "chunk_index": 0,
            "course_id": "c1", "lecture_id": None,
            "_distance": 0.25, "_lex": 1.0,
        }
        mention_chunk = {
            "text": "בעולם VUCA עסקים נדרשים לגמישות",
            "snippet": "בעולם VUCA",
            "document_id": "d1", "chunk_index": 1,
            "course_id": "c1", "lecture_id": None,
            "_distance": 0.20, "_lex": 1.0,
        }

        tokens = {"VUCA", "What", "does", "stand", "for"}
        ranked = merge_and_rerank(
            lexical_chunks=[definition_chunk, mention_chunk],
            vector_chunks=[],
            question_tokens=tokens,
            phrases_in_q=[],
            domain_query=False,
        )

        assert ranked[0]["chunk_index"] == 0, (
            "Definition/expansion chunk must rank first over a mere mention chunk"
        )

    def test_english_definition_question_retrieves_relevant_chunk_via_hebrew_variant(self, mock_vector_store):
        mention_chunk = make_chunk(text="VUCA affects organizations in uncertain environments", chunk_index=1, distance=0.05)
        definition_chunk = make_chunk(
            text="VUCA הוא ראשי תיבות של Volatility, Uncertainty, Complexity, Ambiguity",
            chunk_index=0,
            distance=0.18,
        )
        mock_vector_store.fetch_chunks_for_scope.return_value = []

        def _search(*args, **kwargs):
            query = kwargs.get("query") or args[0]
            if query == "What does VUCA stand for?":
                return [mention_chunk]
            if "מה" in query or "ראשי תיבות" in query or "פירוש" in query:
                return [definition_chunk]
            return []

        mock_vector_store.search_with_distances.side_effect = _search

        chunks, abstain, _ = hybrid_retrieve_for_qa(
            mock_vector_store,
            "What does VUCA stand for?",
            course_id="c1",
            lecture_id=None,
        )

        assert abstain is False
        assert chunks[0]["chunk_index"] == 0
        assert "Volatility" in chunks[0]["text"]

    def test_hebrew_definition_question_retrieves_relevant_chunk_via_english_variant(self, mock_vector_store):
        mention_chunk = make_chunk(text="VUCA הוא מושג חשוב בעולם הניהול", chunk_index=1, distance=0.05)
        definition_chunk = make_chunk(
            text="VUCA stands for Volatility, Uncertainty, Complexity, Ambiguity.",
            chunk_index=0,
            distance=0.18,
        )
        mock_vector_store.fetch_chunks_for_scope.return_value = []

        def _search(*args, **kwargs):
            query = kwargs.get("query") or args[0]
            if query == "מה זה VUCA?":
                return [mention_chunk]
            if query in {"What is VUCA?", "Define VUCA", "What does VUCA stand for?"}:
                return [definition_chunk]
            return []

        mock_vector_store.search_with_distances.side_effect = _search

        chunks, abstain, _ = hybrid_retrieve_for_qa(
            mock_vector_store,
            "מה זה VUCA?",
            course_id="c1",
            lecture_id=None,
        )

        assert abstain is False
        assert chunks[0]["chunk_index"] == 0
        assert "stands for" in chunks[0]["text"]

    def test_logging_includes_language_and_expansion_details(self, mock_vector_store, caplog):
        import logging

        mock_vector_store.fetch_chunks_for_scope.return_value = []
        mock_vector_store.search_with_distances.return_value = [
            make_chunk(
                text="VUCA stands for Volatility, Uncertainty, Complexity, Ambiguity.",
                distance=0.1,
            )
        ]

        with caplog.at_level(logging.INFO, logger="app.services.hybrid_qa_retrieval"):
            hybrid_retrieve_for_qa(
                mock_vector_store,
                "What does VUCA stand for?",
                course_id="c1",
                lecture_id=None,
            )

        messages = [record.message for record in caplog.records]
        assert any("retrieval.query_plan" in message and "language=en" in message for message in messages)
        assert any("definition_mode=True" in message for message in messages)
        assert any("expanded_queries=" in message for message in messages)
        assert any("rerank.acronym_boost applied=True" in message for message in messages)

    def test_prompt_max_two_sentences_instruction_present(self, mock_vector_store, db):
        """Definition prompt must instruct the model to answer in at most 2 sentences."""
        chunk = make_chunk(text="VUCA stands for Volatility Uncertainty Complexity Ambiguity", distance=0.1)
        mock_vector_store.fetch_chunks_for_scope.return_value = []
        mock_vector_store.search_with_distances.return_value = [chunk]

        with patch("app.agents.qa_agent.VectorStoreService", return_value=mock_vector_store):
            agent = QAAgent()

        captured: list[str] = []

        def _fake_post(url, json=None, timeout=None):
            captured.append(json.get("prompt", ""))
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"response": "VUCA stands for Volatility, Uncertainty, Complexity, Ambiguity."}
            resp.raise_for_status.return_value = None
            return resp

        with patch("app.agents.qa_agent.requests.post", side_effect=_fake_post), \
             patch("app.agents.qa_agent.enrich_sources", return_value=[]):
            agent.answer(
                question="What does VUCA stand for?",
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="open",
            )

        assert captured, "LLM was never called"
        prompt = captured[0]
        assert "2 sentence" in prompt or "at most 2" in prompt or "2 משפטים" in prompt, (
            "Prompt must constrain definition answers to at most 2 sentences"
        )

    def test_prompt_language_instruction_present(self, mock_vector_store, db):
        """Definition prompt must instruct the model to match the question language."""
        chunk = make_chunk(text="VUCA ראשי תיבות Volatility Uncertainty", distance=0.1)
        mock_vector_store.fetch_chunks_for_scope.return_value = []
        mock_vector_store.search_with_distances.return_value = [chunk]

        with patch("app.agents.qa_agent.VectorStoreService", return_value=mock_vector_store):
            agent = QAAgent()

        captured: list[str] = []

        def _fake_post(url, json=None, timeout=None):
            captured.append(json.get("prompt", ""))
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"response": "VUCA stands for..."}
            resp.raise_for_status.return_value = None
            return resp

        with patch("app.agents.qa_agent.requests.post", side_effect=_fake_post), \
             patch("app.agents.qa_agent.enrich_sources", return_value=[]):
            agent.answer(
                question="What does VUCA stand for?",
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="open",
            )

        assert captured
        prompt = captured[0]
        assert "same language" in prompt or "language" in prompt.lower(), (
            "Prompt must instruct the model to reply in the question's language"
        )

    def test_definition_answer_is_trimmed_to_two_sentences(self, mock_vector_store, db):
        chunk = make_chunk(text="VUCA stands for Volatility, Uncertainty, Complexity, Ambiguity.", distance=0.1)
        mock_vector_store.fetch_chunks_for_scope.return_value = []
        mock_vector_store.search_with_distances.return_value = [chunk]

        with patch("app.agents.qa_agent.VectorStoreService", return_value=mock_vector_store):
            agent = QAAgent()

        long_answer = (
            "VUCA stands for Volatility, Uncertainty, Complexity, and Ambiguity. "
            "It describes a volatile and uncertain environment. "
            "This third sentence should be removed."
        )

        with patch("app.agents.qa_agent.requests.post") as mock_post, \
             patch("app.agents.qa_agent.enrich_sources", return_value=[]):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"response": long_answer}
            mock_resp.raise_for_status.return_value = None
            mock_post.return_value = mock_resp

            result = agent.answer(
                question="What does VUCA stand for?",
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="open",
            )

        assert result["answer"].count(".") <= 2
        assert result["answer"].startswith("VUCA stands for")

    def test_hebrew_and_english_definition_variants_keep_equivalent_core_content(self, mock_vector_store, db):
        chunk = make_chunk(
            text="VUCA הוא ראשי תיבות של Volatility, Uncertainty, Complexity, Ambiguity.",
            distance=0.1,
        )
        mock_vector_store.fetch_chunks_for_scope.return_value = []
        mock_vector_store.search_with_distances.return_value = [chunk]

        with patch("app.agents.qa_agent.VectorStoreService", return_value=mock_vector_store):
            agent = QAAgent()

        answers = {
            "מה זה VUCA?": "VUCA הוא ראשי תיבות של Volatility, Uncertainty, Complexity, Ambiguity.",
            "What does VUCA stand for?": "VUCA stands for Volatility, Uncertainty, Complexity, and Ambiguity.",
        }

        def _fake_post(url, json=None, timeout=None):
            prompt = json.get("prompt", "")
            resp = MagicMock()
            resp.status_code = 200
            if "Question:\nמה זה VUCA?" in prompt:
                resp.json.return_value = {"response": answers["מה זה VUCA?"]}
            else:
                resp.json.return_value = {"response": answers["What does VUCA stand for?"]}
            resp.raise_for_status.return_value = None
            return resp

        with patch("app.agents.qa_agent.requests.post", side_effect=_fake_post), \
             patch("app.agents.qa_agent.enrich_sources", return_value=[]):
            he_result = agent.answer(
                question="מה זה VUCA?",
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="open",
            )
            en_result = agent.answer(
                question="What does VUCA stand for?",
                db=db,
                course_id="c1",
                lecture_id=None,
                qa_mode="open",
            )

        for token in ["Volatility", "Uncertainty", "Complexity", "Ambiguity"]:
            assert token in he_result["answer"]
            assert token in en_result["answer"]


# ---------------------------------------------------------------------------
# Summary agent — model env var, best-effort ingestion
# ---------------------------------------------------------------------------

from app.agents.summary_agent import SummaryAgent, _SUMMARY_OLLAMA_MODEL, _SUMMARY_PROVIDER


class TestSummaryAgentBasics:
    """SummaryAgent interface: model selection, prompts, empty guard."""

    def test_ollama_model_reads_from_env(self):
        agent = SummaryAgent(provider="ollama")
        assert agent.ollama_model == _SUMMARY_OLLAMA_MODEL

    def test_default_ollama_model_is_not_llama31(self):
        assert _SUMMARY_OLLAMA_MODEL != "llama3.1"

    def test_model_name_override_sets_both_models(self):
        agent = SummaryAgent(model_name="custom-model")
        assert agent.ollama_model == "custom-model"
        assert agent.openai_model == "custom-model"

    def test_empty_text_returns_no_content_message(self):
        agent = SummaryAgent()
        assert "No content" in agent.summarize("", language="en")

    def test_ollama_summarize_success(self):
        agent = SummaryAgent(provider="ollama")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "A concise summary."}
        mock_resp.raise_for_status.return_value = None

        with patch("app.agents.summary_agent.requests.post", return_value=mock_resp) as mock_post:
            result = agent.summarize("Some study material text.", language="en")

        assert result == "A concise summary."
        payload = mock_post.call_args[1]["json"]
        assert payload["model"] == _SUMMARY_OLLAMA_MODEL
        assert payload["stream"] is False

    def test_summarize_404_raises(self):
        agent = SummaryAgent(provider="ollama")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = Exception("404 Client Error: Not Found")
        mock_resp.text = "model not found"

        with patch("app.agents.summary_agent.requests.post", return_value=mock_resp):
            with pytest.raises(Exception, match="404"):
                agent.summarize("Some text.", language="en")

    def test_logs_provider_and_started(self, caplog):
        import logging
        agent = SummaryAgent(provider="ollama")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "ok"}
        mock_resp.raise_for_status.return_value = None

        with patch("app.agents.summary_agent.requests.post", return_value=mock_resp), \
             caplog.at_level(logging.INFO, logger="app.agents.summary_agent"):
            agent.summarize("text", language="en")

        combined = " ".join(caplog.messages)
        assert "summary_agent.summary_started" in combined
        assert "summary_agent.provider_used" in combined

    def test_hebrew_prompt(self):
        agent = SummaryAgent()
        assert "סכם" in agent._build_prompt("x", "he") or "מסכם" in agent._build_prompt("x", "he")

    def test_english_prompt(self):
        agent = SummaryAgent()
        prompt = agent._build_prompt("x", "en")
        assert "Summarize" in prompt or "summarizing" in prompt.lower()


# ---------------------------------------------------------------------------
# Summary lifecycle: background execution, provider routing, status column
# ---------------------------------------------------------------------------

import os as _os


class TestSummaryProviderRouting:
    """SummaryAgent selects correct provider based on env vars."""

    def test_ollama_provider_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("SUMMARY_PROVIDER", raising=False)
        import importlib
        import app.agents.summary_agent as sam
        importlib.reload(sam)
        assert sam._SUMMARY_PROVIDER == "ollama"

    def test_openai_provider_when_api_key_present(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("SUMMARY_PROVIDER", raising=False)
        import importlib
        import app.agents.summary_agent as sam
        importlib.reload(sam)
        assert sam._SUMMARY_PROVIDER == "openai"

    def test_explicit_summary_provider_wins_over_auto_detect(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("SUMMARY_PROVIDER", "ollama")
        import importlib
        import app.agents.summary_agent as sam
        importlib.reload(sam)
        assert sam._SUMMARY_PROVIDER == "ollama"

    def test_summary_timeout_reads_summary_timeout_s_env(self, monkeypatch):
        monkeypatch.setenv("SUMMARY_TIMEOUT_S", "15")
        import importlib
        import app.agents.summary_agent as sam
        importlib.reload(sam)
        assert sam._SUMMARY_TIMEOUT == 15

    def test_ollama_provider_calls_generate_endpoint(self):
        from app.agents.summary_agent import SummaryAgent
        agent = SummaryAgent(provider="ollama")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "A summary."}
        mock_resp.raise_for_status.return_value = None

        with patch("app.agents.summary_agent.requests.post", return_value=mock_resp) as mock_post:
            result = agent.summarize("text", language="en")

        assert result == "A summary."
        url = mock_post.call_args[0][0]
        assert "/api/generate" in url

    def test_openai_provider_calls_openai_sdk(self):
        from app.agents.summary_agent import SummaryAgent
        agent = SummaryAgent(provider="openai")

        mock_choice = MagicMock()
        mock_choice.message.content = "OpenAI summary."
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        with patch("app.agents.summary_agent._OPENAI_API_KEY", "sk-test"), \
             patch("openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.chat.completions.create.return_value = mock_completion
            result = agent.summarize("text", language="en")

        assert result == "OpenAI summary."
        MockOpenAI.return_value.chat.completions.create.assert_called_once()

    def test_openai_provider_raises_when_no_api_key(self):
        from app.agents.summary_agent import SummaryAgent
        agent = SummaryAgent(provider="openai")
        with patch("app.agents.summary_agent._OPENAI_API_KEY", ""):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                agent.summarize("text")

    def test_timeout_logged_as_client_only(self, caplog):
        import logging
        from requests.exceptions import Timeout
        from app.agents.summary_agent import SummaryAgent
        agent = SummaryAgent(provider="ollama")

        with patch("app.agents.summary_agent.requests.post", side_effect=Timeout("timed out")), \
             caplog.at_level(logging.ERROR, logger="app.agents.summary_agent"):
            with pytest.raises(Timeout):
                agent.summarize("text")

        combined = " ".join(caplog.messages)
        assert "summary_timeout_client" in combined
        assert "ollama" in combined.lower()


class TestSummaryStatusColumn:
    """summary_status field is present on Document and propagated through APIs."""

    def test_document_model_has_summary_status_field(self):
        from app.models.document import Document
        doc = Document()
        assert hasattr(doc, "summary_status")

    def test_document_to_dict_includes_summary_status(self):
        from app.routes.documents import _document_to_dict
        from app.models.document import Document

        doc = MagicMock(spec=Document)
        doc.id = "d1"
        doc.course_id = "c1"
        doc.lecture_id = None
        doc.file_name = "test.pdf"
        doc.file_type = "pdf"
        doc.language = "en"
        doc.topic = None
        doc.source_type = None
        doc.uploaded_at = None
        doc.processing_status = "ready"
        doc.processing_progress = 100
        doc.summary_status = "completed"
        doc.error_type = None
        doc.error_stage = None
        doc.last_error = None
        doc.raw_text = "some text"

        result = _document_to_dict(doc, lecture_title=None, summary=None)
        assert "summary_status" in result
        assert result["summary_status"] == "completed"

    def test_document_to_dict_defaults_summary_status_when_none(self):
        from app.routes.documents import _document_to_dict
        from app.models.document import Document

        doc = MagicMock(spec=Document)
        doc.id = "d2"
        doc.course_id = "c1"
        doc.lecture_id = None
        doc.file_name = "test.pdf"
        doc.file_type = "pdf"
        doc.language = "en"
        doc.topic = None
        doc.source_type = None
        doc.uploaded_at = None
        doc.processing_status = "ready"
        doc.processing_progress = 100
        doc.summary_status = None
        doc.error_type = None
        doc.error_stage = None
        doc.last_error = None
        doc.raw_text = ""

        result = _document_to_dict(doc, lecture_title=None, summary=None)
        assert result["summary_status"] == "not_started"


class TestRunSummaryInBackground:
    """_run_summary_in_background sets summary_status correctly."""

    def _make_doc(self, doc_id="doc-bg-1"):
        from app.models.document import Document
        doc = MagicMock(spec=Document)
        doc.id = doc_id
        doc.course_id = "c1"
        doc.language = "en"
        doc.raw_text = "Background summary text."
        doc.summary_status = "pending"
        doc.last_error = None
        return doc

    def test_success_sets_status_completed(self):
        from app.routes.documents import _run_summary_in_background
        from app.models.summary import Summary as SummaryModel

        doc = self._make_doc()
        statuses = []

        def _fake_commit():
            if hasattr(doc, "summary_status"):
                statuses.append(doc.summary_status)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = doc
        mock_db.query.return_value.filter.return_value.delete.return_value = None
        mock_db.commit.side_effect = _fake_commit

        with patch("app.routes.documents.SessionLocal", return_value=mock_db), \
             patch("app.routes.documents.SummaryAgent") as MockAgent, \
             patch("app.routes.documents._refresh_course_aggregates"):
            MockAgent.return_value.summarize.return_value = "Done summary."
            _run_summary_in_background(doc.id)

        assert doc.summary_status == "completed"

    def test_failure_sets_status_failed(self):
        from app.routes.documents import _run_summary_in_background

        doc = self._make_doc()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        with patch("app.routes.documents.SessionLocal", return_value=mock_db), \
             patch("app.routes.documents.SummaryAgent") as MockAgent:
            MockAgent.return_value.summarize.side_effect = Exception("Ollama 404")
            _run_summary_in_background(doc.id)

        assert doc.summary_status == "failed"

    def test_failure_does_not_change_processing_status(self):
        from app.routes.documents import _run_summary_in_background

        doc = self._make_doc()
        doc.processing_status = "ready"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        with patch("app.routes.documents.SessionLocal", return_value=mock_db), \
             patch("app.routes.documents.SummaryAgent") as MockAgent:
            MockAgent.return_value.summarize.side_effect = Exception("Timeout")
            _run_summary_in_background(doc.id)

        assert doc.processing_status == "ready"

    def test_aggregate_failure_does_not_revert_completed_status(self):
        from app.routes.documents import _run_summary_in_background

        doc = self._make_doc()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = doc
        mock_db.query.return_value.filter.return_value.delete.return_value = None

        with patch("app.routes.documents.SessionLocal", return_value=mock_db), \
             patch("app.routes.documents.SummaryAgent") as MockAgent, \
             patch("app.routes.documents._refresh_course_aggregates",
                   side_effect=Exception("aggregate boom")):
            MockAgent.return_value.summarize.return_value = "summary text"
            _run_summary_in_background(doc.id)

        assert doc.summary_status == "completed"

    def test_db_closed_even_on_exception(self):
        from app.routes.documents import _run_summary_in_background

        doc = self._make_doc()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = doc

        with patch("app.routes.documents.SessionLocal", return_value=mock_db), \
             patch("app.routes.documents.SummaryAgent") as MockAgent:
            MockAgent.return_value.summarize.side_effect = RuntimeError("crash")
            _run_summary_in_background(doc.id)

        mock_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# Aggregate agents: provider routing, step isolation, prompt limits
# ---------------------------------------------------------------------------

class TestAggregatesProviderRouting:
    """CourseSummaryAgent and KnowledgeMapAgent both honour AGGREGATES_PROVIDER."""

    def test_ollama_provider_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AGGREGATES_PROVIDER", raising=False)
        import importlib
        import app.agents.course_summary_agent as csa
        import app.agents.knowledge_map_agent as kma
        importlib.reload(csa)
        importlib.reload(kma)
        assert csa._AGGREGATES_PROVIDER == "ollama"
        assert kma._AGGREGATES_PROVIDER == "ollama"

    def test_openai_provider_when_api_key_present(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("AGGREGATES_PROVIDER", raising=False)
        import importlib
        import app.agents.course_summary_agent as csa
        import app.agents.knowledge_map_agent as kma
        importlib.reload(csa)
        importlib.reload(kma)
        assert csa._AGGREGATES_PROVIDER == "openai"
        assert kma._AGGREGATES_PROVIDER == "openai"

    def test_explicit_aggregates_provider_wins(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("AGGREGATES_PROVIDER", "ollama")
        import importlib
        import app.agents.course_summary_agent as csa
        importlib.reload(csa)
        assert csa._AGGREGATES_PROVIDER == "ollama"

    def test_aggregates_timeout_reads_env(self, monkeypatch):
        monkeypatch.setenv("AGGREGATES_TIMEOUT_S", "20")
        import importlib
        import app.agents.course_summary_agent as csa
        importlib.reload(csa)
        assert csa._AGGREGATES_TIMEOUT == 20

    def test_course_summary_ollama_calls_generate(self):
        from app.agents.course_summary_agent import CourseSummaryAgent
        agent = CourseSummaryAgent(provider="ollama")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "course summary"}
        mock_resp.raise_for_status.return_value = None

        with patch("app.agents.course_summary_agent.requests.post", return_value=mock_resp) as p:
            result = agent.summarize_course(["summary 1", "summary 2"], language="en")

        assert result == "course summary"
        payload = p.call_args[1]["json"]
        assert "/api/generate" in p.call_args[0][0]
        assert "num_predict" in payload.get("options", {})

    def test_course_summary_openai_calls_sdk(self):
        from app.agents.course_summary_agent import CourseSummaryAgent
        agent = CourseSummaryAgent(provider="openai")
        mock_choice = MagicMock()
        mock_choice.message.content = "openai course summary"
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]

        with patch("app.agents.course_summary_agent._OPENAI_API_KEY", "sk-test"), \
             patch("openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.chat.completions.create.return_value = mock_completion
            result = agent.summarize_course(["s1"], language="en")

        assert result == "openai course summary"

    def test_knowledge_map_ollama_includes_num_predict(self):
        from app.agents.knowledge_map_agent import KnowledgeMapAgent
        agent = KnowledgeMapAgent(provider="ollama")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "knowledge map"}
        mock_resp.raise_for_status.return_value = None

        with patch("app.agents.knowledge_map_agent.requests.post", return_value=mock_resp) as p:
            agent.generate_map("course summary", ["doc1 summary"], language="en")

        payload = p.call_args[1]["json"]
        assert "num_predict" in payload.get("options", {})

    def test_course_summary_raises_when_no_openai_key(self):
        from app.agents.course_summary_agent import CourseSummaryAgent
        agent = CourseSummaryAgent(provider="openai")
        with patch("app.agents.course_summary_agent._OPENAI_API_KEY", ""):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                agent.summarize_course(["s1"])


class TestAggregatesPromptLimits:
    """Input capping keeps prompts within bounds."""

    def test_course_summary_caps_at_max_summaries(self):
        from app.agents.course_summary_agent import CourseSummaryAgent, _MAX_SUMMARIES
        agent = CourseSummaryAgent(provider="ollama")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "ok"}
        mock_resp.raise_for_status.return_value = None

        too_many = [f"summary {i}" for i in range(_MAX_SUMMARIES + 5)]
        with patch("app.agents.course_summary_agent.requests.post", return_value=mock_resp) as p:
            agent.summarize_course(too_many)

        prompt = p.call_args[1]["json"]["prompt"]
        # Numbered input summaries look like "summary 0", "summary 1" etc.
        # The prompt template also contains "Short course summary" — so total
        # occurrences of "summary " is capped summaries + template occurrences.
        input_summary_occurrences = sum(
            1 for i in range(_MAX_SUMMARIES + 5) if f"summary {i}" in prompt
        )
        assert input_summary_occurrences <= _MAX_SUMMARIES

    def test_knowledge_map_caps_combined_summaries(self):
        from app.agents.knowledge_map_agent import KnowledgeMapAgent, _MAX_SUMMARIES_CHARS
        agent = KnowledgeMapAgent(provider="ollama")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "ok"}
        mock_resp.raise_for_status.return_value = None

        # Create a summary that would be enormous when combined
        huge_summaries = ["x" * 3000] * 5
        with patch("app.agents.knowledge_map_agent.requests.post", return_value=mock_resp) as p:
            agent.generate_map("cs", huge_summaries)

        prompt = p.call_args[1]["json"]["prompt"]
        # The x-block in the prompt should be bounded
        assert len(prompt) < _MAX_SUMMARIES_CHARS + 1000  # some overhead for template text


class TestRefreshCourseAggregatesIsolation:
    """_refresh_course_aggregates: each step fails independently."""

    def _setup_db_mock(self, summaries):
        from app.models.summary import Summary as SummaryModel
        mock_db = MagicMock()
        mock_rows = []
        for text in summaries:
            row = MagicMock(spec=SummaryModel)
            row.summary_text = text
            mock_rows.append(row)
        mock_db.query.return_value.join.return_value.filter.return_value.all.return_value = mock_rows
        return mock_db

    def test_knowledge_map_runs_even_if_course_summary_fails(self):
        from app.routes.documents import _refresh_course_aggregates

        mock_db = self._setup_db_mock(["summary one", "summary two"])
        km_called = []

        with patch("app.routes.documents.CourseSummaryAgent") as MockCSA, \
             patch("app.routes.documents.KnowledgeMapAgent") as MockKMA:
            MockCSA.return_value.summarize_course.side_effect = Exception("course summary boom")
            MockKMA.return_value.generate_map.side_effect = lambda *a, **kw: km_called.append(True) or "km result"
            _refresh_course_aggregates(mock_db, "course-1", "en", doc_id="d1")

        assert len(km_called) == 1, "knowledge map must run even when course summary fails"

    def test_course_summary_runs_even_if_knowledge_map_would_fail(self):
        from app.routes.documents import _refresh_course_aggregates

        mock_db = self._setup_db_mock(["summary one"])
        cs_called = []

        with patch("app.routes.documents.CourseSummaryAgent") as MockCSA, \
             patch("app.routes.documents.KnowledgeMapAgent") as MockKMA:
            MockCSA.return_value.summarize_course.side_effect = lambda *a, **kw: cs_called.append(True) or "cs"
            MockKMA.return_value.generate_map.side_effect = Exception("km boom")
            _refresh_course_aggregates(mock_db, "course-1", "en", doc_id="d1")

        assert len(cs_called) == 1

    def test_both_fail_without_raising(self):
        from app.routes.documents import _refresh_course_aggregates

        mock_db = self._setup_db_mock(["summary"])

        with patch("app.routes.documents.CourseSummaryAgent") as MockCSA, \
             patch("app.routes.documents.KnowledgeMapAgent") as MockKMA:
            MockCSA.return_value.summarize_course.side_effect = Exception("cs boom")
            MockKMA.return_value.generate_map.side_effect = Exception("km boom")
            # Must not raise — both failures are contained
            _refresh_course_aggregates(mock_db, "course-1", "en", doc_id="d1")

    def test_skipped_when_no_summaries(self):
        from app.routes.documents import _refresh_course_aggregates

        mock_db = self._setup_db_mock([])
        cs_called = []

        with patch("app.routes.documents.CourseSummaryAgent") as MockCSA:
            MockCSA.return_value.summarize_course.side_effect = lambda *a, **kw: cs_called.append(1)
            _refresh_course_aggregates(mock_db, "course-1", "en", doc_id="d1")

        assert len(cs_called) == 0

    def test_logs_per_step_started_and_completed(self, caplog):
        import logging
        from app.routes.documents import _refresh_course_aggregates

        mock_db = self._setup_db_mock(["summary text"])

        with patch("app.routes.documents.CourseSummaryAgent") as MockCSA, \
             patch("app.routes.documents.KnowledgeMapAgent") as MockKMA, \
             caplog.at_level(logging.INFO, logger="app.routes.documents"):
            MockCSA.return_value.summarize_course.return_value = "cs result"
            MockKMA.return_value.generate_map.return_value = "km result"
            _refresh_course_aggregates(mock_db, "course-1", "en", doc_id="d1")

        combined = " ".join(caplog.messages)
        assert "aggregates_refresh.started" in combined
        assert "aggregates_refresh.course_summary.started" in combined
        assert "aggregates_refresh.course_summary.completed" in combined
        assert "aggregates_refresh.knowledge_map.started" in combined
        assert "aggregates_refresh.knowledge_map.completed" in combined
        assert "aggregates_refresh.completed" in combined
