import os
import logging
from flask import Flask, request, jsonify, send_file
import psycopg2
import requests
import openai
from dotenv import load_dotenv
from io import BytesIO

# --- Basic Setup ---
load_dotenv() # Load environment variables from .env file for local development
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Environment Variables & Constants ---
# Use os.getenv to read environment variables set by Docker Compose
DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "db") # "db" is the service name in docker-compose

LOCAL_AI_URL = os.getenv("LOCAL_AI_URL", "http://local-ai:8080/v1")
INTERVIEW_DURATION_MINUTES = 20
MAX_QUESTIONS = 10 # To keep the interview concise

# --- OpenAI Client for LocalAI ---
# The openai library is configured to talk to our LocalAI container
client = openai.OpenAI(
    base_url=LOCAL_AI_URL,
    api_key="sk-111111111111111111111111111111111111111111111111" # LocalAI doesn't require a real key
)

# --- Database Connection ---
def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST
        )
        logging.info("Database connection successful.")
        return conn
    except psycopg2.OperationalError as e:
        logging.error(f"Could not connect to database: {e}")
        return None

# --- Core LLM Interaction Functions ---

def get_llm_response(messages, temperature=0.7):
    """Generic function to get a response from the LLM."""
    try:
        response = client.chat.completions.create(
            model="gpt-4", # This model name should match one configured in LocalAI
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"LLM API call failed: {e}")
        return "Sorry, I encountered an error and cannot respond right now."

# --- API Endpoints ---

