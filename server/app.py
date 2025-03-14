import json
import shutil
from os import makedirs, path
from flask import Flask, send_from_directory, request, jsonify, session, Response, stream_with_context, copy_current_request_context
from flask_cors import CORS
import os
from openai import OpenAI
from server import create_db
import uuid
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import cv2
import numpy as np
import requests
import fitz
import logging
from typing import List, Dict

app = Flask(__name__, static_folder="/app/client/build", static_url_path="/")

# CORS setup - Already good, but explicitly allow localhost:3000 for React dev
CORS(app)  
# Session configuration
app.secret_key = os.urandom(24)  # Secure key for session
app.config['SESSION_COOKIE_SECURE'] = True  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 'None' works for cross-origin, but Lax is safer for dev
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JS access to session cookie
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB upload limit
app.logger.setLevel(logging.INFO)
# Load environment variables

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# Directories
AUDIO_DIR = "audio_files"
makedirs(AUDIO_DIR, mode=0o777, exist_ok=True)
SESSIONS_DIR = "user_sessions"
makedirs(SESSIONS_DIR, mode=0o777, exist_ok=True)

# Session cleanup scheduler
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

def preprocess_for_ocr(pil_image):
    img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    return Image.fromarray(thresh)

def extract_title_and_abstract(file_path: str) -> tuple[str, str]:
    """Extract title and abstract from the first 5 pages of a PDF."""
    title = ""
    abstract = ""
    
    # Try to get title from metadata using PyMuPDF
    try:
        doc = fitz.open(file_path)
        metadata = doc.metadata
        title = metadata.get('title', '').strip()
    except Exception as e:
        app.logger.warning(f"Metadata extraction failed: {e}")

    # Extract text from the first 5 pages
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages[:5]):
            page_text = page.extract_text()
            if page_text:
                # If title not found in metadata, use the first non-empty line
                if not title:
                    lines = page_text.split('\n')
                    for line in lines:
                        if line.strip():
                            title = line.strip()
                            break
                # Look for abstract
                if "abstract" in page_text.lower():
                    abstract_section = page_text.lower().split("abstract", 1)[1].strip()
                    abstract = abstract_section.split('\n\n', 1)[0].strip()
                    break
            else:
                # Fall back to OCR if text extraction fails
                try:
                    images = convert_from_path(file_path, first_page=i + 1, last_page=i + 1)
                    for image in images:
                        image = preprocess_for_ocr(image)
                        ocr_text = pytesseract.image_to_string(image, lang='eng', config='--psm 6 --oem 1')
                        if "abstract" in ocr_text.lower():
                            abstract_section = ocr_text.lower().split("abstract", 1)[1].strip()
                            abstract = abstract_section.split('\n\n', 1)[0].strip()
                            break
                except Exception as e:
                    app.logger.error(f"OCR error on page {i+1}: {e}")
    
    return title, abstract

def extract_keywords_with_openai(text: str) -> list[str]:
    """Extract 3-5 key medical research terms from the title and abstract using OpenAI."""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "user",
                "content": f"Extract 3 to 6 key medical research terms (e.g., diseases, molecules, concepts, materials, therapy) from this text (title and abstract combined): {text}. Return them as a comma-separated list."
            }]
        )
        keywords = response.choices[0].message.content.split(", ")
        return [k.strip() for k in keywords if k.strip()]
    except Exception as e:
        app.logger.error(f"OpenAI keyword extraction error: {e}")
        return []

