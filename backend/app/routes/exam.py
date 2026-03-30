import json
import random
from collections import defaultdict
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.sql import func

from app.db.database import get_db
from app.models.exam_question import ExamQuestion
from app.models.exam_simulation import ExamSimulation
from app.models.exam_simulation_question import ExamSimulationQuestion
from app.schemas.exam import (
    ExamQuestionCreate,
    ExamQuestionResponse,
    GenerateSimulationRequest,
    GenerateSimulationResponse,
    SimulationQuestionResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    SimulationResultResponse,
    TopicPerformanceItem,
)

router = APIRouter(prefix="/exam", tags=["Exam"])

def _normalize_free_text_answer(value: Optional[str]) -> str:
    value = (value or "").strip()
    value = " ".join(value.split())
    return value.casefold()



def _parse_options(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _question_to_response(q: ExamQuestion) -> ExamQuestionResponse:
    return ExamQuestionResponse(
        id=q.id,
        source_type=q.source_type,
        course_id=q.course_id,
        lecture_id=q.lecture_id,
        topic=q.topic,
        difficulty=q.difficulty,
        question_type=q.question_type,
        question_text=q.question_text,
        options=_parse_options(q.options_json),
        correct_answer_text=q.correct_answer_text,
        correct_answer_index=q.correct_answer_index,
        explanation=q.explanation,
        source_ref=q.source_ref,
        language=q.language,
        is_active=q.is_active,
    )


@router.post("/questions", response_model=ExamQuestionResponse)
def create_question(payload: ExamQuestionCreate, db: Session = Depends(get_db)):
    q = ExamQuestion(
        source_type=payload.source_type,
        course_id=payload.course_id,
        lecture_id=payload.lecture_id,
        topic=payload.topic,
        difficulty=payload.difficulty,
        question_type=payload.question_type,
        question_text=payload.question_text,
        options_json=json.dumps(payload.options or [], ensure_ascii=False) if payload.options else None,
        correct_answer_text=payload.correct_answer_text,
        correct_answer_index=payload.correct_answer_index,
        explanation=payload.explanation,
        source_ref=payload.source_ref,
        language=payload.language,
        is_active=payload.is_active,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _question_to_response(q)


@router.get("/questions", response_model=List[ExamQuestionResponse])
def list_questions(
    topic: Optional[str] = None,
    difficulty: Optional[str] = None,
    language: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(ExamQuestion).filter(ExamQuestion.is_active == True)

    if topic:
        query = query.filter(ExamQuestion.topic == topic)
    if difficulty and difficulty != "mixed":
        query = query.filter(ExamQuestion.difficulty == difficulty)
    if language:
        query = query.filter(ExamQuestion.language == language)

    results = query.order_by(desc(ExamQuestion.created_at)).all()
    return [_question_to_response(q) for q in results]


@router.post("/simulations/generate", response_model=GenerateSimulationResponse)
def generate_simulation(payload: GenerateSimulationRequest, db: Session = Depends(get_db)):
    query = db.query(ExamQuestion).filter(
        ExamQuestion.is_active == True,
        ExamQuestion.question_type == "mcq"
    )

    if payload.language:
        query = query.filter(ExamQuestion.language == payload.language)

    if payload.topic:
        query = query.filter(ExamQuestion.topic == payload.topic)

    if payload.difficulty and payload.difficulty != "mixed":
        query = query.filter(ExamQuestion.difficulty == payload.difficulty)

    if payload.mode == "course_material" and payload.course_id:
        query = query.filter(ExamQuestion.course_id == payload.course_id)

    if payload.mode == "full":
        if not payload.include_course_material and payload.include_public_bank:
            query = query.filter(ExamQuestion.source_type == "public_bank")
        elif payload.include_course_material and not payload.include_public_bank:
            query = query.filter(ExamQuestion.source_type != "public_bank")

    candidates = query.all()

    if not candidates:
        raise HTTPException(status_code=404, detail="No questions found for the selected filters")

    random.shuffle(candidates)
    selected = candidates[: payload.question_count]

    simulation = ExamSimulation(
        course_id=payload.course_id,
        mode=payload.mode,
        topic=payload.topic,
        difficulty=payload.difficulty,
        question_count=len(selected),
        status="in_progress",
    )
    db.add(simulation)
    db.commit()
    db.refresh(simulation)

    response_questions = []

    for idx, q in enumerate(selected, start=1):
        sq = ExamSimulationQuestion(
            simulation_id=simulation.id,
            question_id=q.id,
            display_order=idx,
        )
        db.add(sq)
        db.commit()
        db.refresh(sq)

        response_questions.append(
            SimulationQuestionResponse(
                simulation_question_id=sq.id,
                question_id=q.id,
                topic=q.topic,
                difficulty=q.difficulty,
                question_type=q.question_type,
                question_text=q.question_text,
                options=_parse_options(q.options_json),
            )
        )

    return GenerateSimulationResponse(
        simulation_id=simulation.id,
        question_count=len(response_questions),
        questions=response_questions,
    )


@router.get("/simulations/{simulation_id}", response_model=GenerateSimulationResponse)
def get_simulation(simulation_id: str, db: Session = Depends(get_db)):
    simulation = db.query(ExamSimulation).filter(ExamSimulation.id == simulation_id).first()
    if not simulation:
        raise HTTPException(status_code=404, detail="Simulation not found")

    rows = (
        db.query(ExamSimulationQuestion, ExamQuestion)
        .join(ExamQuestion, ExamSimulationQuestion.question_id == ExamQuestion.id)
        .filter(ExamSimulationQuestion.simulation_id == simulation_id)
        .order_by(ExamSimulationQuestion.display_order.asc())
        .all()
    )

    questions = []
    for sq, q in rows:
        questions.append(
            SimulationQuestionResponse(
                simulation_question_id=sq.id,
                question_id=q.id,
                topic=q.topic,
                difficulty=q.difficulty,
                question_type=q.question_type,
                question_text=q.question_text,
                options=_parse_options(q.options_json),
            )
        )

    return GenerateSimulationResponse(
        simulation_id=simulation.id,
        question_count=len(questions),
        questions=questions,
    )


@router.post("/simulations/{simulation_id}/answer", response_model=SubmitAnswerResponse)
def submit_answer(simulation_id: str, payload: SubmitAnswerRequest, db: Session = Depends(get_db)):
    sq = (
        db.query(ExamSimulationQuestion)
        .filter(
            ExamSimulationQuestion.id == payload.simulation_question_id,
            ExamSimulationQuestion.simulation_id == simulation_id,
        )
        .first()
    )

    if not sq:
        raise HTTPException(status_code=404, detail="Simulation question not found")

    q = db.query(ExamQuestion).filter(ExamQuestion.id == sq.question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    is_correct = False

    if q.question_type == "mcq":
        if payload.user_answer_index is None:
            raise HTTPException(status_code=400, detail="user_answer_index is required for mcq")
        is_correct = payload.user_answer_index == q.correct_answer_index
        sq.user_answer_index = payload.user_answer_index
    else:
        answer_text = (payload.user_answer_text or "").strip()
        sq.user_answer_text = answer_text
        is_correct = _normalize_free_text_answer(answer_text) == _normalize_free_text_answer(q.correct_answer_text)

    sq.is_correct = is_correct
    sq.feedback = q.explanation
    sq.answered_at = func.now()

    db.commit()

    return SubmitAnswerResponse(
        is_correct=is_correct,
        correct_answer_index=q.correct_answer_index,
        correct_answer_text=q.correct_answer_text,
        explanation=q.explanation,
    )


@router.post("/simulations/{simulation_id}/finish", response_model=SimulationResultResponse)
def finish_simulation(simulation_id: str, db: Session = Depends(get_db)):
    simulation = db.query(ExamSimulation).filter(ExamSimulation.id == simulation_id).first()
    if not simulation:
        raise HTTPException(status_code=404, detail="Simulation not found")

    rows = (
        db.query(ExamSimulationQuestion, ExamQuestion)
        .join(ExamQuestion, ExamSimulationQuestion.question_id == ExamQuestion.id)
        .filter(ExamSimulationQuestion.simulation_id == simulation_id)
        .all()
    )

    score = 0
    max_score = len(rows)
    topic_stats = defaultdict(lambda: {"correct": 0, "wrong": 0})

    for sq, q in rows:
        if sq.is_correct:
            score += 1
            topic_stats[q.topic]["correct"] += 1
        else:
            topic_stats[q.topic]["wrong"] += 1

    weak_topics = sorted(
        topic_stats.keys(),
        key=lambda t: topic_stats[t]["wrong"],
        reverse=True
    )
    weak_topics = [t for t in weak_topics if topic_stats[t]["wrong"] > 0][:5]

    simulation.status = "completed"
    simulation.score = score
    simulation.max_score = max_score
    simulation.completed_at = func.now()
    db.commit()

    percentage = round((score / max_score) * 100, 2) if max_score else 0.0

    return SimulationResultResponse(
        score=score,
        max_score=max_score,
        percentage=percentage,
        weak_topics=weak_topics,
    )


@router.get("/performance/topics", response_model=List[TopicPerformanceItem])
def get_topic_performance(db: Session = Depends(get_db)):
    rows = (
        db.query(ExamSimulationQuestion, ExamQuestion)
        .join(ExamQuestion, ExamSimulationQuestion.question_id == ExamQuestion.id)
        .filter(ExamSimulationQuestion.is_correct.isnot(None))
        .all()
    )

    topic_stats = defaultdict(lambda: {"correct": 0, "wrong": 0})

    for sq, q in rows:
        if sq.is_correct:
            topic_stats[q.topic]["correct"] += 1
        else:
            topic_stats[q.topic]["wrong"] += 1

    result = []
    for topic, stats in topic_stats.items():
        result.append(
            TopicPerformanceItem(
                topic=topic,
                correct_count=stats["correct"],
                wrong_count=stats["wrong"],
            )
        )

    result.sort(key=lambda x: x.wrong_count, reverse=True)
    return result