@app.route('/api/start', methods=['POST'])
def start_interview():
    """Starts the interview, creates a record in the DB, and asks the first question."""
    data = request.get_json()
    user_name = data.get('name')
    user_experience = data.get('experience')

    if not user_name or not user_experience:
        return jsonify({"error": "Name and experience are required"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        with conn.cursor() as cur:
            # Create the interview record
            cur.execute(
                "INSERT INTO interviews (user_name, programming_experience) VALUES (%s, %s) RETURNING interview_id",
                (user_name, user_experience)
            )
            interview_id = cur.fetchone()[0]
            
            # Generate the first question using the LLM
            prompt = f"You are an AI interviewer. The candidate's name is {user_name} and their experience is: '{user_experience}'. Start the interview by greeting them and asking your first technical question based on their stated experience. Keep the question moderately difficult."
            
            first_question = get_llm_response([{"role": "system", "content": prompt}])

            # Save the first question
            cur.execute(
                "INSERT INTO questions_answers (interview_id, question_text) VALUES (%s, %s)",
                (interview_id, first_question)
            )
            conn.commit()
            logging.info(f"Started interview {interview_id} for {user_name}.")
            return jsonify({
                "interview_id": interview_id,
                "response": first_question,
                "interview_over": False
            })
    except Exception as e:
        logging.error(f"Error starting interview: {e}")
        conn.rollback()
        return jsonify({"error": "An internal error occurred"}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/chat', methods=['POST'])
def handle_chat():
    """Processes user's answer, evaluates it, and asks the next question."""
    data = request.get_json()
    interview_id = data.get('interview_id')
    user_answer = data.get('text')

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        with conn.cursor() as cur:
            # Get conversation history
            cur.execute(
                "SELECT question_text, answer_text FROM questions_answers WHERE interview_id = %s ORDER BY qa_id",
                (interview_id,)
            )
            history = cur.fetchall()
            
            # Update last question with user's answer
            cur.execute(
                "UPDATE questions_answers SET answer_text = %s WHERE qa_id = (SELECT MAX(qa_id) FROM questions_answers WHERE interview_id = %s)",
                (user_answer, interview_id)
            )

            # Check if max questions reached
            if len(history) >= MAX_QUESTIONS:
                # Perform final evaluation
                final_prompt_messages = [{"role": "system", "content": "You are an expert technical interviewer. Based on the following Q&A history, provide a concise final evaluation of the candidate's performance. Mention strengths and weaknesses."}]
                for q, a in history:
                    final_prompt_messages.append({"role": "assistant", "content": q})
                    final_prompt_messages.append({"role": "user", "content": a or "No answer provided."})
                
                final_evaluation = get_llm_response(final_prompt_messages)

                cur.execute(
                    "UPDATE interviews SET final_evaluation = %s WHERE interview_id = %s",
                    (final_evaluation, interview_id)
                )
                conn.commit()
                logging.info(f"Interview {interview_id} finished. Final evaluation generated.")
                return jsonify({
                    "response": "Thank you for your time. The interview is now complete.",
                    "final_evaluation": final_evaluation,
                    "interview_over": True
                })

            # If not over, generate next question based on history
            prompt_messages = [{"role": "system", "content": "You are an AI interviewer. Continue the interview based on the history. Ask the next logical question. Vary the difficulty. Do not repeat questions."}]
            for q, a in history:
                prompt_messages.append({"role": "assistant", "content": q})
                if a: prompt_messages.append({"role": "user", "content": a})
            
            next_question = get_llm_response(prompt_messages)

            # Save the new question
            cur.execute(
                "INSERT INTO questions_answers (interview_id, question_text) VALUES (%s, %s)",
                (interview_id, next_question)
            )
            conn.commit()
            logging.info(f"Asking next question for interview {interview_id}.")
            return jsonify({
                "response": next_question,
                "interview_over": False
            })
    except Exception as e:
        logging.error(f"Error in chat handler: {e}")
        conn.rollback()
        return jsonify({"error": "An internal error occurred"}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/speak', methods=['POST'])
def synthesize_speech():
    """Converts text to speech using LocalAI's TTS endpoint."""
    data = request.get_json()
    text_to_speak = data.get('text')
    
    try:
        # LocalAI's TTS endpoint is separate from the chat completions one
        tts_url = os.getenv("LOCAL_AI_URL", "http://local-ai:8080") + "/tts"
        response = requests.post(
            tts_url,
            json={
                "model": "tts-1", # This should match a TTS model configured in LocalAI
                "input": text_to_speak
            }
        )
        response.raise_for_status() # Raise an exception for bad status codes
        logging.info("Successfully synthesized speech.")
        return send_file(BytesIO(response.content), mimetype='audio/wav')
    except Exception as e:
        logging.error(f"TTS generation failed: {e}")
        return jsonify({"error": "Could not generate speech"}), 500


@app.route('/api/report/<int:interview_id>', methods=['GET'])
def download_report(interview_id):
    """Generates and serves a text file report of the interview."""
    conn = get_db_connection()
    if not conn:
        return "Database connection failed", 500
    
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_name, interview_date, programming_experience, final_evaluation FROM interviews WHERE interview_id = %s", (interview_id,))
            interview_data = cur.fetchone()
            
            cur.execute("SELECT question_text, answer_text FROM questions_answers WHERE interview_id = %s ORDER BY qa_id", (interview_id,))
            qa_data = cur.fetchall()

            report_content = f"Interview Report\n{'='*20}\n"
            report_content += f"Candidate: {interview_data[0]}\n"
            report_content += f"Date: {interview_data[1].strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            report_content += f"Stated Experience: {interview_data[2]}\n\n"
            report_content += f"--- Transcript ---\n\n"

            for i, (q, a) in enumerate(qa_data):
                report_content += f"Q{i+1}: {q}\n"
                report_content += f"A{i+1}: {a or 'No answer provided.'}\n\n"

            report_content += f"--- Final Evaluation ---\n{interview_data[3]}\n"
            
            buffer = BytesIO()
            buffer.write(report_content.encode('utf-8'))
            buffer.seek(0)
            
            logging.info(f"Generated report for interview {interview_id}.")
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f"interview_report_{interview_id}.txt",
                mimetype='text/plain'
            )
    except Exception as e:
        logging.error(f"Failed to generate report: {e}")
        return "Error generating report", 500
    finally:
        if conn:
            conn.close()


# --- Main Execution ---
if __name__ == '__main__':
    # Flask is run by a production-ready WSGI server like Gunicorn in the Dockerfile
    # For local testing, you can use: app.run(host='0.0.0.0', port=5000, debug=True)
    # The CMD in the Dockerfile will be different for production.
    # For simplicity, we will use the Flask development server.
    app.run(host='0.0.0.0', port=5000)
	