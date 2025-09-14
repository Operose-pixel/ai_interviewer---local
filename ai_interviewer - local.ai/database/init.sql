-- This ensures the tables are created with the correct ownership and encoding
CREATE TABLE interviews (
    interview_id SERIAL PRIMARY KEY,
    user_name VARCHAR(255) NOT NULL,
    interview_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    programming_experience TEXT,
    final_evaluation TEXT
);

CREATE TABLE questions_answers (
    qa_id SERIAL PRIMARY KEY,
    interview_id INTEGER REFERENCES interviews(interview_id),
    question_text TEXT NOT NULL,
    answer_text TEXT,
    evaluation TEXT,
    question_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
