import os
import json
import shutil
import uuid
import logging
from datetime import datetime, timedelta

from flask import Flask, send_from_directory, request, jsonify, session, Response, stream_with_context, copy_current_request_context
from flask_cors import CORS
from openai import OpenAI


from server import app
# Import the database functions from create_db.py.
from server import create_db

# Initialize Flask app.
app = Flask(__name__, static_folder="/app/client/build", static_url_path="/")
CORS(app)
app.secret_key = os.urandom(24)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.logger.setLevel(logging.INFO)

# Directories for audio and sessions.
AUDIO_DIR = "audio_files"
SESSIONS_DIR = "user_sessions"
os.makedirs(AUDIO_DIR, mode=0o777, exist_ok=True)
os.makedirs(SESSIONS_DIR, mode=0o777, exist_ok=True)

# Set up a scheduler for cleaning up old sessions.
from apscheduler.schedulers.background import BackgroundScheduler
scheduler = BackgroundScheduler()
scheduler.start()

def cleanup_old_sessions():
    now = datetime.now()
    if not os.path.exists(SESSIONS_DIR):
        return
    for session_id in os.listdir(SESSIONS_DIR):
        session_path = os.path.join(SESSIONS_DIR, session_id)
        last_accessed = datetime.fromtimestamp(os.path.getmtime(session_path))
        if (now - last_accessed) > timedelta(minutes=5):
            shutil.rmtree(session_path, ignore_errors=True)

scheduler.add_job(cleanup_old_sessions, 'interval', minutes=20)

# Initialize an OpenAI client (used for streaming responses).
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.before_request
def initialize_session():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        session_dir = os.path.join(SESSIONS_DIR, session['session_id'])
        session_data = os.path.join(session_dir, "uploaded-files")
        session_chroma = os.path.join(session_dir, "chroma")
        session['DATA_PATH'] = session_data
        session['CHROMA_PATH'] = session_chroma
        session['history'] = []
        session['uploaded_files'] = []
        session['has_documents'] = False

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_file = os.path.join(app.static_folder, path)
    if os.path.isfile(static_file):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/reset', methods=['POST'])
def reset_session():
    session.clear()
    session['session_id'] = str(uuid.uuid4())
    session_dir = os.path.join(SESSIONS_DIR, session['session_id'])
    session_data = os.path.join(session_dir, "uploaded-files")
    session_chroma = os.path.join(session_dir, "chroma")
    session['DATA_PATH'] = session_data
    session['CHROMA_PATH'] = session_chroma
    session['history'] = []
    session['uploaded_files'] = []
    session['has_documents'] = False
    return jsonify({'status': 'session reset'})

@app.route('/api/upload', methods=['POST'])
def handle_upload():
    app.logger.info("Received upload request")
    msg = ""
    has_documents = session.get('has_documents', False)
    if has_documents:
        session.clear()
        session['session_id'] = str(uuid.uuid4())
        session_dir = os.path.join(SESSIONS_DIR, session['session_id'])
        session_data = os.path.join(session_dir, "uploaded-files")
        session_chroma = os.path.join(session_dir, "chroma")
        session['DATA_PATH'] = session_data
        session['CHROMA_PATH'] = session_chroma
        session['history'] = []
        session['uploaded_files'] = []
        session['has_documents'] = False
        msg = "Previous file won't be referenced in the conversation."

    DATA_PATH = session.get('DATA_PATH')
    CHROMA_PATH = session.get('CHROMA_PATH')
    os.makedirs(DATA_PATH, mode=0o777, exist_ok=True)
    os.makedirs(CHROMA_PATH, mode=0o777, exist_ok=True)

    uploaded_file = request.files.get('file')
    if not uploaded_file:
        app.logger.warning("No file provided in request")
        return jsonify({'error': 'No file provided'}), 400

    if os.path.exists(DATA_PATH):
        shutil.rmtree(DATA_PATH)
    if os.path.exists(CHROMA_PATH):
        shutil.rmtree(CHROMA_PATH)
    os.makedirs(DATA_PATH, mode=0o777, exist_ok=True)
    os.makedirs(CHROMA_PATH, mode=0o777, exist_ok=True)

    file_path = os.path.join(DATA_PATH, uploaded_file.filename)
    app.logger.info(f"Saving file to: {file_path}")
    uploaded_file.save(file_path)
    
    try:
        app.logger.info("Processing file with create_db")
        create_db.create_data(DATA_PATH, CHROMA_PATH)
        session['uploaded_files'] = [uploaded_file.filename]
        session['has_documents'] = True
        session.modified = True

        app.logger.info("Extracting title and abstract")
        title, abstract = extract_title_and_abstract(file_path)
        app.logger.info(f"Extracted title: {title}")
        app.logger.info(f"Extracted abstract: {abstract[:100]}...")

        app.logger.info("Searching similar articles based on PDF content")
        result = search_similar_articles_from_pdf(file_path, title)
        similar_articles = result.get("similar_articles", [])
        extracted_keywords = result.get("keywords_used", "")
        # Optionally, convert the keywords string into an array.
        keywords_list = [kw.strip() for kw in extracted_keywords.split(',') if kw.strip()] if extracted_keywords else []

        app.logger.info(f"File '{uploaded_file.filename}' processed successfully")
        return jsonify({
            'response': f"📁 File '{uploaded_file.filename}' processed successfully!",
            'filename': uploaded_file.filename,
            'keywords': keywords_list,
            'similar_articles': similar_articles 
        })
    except Exception as e:
        app.logger.error(f"File processing error: {e}")
        return jsonify({'error': str(e)}), 500