def search_similar_articles(keywords: List[str], uploaded_title: str = None) -> List[Dict]:
    """Search Semantic Scholar and PubMed for relevant articles, ensuring uniqueness and excluding the uploaded article."""
    if not keywords or not any(k.strip() for k in keywords):
        app.logger.warning("No valid keywords provided for article search")
        return []

    all_articles = []
    seen_titles = set()  # For deduplication (case-insensitive)

    # Helper to add unique, relevant articles
    def add_unique_articles(articles: List[Dict], source: str):
        for article in articles:
            title_lower = article["title"].lower().strip()
            # Skip if already seen or matches uploaded article (if provided)
            if title_lower in seen_titles or (uploaded_title and uploaded_title.lower().strip() in title_lower):
                continue
            seen_titles.add(title_lower)
            all_articles.append(article)
            app.logger.info(f"Added article from {source}: {article['title']}")

    # 1. Semantic Scholar (AND logic)
    query = " ".join(keywords)
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={query}&limit=10&fields=title,authors,url"
    app.logger.info(f"Searching Semantic Scholar with query: {query}")
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        articles = [{
            "title": article["title"],
            "authors": ", ".join([a["name"] for a in article.get("authors", [])]),
            "link": article["url"] or f"https://www.semanticscholar.org/paper/{article['paperId']}"
        } for article in data.get("data", [])]
        add_unique_articles(articles, "Semantic Scholar (AND)")
    except Exception as e:
        app.logger.error(f"Semantic Scholar search failed: {e}")

    # Stop if we have 5 unique articles
    if len(all_articles) >= 5:
        app.logger.info(f"Stopping with {len(all_articles)} unique articles from Semantic Scholar")
        return all_articles[:5]

    # 2. Semantic Scholar (OR logic) - Broader search
    query_or = " OR ".join(keywords)
    url_or = f"https://api.semanticscholar.org/graph/v1/paper/search?query={query_or}&limit=10&fields=title,authors,url"
    app.logger.info(f"Searching Semantic Scholar with OR query: {query_or}")
    try:
        response = requests.get(url_or, timeout=5)
        response.raise_for_status()
        data = response.json()
        articles = [{
            "title": article["title"],
            "authors": ", ".join([a["name"] for a in article.get("authors", [])]),
            "link": article["url"] or f"https://www.semanticscholar.org/paper/{article['paperId']}"
        } for article in data.get("data", [])]
        add_unique_articles(articles, "Semantic Scholar (OR)")
    except Exception as e:
        app.logger.error(f"Semantic Scholar OR search failed: {e}")

    # Stop if we have 5 unique articles
    if len(all_articles) >= 5:
        app.logger.info(f"Stopping with {len(all_articles)} unique articles after Semantic Scholar OR")
        return all_articles[:5]

    # 3. PubMed
    pubmed_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={query}&retmode=json&retmax=10&sort=relevance"
    app.logger.info(f"Searching PubMed with query: {query}")
    try:
        response = requests.get(pubmed_url, timeout=5)
        response.raise_for_status()
        data = response.json()
        pmids = data.get("esearchresult", {}).get("idlist", [])
        if pmids:
            details_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={','.join(pmids)}&retmode=json"
            details_response = requests.get(details_url, timeout=5)
            details_response.raise_for_status()
            details_data = details_response.json()
            articles = []
            for pmid in pmids:
                article = details_data.get("result", {}).get(pmid, {})
                if article:
                    authors = ", ".join([author["name"] for author in article.get("authors", [])]) if "authors" in article else "Unknown"
                    articles.append({
                        "title": article.get("title", "Untitled"),
                        "authors": authors,
                        "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                    })
            add_unique_articles(articles, "PubMed")
    except Exception as e:
        app.logger.error(f"PubMed search failed: {e}")

    # Final result
    app.logger.info(f"Finished with {len(all_articles)} unique articles")
    return all_articles[:5] if len(all_articles) >= 5 else all_articles


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
    # First, try to serve static files (CSS, JS, images, etc.)
    static_file = os.path.join(app.static_folder, path)
    if os.path.isfile(static_file):
        return send_from_directory(app.static_folder, path)
    # If not a static file, serve index.html
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
        app.logger.info(f"Extracted abstract: {abstract[:100]}...")  # Limit abstract log length
        combined_text = f"{title}\n{abstract}" if abstract else title

        app.logger.info("Extracting keywords with OpenAI")
        keywords = extract_keywords_with_openai(combined_text) if combined_text else []
        app.logger.info(f"Extracted keywords: {keywords}")

        app.logger.info("Searching similar articles")
        similar_articles = search_similar_articles(keywords) if keywords else []
        app.logger.info(f"Similar articles: {similar_articles}")

        app.logger.info(f"File '{uploaded_file.filename}' processed successfully")
        return jsonify({
            'response': f"📁 File '{uploaded_file.filename}' processed successfully!",
            'filename': uploaded_file.filename,
            'keywords': keywords,
            'similar_articles': similar_articles 
        })
    except Exception as e:
        app.logger.error(f"File processing error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stream')
def stream_response():
    user_message = request.args.get("message")
    if not user_message:
        return Response("data: {'error': 'No message provided'}\n\n", mimetype="text/event-stream")

    CHROMA_PATH = session.get('CHROMA_PATH')
    has_documents = session.get('has_documents', False)
    uploaded_files = session.get('uploaded_files', [])
    history = session.get('history', [])
    
    app.logger.info(f"Stream request - Session ID: {session.get('session_id')}, Message: {user_message}, "
                    f"Has documents: {has_documents}, Chroma path: {CHROMA_PATH}, "
                    f"Uploaded files: {uploaded_files}, History length: {len(history)}")
    
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
                app.logger.warning("No documents available or Chroma path invalid")

            # Always include conversation history
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
                "Format your responses using clean, single-column Markdown for clarity: use `-` for bullet points (one per line, no extra spaces or tabs), `**` for bold text, and `\n` for line breaks. Ensure responses are left-aligned, concise, and free of extra whitespace, tabs, or column-like formatting. Do not use multiple spaces, tabs, or any HTML that could cause layout issues."
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

            # Send the raw OpenAI response as Markdown, preserving all formatting
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

@app.route('/api/get_session_id', methods=['GET'])
def get_session_id():
    return jsonify({'session_id': session.get('session_id')})

@app.errorhandler(404)
def not_found(e):
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', use_reloader=True, port=5000, threaded=True)