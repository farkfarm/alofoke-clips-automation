import pytest

from alofoke_clips.config import SelectionConfig
from alofoke_clips.detection import engagement_score, evaluate, select, text_similarity
from alofoke_clips.models import Analysis


def test_score_is_explainable(analysis):
    assert engagement_score(analysis.candidates[0]) == 79


def test_quality_candidate_selected(transcript, analysis):
    candidates = evaluate(analysis, transcript, SelectionConfig())
    chosen = select(candidates, "source", [], SelectionConfig())
    assert len(chosen) == 1
    assert (chosen[0].start, chosen[0].end) == (1.75, 17.25)


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"segment_ids": ["inventado"]}, "unknown"),
        ({"segment_ids": ["s000002", "s000001", "s000000"]}, "unordered"),
        ({"segment_ids": ["s000000", "s000002"]}, "contiguous"),
        ({"segment_ids": ["s000000", "s000000"]}, "repeated"),
        ({"confidence": 0.2}, "confidence"),
        (
            {
                "evidence": [
                    {"segment_id": "s000002", "quote": "Una acusación que no aparece en el texto"}
                ]
            },
            "evidence",
        ),
        ({"evidence": [{"segment_id": "missing", "quote": "evidencia inexistente"}]}, "evidence"),
    ],
)
def test_rejects_ungrounded_candidates(transcript, analysis, change, reason):
    raw = analysis.model_dump()
    raw["candidates"][0].update(change)
    candidate = evaluate(Analysis.model_validate(raw), transcript, SelectionConfig())[0]
    assert reason in candidate.decision


def test_abstention_returns_no_clips(transcript):
    analysis = Analysis(candidates=[], abstention_reason="Conversación rutinaria sin desenlace.")
    assert evaluate(analysis, transcript, SelectionConfig()) == []


@pytest.mark.parametrize("factor", ["context", "payoff"])
def test_context_and_payoff_required(transcript, analysis, factor):
    getattr(analysis.candidates[0].factors, factor).value = 1
    assert "context or payoff" in evaluate(analysis, transcript, SelectionConfig())[0].decision


def test_low_scores_never_force_minimum_quantity(transcript, analysis):
    for name in analysis.candidates[0].factors.__class__.model_fields:
        getattr(analysis.candidates[0].factors, name).value = 3
    candidates = evaluate(analysis, transcript, SelectionConfig())
    assert "threshold" in candidates[0].decision
    assert select(candidates, "hash", [], SelectionConfig()) == []


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"min_seconds": 20}, "duration"),
        ({"min_seconds": 10, "max_seconds": 14}, "duration"),
        ({"min_words": 200}, "speech"),
        ({"max_clips": 0}, "clip limit"),
    ],
)
def test_selection_limits(transcript, analysis, kwargs, reason):
    config = SelectionConfig(**kwargs)
    candidates = evaluate(analysis, transcript, config)
    select(candidates, "hash", [], config)
    assert reason in candidates[0].decision


def test_overlap_and_transcript_deduplication(transcript, analysis):
    repeated = Analysis(candidates=analysis.candidates * 2, abstention_reason="")
    candidates = evaluate(repeated, transcript, SelectionConfig())
    assert len(select(candidates, "hash", [], SelectionConfig())) == 1
    assert candidates[1].duplicate_of == candidates[0].id
    existing = [
        {
            "id": "old",
            "source_hash": "another-encoding",
            "start": 1,
            "end": 17,
            "text": candidates[0].text,
        }
    ]
    assert (
        select(
            evaluate(analysis, transcript, SelectionConfig()),
            "newhash",
            existing,
            SelectionConfig(),
        )
        == []
    )


def test_duplicate_normalization_preserves_comparison():
    assert text_similarity("¡Qué emoción, lo LOGRAMOS!", "que emocion lo logramos") == 1
    assert text_similarity("", "") == 0
    assert text_similarity("no hablamos del tema", "mañana sale el sol") < 0.88


def test_no_speech_probability_rejects_candidate(transcript, analysis):
    transcript.segments[1].no_speech_probability = 0.9
    assert "unreliable" in evaluate(analysis, transcript, SelectionConfig())[0].decision


def test_silence_ratio_rejects_sparse_candidate(transcript, analysis):
    transcript.segments[1].start = 100
    transcript.segments[1].end = 101
    transcript.segments[2].start = 102
    transcript.segments[2].end = 103
    transcript.segments[0].end = 3
    transcript.duration = 110
    config = SelectionConfig(max_seconds=120)
    assert "silence" in evaluate(analysis, transcript, config)[0].decision