# Streaming endpoint.
@app.route('/api/stream')
def stream_response():
    user_message = request.args.get("message")
    if not user_message:
        return Response("data: {'error': 'No message provided'}\n\n", mimetype="text/event-stream")

    CHROMA_PATH = session.get('CHROMA_PATH')
    has_documents = session.get('has_documents', False)
    uploaded_files = session.get('uploaded_files', [])
    history = session.get('history', [])
    
    app.logger.info(
        f"Stream request - Session ID: {session.get('session_id')}, Message: {user_message}, "
        f"Has documents: {has_documents}, Chroma path: {CHROMA_PATH}, "
        f"Uploaded files: {uploaded_files}, History length: {len(history)}"
    )
    
    def format_history(history: list) -> str:
        formatted = []
        for msg in history[1:]:
            role = "User" if msg['role'] == 'user' else "Assistant"
            formatted.append(f"{role}: {msg['content']}")
        return "\n".join(formatted)

    @copy_current_request_context
    def generate():
        try:
            prompt_sections = []
            rag_context = ""
            if has_documents and CHROMA_PATH and os.path.exists(CHROMA_PATH):
                app.logger.info(f"Querying Chroma database at: {CHROMA_PATH} for message: {user_message}")
                relevant_docs = create_db.query_collection(query_text=user_message, chroma_path=CHROMA_PATH, k=5)
                app.logger.info(f"Retrieved {len(relevant_docs)} documents from Chroma")
                if relevant_docs:
                    rag_context = "\n".join([doc.page_content for doc in relevant_docs])
                    prompt_sections.append(f"DOCUMENT CONTEXT:\n{rag_context}")
                else:
                    app.logger.warning("No relevant documents found in Chroma")
            else:
                app.logger.warning("No documents available or invalid Chroma path")

            if history:
                formatted_history = format_history(history)
                app.logger.info(f"Conversation history included:\n{formatted_history}")
                prompt_sections.append(f"CONVERSATION HISTORY:\n{formatted_history}")

            prompt_sections.append(f"USER QUESTION: {user_message}")
            final_prompt = "\n\n".join(prompt_sections)
            app.logger.info(f"Final prompt sent to OpenAI:\n{final_prompt}")

            system_message = (
                "You are a helpful assistant specialized in medical research. "
                "Use the 'CONVERSATION HISTORY' provided in the prompt to maintain context and continuity across messages. "
                "If 'DOCUMENT CONTEXT' is provided, use it to answer questions related to the uploaded PDF. "
                "If no 'DOCUMENT CONTEXT' is provided and the question requires document-specific information, "
                "respond with: 'Please upload the PDF file you would like me to assist you with regarding medical research. Thank you!' "
                "For general questions not requiring documents, provide a full and complete answer, referencing the conversation history if relevant. "
                "Format your responses using clean, single-column Markdown for clarity: use `-` for bullet points, ** for bold text, and `\\n` for line breaks. "
                "Ensure responses are left-aligned, concise, and free of extra whitespace or HTML formatting."
            )

            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": final_prompt}
            ]

            full_response = []
            stream = client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                stream=True
            )

            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield f"data: {json.dumps({'type': 'stream', 'content': content})}\n\n"
                    full_response.append(content)

            markdown_response = ''.join(full_response).strip()
            yield f"data: {json.dumps({'type': 'final', 'content': markdown_response})}\n\n"

            session['history'] = session.get('history', []) + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": markdown_response}
            ]
            session.modified = True

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            app.logger.error(f"Stream error: {str(e)}")

    return Response(stream_with_context(generate()), mimetype="text/event-stream")

# Audio transcription endpoint.
@app.route('/api/transcribe', methods=['POST'])
def transcribe_audio():
    temp_path = os.path.join(AUDIO_DIR, f"{uuid.uuid4()}.webm")
    try:
        audio_file = request.files['audio']
        audio_file.save(temp_path)
        with open(temp_path, "rb") as audio:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio,
                response_format="text"
            )
        return jsonify({'text': transcription, 'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# Endpoint to get the current session ID.
@app.route('/api/get_session_id', methods=['GET'])
def get_session_id():
    return jsonify({'session_id': session.get('session_id')})

# Fallback error handler.
@app.errorhandler(404)
def not_found(e):
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', use_reloader=True, port=5000, threaded=True)
