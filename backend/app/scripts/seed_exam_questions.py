import json

from app.db.database import SessionLocal
from app.models.exam_question import ExamQuestion


QUESTIONS = [
    {
        "topic": "governance",
        "difficulty": "easy",
        "question_type": "mcq",
        "question_text": "מי אחראי לקביעת האסטרטגיה של החברה?",
        "options": ["המנכ״ל", "הדירקטוריון", "ועדת ביקורת", "סמנכ״ל כספים"],
        "correct_answer_text": "הדירקטוריון",
        "correct_answer_index": 1,
        "explanation": "הדירקטוריון אחראי לקביעת האסטרטגיה ולפיקוח על ההנהלה.",
    },
    {
        "topic": "governance",
        "difficulty": "easy",
        "question_type": "mcq",
        "question_text": "מהו תפקידו המרכזי של הדירקטוריון?",
        "options": [
            "ניהול שוטף של החברה",
            "פיקוח על הנהלת החברה וקביעת מדיניות",
            "ביצוע הנהלת חשבונות",
            "ניהול המכירות",
        ],
        "correct_answer_text": "פיקוח על הנהלת החברה וקביעת מדיניות",
        "correct_answer_index": 1,
        "explanation": "הדירקטוריון אינו מנהל את הפעילות השוטפת אלא מפקח ומכווין.",
    },
    {
        "topic": "board_responsibilities",
        "difficulty": "medium",
        "question_type": "mcq",
        "question_text": "איזו מן הבאות היא דוגמה לחובת זהירות של דירקטור?",
        "options": [
            "להימנע מניגוד עניינים בלבד",
            "לבחון מידע מהותי לפני קבלת החלטה",
            "להבטיח רווחיות בכל רבעון",
            "לחתום על כל חוזה מסחרי",
        ],
        "correct_answer_text": "לבחון מידע מהותי לפני קבלת החלטה",
        "correct_answer_index": 1,
        "explanation": "חובת הזהירות מחייבת הפעלת שיקול דעת ובחינת מידע רלוונטי.",
    },
    {
        "topic": "board_responsibilities",
        "difficulty": "medium",
        "question_type": "mcq",
        "question_text": "חובת אמונים של דירקטור משמעה בעיקר:",
        "options": [
            "נאמנות לאינטרס החברה",
            "ציות מלא למנכ״ל",
            "הימנעות מדיונים קשים",
            "תמיכה תמידית בבעל השליטה",
        ],
        "correct_answer_text": "נאמנות לאינטרס החברה",
        "correct_answer_index": 0,
        "explanation": "חובת האמונים מחייבת את הדירקטור לפעול לטובת החברה ולא לטובת אינטרס זר.",
    },
    {
        "topic": "audit_committee",
        "difficulty": "medium",
        "question_type": "mcq",
        "question_text": "מהו אחד מתפקידי ועדת הביקורת?",
        "options": [
            "לקבוע אסטרטגיית מכירות",
            "לפקח על תהליכי בקרה, ביקורת ודיווח",
            "לנהל גיוס עובדים",
            "לאשר כל הוצאה תפעולית",
        ],
        "correct_answer_text": "לפקח על תהליכי בקרה, ביקורת ודיווח",
        "correct_answer_index": 1,
        "explanation": "ועדת הביקורת עוסקת בפיקוח, בקרה ותהליכים מהותיים של ממשל תאגידי.",
    },
    {
        "topic": "audit_committee",
        "difficulty": "hard",
        "question_type": "mcq",
        "question_text": "מדוע חשוב שוועדת הביקורת תהיה בלתי תלויה ככל האפשר?",
        "options": [
            "כדי לקצר ישיבות",
            "כדי לשפר את אפקטיביות הפיקוח ולצמצם הטיות",
            "כדי להחליף את המנכ״ל",
            "כדי לנהל את הכספים ביום-יום",
        ],
        "correct_answer_text": "כדי לשפר את אפקטיביות הפיקוח ולצמצם הטיות",
        "correct_answer_index": 1,
        "explanation": "עצמאות הוועדה חיונית לפיקוח אמיתי ולמניעת ניגודי עניינים.",
    },
    {
        "topic": "financial_statements",
        "difficulty": "easy",
        "question_type": "mcq",
        "question_text": "אם הכנסות החברה הן 100, עלות המכר 60 והוצאות תפעול 20 — מהו הרווח התפעולי?",
        "options": ["10", "20", "30", "40"],
        "correct_answer_text": "20",
        "correct_answer_index": 1,
        "explanation": "100 פחות 60 פחות 20 שווה 20.",
    },
    {
        "topic": "financial_statements",
        "difficulty": "medium",
        "question_type": "mcq",
        "question_text": "איזה מסמך מציג את מצב הנכסים, ההתחייבויות וההון העצמי במועד מסוים?",
        "options": ["דוח רווח והפסד", "מאזן", "דוח תזרים מזומנים", "דוח דירקטוריון"],
        "correct_answer_text": "מאזן",
        "correct_answer_index": 1,
        "explanation": "המאזן מציג תמונת מצב בנקודת זמן.",
    },
    {
        "topic": "financial_statements",
        "difficulty": "hard",
        "question_type": "mcq",
        "question_text": "EBITDA גדל אך תזרים המזומנים התפעולי ירד. מה יכולה להיות סיבה לכך?",
        "options": [
            "ירידה בחוב פיננסי",
            "גידול במלאי או בלקוחות",
            "ירידה בהוצאות הנהלה",
            "שיפור בשיעור הרווח הגולמי",
        ],
        "correct_answer_text": "גידול במלאי או בלקוחות",
        "correct_answer_index": 1,
        "explanation": "שינויים בהון החוזר יכולים לפגוע בתזרים גם כשהרווחיות נראית טובה.",
    },
    {
        "topic": "risk_management",
        "difficulty": "medium",
        "question_type": "mcq",
        "question_text": "מהו תפקיד הדירקטוריון בניהול סיכונים?",
        "options": [
            "להתעלם מסיכונים תפעוליים",
            "לקבוע מסגרת פיקוח ולוודא שקיימים מנגנוני בקרה",
            "לנהל בעצמו כל סיכון תפעולי",
            "להשאיר את הנושא לרואי החשבון בלבד",
        ],
        "correct_answer_text": "לקבוע מסגרת פיקוח ולוודא שקיימים מנגנוני בקרה",
        "correct_answer_index": 1,
        "explanation": "הדירקטוריון קובע את מסגרת ניהול הסיכונים ומפקח עליה.",
    },
    {
        "topic": "risk_management",
        "difficulty": "hard",
        "question_type": "mcq",
        "question_text": "איזה מהבאים הוא סימן אפשרי לכשל בניהול סיכונים?",
        "options": [
            "דיווח שיטתי על חריגות מהותיות באיחור",
            "בקרה פנימית מתועדת",
            "מפת סיכונים מעודכנת",
            "דיוני ועדה מסודרים",
        ],
        "correct_answer_text": "דיווח שיטתי על חריגות מהותיות באיחור",
        "correct_answer_index": 0,
        "explanation": "איחור בדיווח על חריגות הוא סימן משמעותי לחולשה בבקרות ובפיקוח.",
    },
    {
        "topic": "strategy",
        "difficulty": "medium",
        "question_type": "mcq",
        "question_text": "מהו תפקיד הדירקטוריון בתהליך האסטרטגי?",
        "options": [
            "לבצע בפועל את כל תוכניות העבודה",
            "לאשר, לאתגר ולפקח על הכיוון האסטרטגי",
            "להימנע מהתערבות",
            "להחליף את תוכנית העבודה השנתית",
        ],
        "correct_answer_text": "לאשר, לאתגר ולפקח על הכיוון האסטרטגי",
        "correct_answer_index": 1,
        "explanation": "הדירקטוריון צריך לאתגר את ההנהלה ולפקח על הכיוון העסקי.",
    },
    {
        "topic": "strategy",
        "difficulty": "case",
        "question_type": "mcq",
        "question_text": "חברה שוקלת כניסה לשוק חדש עם סיכון רגולטורי גבוה. מה השאלה המרכזית שעל הדירקטוריון לשאול תחילה?",
        "options": [
            "האם אפשר לפרסם מהר יותר מהמתחרים?",
            "מה פרופיל הסיכון-סיכוי והאם קיימת היערכות מתאימה?",
            "האם המשרדים החדשים מעוצבים היטב?",
            "האם הצוות הקיים מרוצה מהמשכורות?",
        ],
        "correct_answer_text": "מה פרופיל הסיכון-סיכוי והאם קיימת היערכות מתאימה?",
        "correct_answer_index": 1,
        "explanation": "בדירקטוריון חשוב לבחון היתכנות, סיכונים, מוכנות ויכולת בקרה.",
    },
    {
        "topic": "corporate_law",
        "difficulty": "medium",
        "question_type": "mcq",
        "question_text": "עסקה עם בעל שליטה דורשת בדרך כלל:",
        "options": [
            "אישור סמנכ״ל כספים בלבד",
            "אישור ועדת ביקורת והדירקטוריון",
            "אישור כל מנהלי המחלקות",
            "אישור בנק החברה בלבד",
        ],
        "correct_answer_text": "אישור ועדת ביקורת והדירקטוריון",
        "correct_answer_index": 1,
        "explanation": "עסקאות עם בעלי שליטה כפופות למנגנוני אישור מחמירים.",
    },
    {
        "topic": "corporate_law",
        "difficulty": "hard",
        "question_type": "mcq",
        "question_text": "כאשר חברה מתקרבת לחדלות פירעון, על הדירקטוריון:",
        "options": [
            "להתמקד רק בהגדלת מכירות",
            "לבחון בזהירות את מצבה, התחייבויותיה והשלכות החלטותיו",
            "להימנע מכל החלטה",
            "להעביר מיד הכול לבעל השליטה",
        ],
        "correct_answer_text": "לבחון בזהירות את מצבה, התחייבויותיה והשלכות החלטותיו",
        "correct_answer_index": 1,
        "explanation": "במצבי משבר וחדלות פירעון חובת הזהירות גוברת ויש לבחון השלכות על נושים וחברה.",
    },
    {
        "topic": "conflict_of_interest",
        "difficulty": "medium",
        "question_type": "mcq",
        "question_text": "מה דירקטור צריך לעשות כאשר עולה חשש לניגוד עניינים אישי?",
        "options": [
            "להסתיר את המידע עד סוף הדיון",
            "לגלות את הניגוד ולפעול בהתאם לכללי הממשל",
            "להחליט לבד",
            "לבקש מהמנכ״ל להחליט במקומו",
        ],
        "correct_answer_text": "לגלות את הניגוד ולפעול בהתאם לכללי הממשל",
        "correct_answer_index": 1,
        "explanation": "שקיפות וגילוי הם תנאי בסיסי לטיפול נכון בניגודי עניינים.",
    },
    {
        "topic": "conflict_of_interest",
        "difficulty": "hard",
        "question_type": "mcq",
        "question_text": "דירקטור משתמש במידע מהותי לא פומבי כדי לקנות מניות. מה המשמעות העיקרית?",
        "options": [
            "חיסכון מס",
            "הפרת חובת אמונים ושימוש במידע פנים",
            "ניהול סיכונים תקין",
            "אין בעיה אם רצה בטובת החברה",
        ],
        "correct_answer_text": "הפרת חובת אמונים ושימוש במידע פנים",
        "correct_answer_index": 1,
        "explanation": "שימוש במידע מהותי לא פומבי עלול להוות עבירה והפרת חובות יסוד.",
    },
    {
        "topic": "board_responsibilities",
        "difficulty": "case",
        "question_type": "mcq",
        "question_text": "המנכ״ל מבקש לאשר עסקה גדולה עוד באותו ערב, ללא חומר רקע מספק. מהי התגובה הנכונה ביותר של דירקטור אחראי?",
        "options": [
            "לאשר מיד כדי לא לעכב את העסקה",
            "לדרוש מידע מספק ולדחות החלטה עד לבחינה נאותה",
            "להשאיר את ההחלטה לבעל השליטה",
            "להצביע לפי מה שרוב הדירקטורים עושים",
        ],
        "correct_answer_text": "לדרוש מידע מספק ולדחות החלטה עד לבחינה נאותה",
        "correct_answer_index": 1,
        "explanation": "חובת הזהירות מחייבת בסיס מידע סביר לפני קבלת החלטה מהותית.",
    },
    {
        "topic": "financial_statements",
        "difficulty": "case",
        "question_type": "mcq",
        "question_text": "חברה מציגה רווח נקי יציב אך תזרים מזומנים שלילי לאורך זמן. מה צריכה להיות דאגת הדירקטוריון?",
        "options": [
            "אין צורך לדון בכך כל עוד יש רווח",
            "יש לבחון איכות רווח, נזילות ויכולת עמידה בהתחייבויות",
            "יש להתמקד רק ביחסי ציבור",
            "זהו נושא של הנהלת חשבונות בלבד",
        ],
        "correct_answer_text": "יש לבחון איכות רווח, נזילות ויכולת עמידה בהתחייבויות",
        "correct_answer_index": 1,
        "explanation": "רווח חשבונאי אינו תחליף לנזילות ולבחינת תזרים בפועל.",
    },
]

# שכפול חכם ליצירת מאגר גדול יותר
EXPANDED_QUESTIONS = []
for i in range(8):
    for q in QUESTIONS:
        item = dict(q)
        item["question_text"] = f'{q["question_text"]} (גרסה {i + 1})'
        EXPANDED_QUESTIONS.append(item)


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0

        for q in EXPANDED_QUESTIONS:
            existing = (
                db.query(ExamQuestion)
                .filter(ExamQuestion.question_text == q["question_text"])
                .first()
            )

            if existing:
                skipped += 1
                continue

            row = ExamQuestion(
                source_type="public_bank",
                course_id=None,
                lecture_id=None,
                topic=q["topic"],
                difficulty=q["difficulty"],
                question_type=q["question_type"],
                question_text=q["question_text"],
                options_json=json.dumps(q.get("options") or [], ensure_ascii=False),
                correct_answer_text=q["correct_answer_text"],
                correct_answer_index=q.get("correct_answer_index"),
                explanation=q.get("explanation"),
                source_ref="internal_seed_v1",
                language="he",
                is_active=True,
            )
            db.add(row)
            inserted += 1

        db.commit()
        total = db.query(ExamQuestion).count()
        print(f"Seed completed successfully. Inserted: {inserted}, Skipped duplicates: {skipped}, Total questions in DB: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
