import os
import shutil
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict

import cv2
import numpy as np
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

import requests
from openai import OpenAI
from PyPDF2 import PdfReader

# Initialize logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Initialize an OpenAI client using the API key from environment variables.
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def preprocess_for_ocr(pil_image):
    img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    return Image.fromarray(thresh)

def extract_title_and_abstract(file_path: str) -> tuple[str, str]:
    """
    Extract title and abstract from the first 5 pages of a PDF.
    First, try to get the title from the PDF metadata.
    Then attempt to find an abstract using the word "abstract".
    """
    title = ""
    abstract = ""
    
    try:
        reader = PdfReader(file_path)
        metadata = reader.metadata or {}
        title = metadata.get('/Title', '').strip() if metadata.get('/Title') else ''
    except Exception as e:
        logger.warning(f"Metadata extraction failed: {e}")
    
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages[:5]):
            page_text = page.extract_text()
            if page_text:
                if not title:
                    for line in page_text.split('\n'):
                        if line.strip():
                            title = line.strip()
                            break
                if "abstract" in page_text.lower():
                    abstract_section = page_text.lower().split("abstract", 1)[1].strip()
                    abstract = abstract_section.split('\n\n', 1)[0].strip()
                    break
    return title, abstract

def extract_first_paragraph(file_path: str) -> str:
    """
    Fallback: Extract the first paragraph from page 1 (up to 200 words).
    """
    abstract = ""
    with pdfplumber.open(file_path) as pdf:
        if pdf.pages:
            page_text = pdf.pages[0].extract_text() or ""
            paragraphs = page_text.split("\n\n")
            if paragraphs:
                abstract = paragraphs[0].strip()
                words = abstract.split()
                if len(words) > 200:
                    abstract = " ".join(words[:200])
    return abstract

def extract_pdf_keywords(file_path: str) -> str:
    """
    Attempt to extract a 'Keywords' section from pages 1-3 of the PDF.
    Uses a regex to capture lines starting with "Keywords" or "Key words", optionally followed by a colon.
    Returns the extracted keywords or an empty string.
    """
    keywords_str = ""
    pattern = re.compile(r'^(keywords|key\s+words)[:\s]+(.*)', re.IGNORECASE)
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages[:3]):
            page_text = page.extract_text()
            if page_text:
                for line in page_text.split('\n'):
                    m = pattern.match(line.strip())
                    if m:
                        keywords_str = m.group(2).strip()
                        if keywords_str:
                            return keywords_str
    return keywords_str

def generate_keywords_from_title_abstract(title: str, abstract: str) -> str:
    """
    Use OpenAI to extract 3 to 6 key medical research keywords from the title and abstract.
    Returns a comma-separated list.
    """
    try:
        prompt = (
            "Extract 4 to 5 key medical research keywords from the following article information. "
            "Return the keywords as a comma-separated list.\n\n"
            f"Title: {title}\nAbstract: {abstract}"
        )
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        keywords = response.choices[0].message.content.strip()
        logger.info(f"Generated keywords from title and abstract: {keywords}")
        return keywords
    except Exception as e:
        logger.error(f"Error generating keywords from title and abstract: {e}")
        return ""

def generate_optimized_query(text: str) -> str:
    """
    Use OpenAI to generate an optimized search query from keywords.
    We ask for a concise query without complex boolean operators.
    """
    try:
        prompt = (
            "Based on the following medical research keywords, generate a concise search query "
            "that captures their essence. Do not use advanced boolean operators; just provide key terms.\n\n"
            f"Keywords: {text}"
        )
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        query = response.choices[0].message.content.strip()
        # Fallback: if the response does not include 'OR', then join the keywords with OR.
        if " OR " not in query:
            # Split the incoming comma separated string and join with " OR "
            query = " OR ".join([kw.strip() for kw in text.split(",") if kw.strip()])
        logger.info(f"Generated optimized query: {query}")
        return query
    except Exception as e:
        logger.error(f"Optimized query generation error: {e}")

def compute_keyword_match_count(keywords_str: str, article_title: str) -> int:
    """
    Splits the keywords_str (assumed comma-separated) into a list and returns
    the number of keywords that appear in the article_title (case-insensitive).
    """
    kw_list = [kw.strip().lower() for kw in keywords_str.split(',') if kw.strip()]
    title_lower = article_title.lower()
    match_count = sum(1 for kw in kw_list if kw in title_lower)
    return match_count

def compute_similarity(text1: str, text2: str) -> float:
    """
    Compute a simple similarity score between two texts based on word overlap.
    """
    set1 = set(text1.lower().split())
    set2 = set(text2.lower().split())
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2)

def search_semantic_scholar(query: str) -> List[Dict]:
    """
    Search Semantic Scholar using the given query.
    """
    articles = []
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={requests.utils.quote(query)}&limit=10&fields=title,authors,url"
    )
    logger.info(f"Searching Semantic Scholar with query: {query}")
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        articles = [{
            "title": article["title"],
            "authors": ", ".join(a["name"] for a in article.get("authors", [])),
            "link": article.get("url") or f"https://www.semanticscholar.org/paper/{article.get('paperId', '')}"
        } for article in data.get("data", [])]
    except Exception as e:
        logger.error(f"Semantic Scholar search failed: {e}")
        articles = []  # Return empty list on error.
    return articles

def search_pubmed(query: str) -> List[Dict]:
    """
    Search PubMed using the given query.
    """
    articles = []
    pubmed_url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
        f"db=pubmed&term={requests.utils.quote(query)}&retmode=json&retmax=10&sort=relevance"
    )
    logger.info(f"Searching PubMed with query: {query}")
    try:
        response = requests.get(pubmed_url, timeout=5)
        response.raise_for_status()
        data = response.json()
        pmids = data.get("esearchresult", {}).get("idlist", [])
        if pmids:
            details_url = (
                f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
                f"db=pubmed&id={','.join(pmids)}&retmode=json"
            )
            details_response = requests.get(details_url, timeout=5)
            details_response.raise_for_status()
            details_data = details_response.json()
            result_field = details_data.get("result", {})
            if isinstance(result_field, list):
                for article in result_field:
                    authors = ", ".join(a["name"] for a in article.get("authors", [])) if "authors" in article else "Unknown"
                    articles.append({
                        "title": article.get("title", "Untitled"),
                        "authors": authors,
                        "link": f"https://pubmed.ncbi.nlm.nih.gov/{article.get('uid', '')}/"
                    })
            else:
                for pmid in pmids:
                    article = result_field.get(pmid, {})
                    if article:
                        authors = ", ".join(a["name"] for a in article.get("authors", [])) if "authors" in article else "Unknown"
                        articles.append({
                            "title": article.get("title", "Untitled"),
                            "authors": authors,
                            "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                        })
    except Exception as e:
        logger.error(f"PubMed search failed: {e}")
        articles = []  # Return empty list on error.
    return articles

def search_similar_articles_from_pdf(file_path: str, uploaded_title: str = None) -> Dict:
    """
    Search for similar articles from a PDF.
    If a 'Keywords' section is found in pages 1-3, use it.
    Otherwise, extract the title and abstract (or first paragraph) and ask GPT to generate keywords.
    Then, use the resulting keywords to generate an optimized query, search external databases,
    deduplicate, and re–rank articles based on partial keyword matching.
    Returns a dict with both 'keywords_used' and 'similar_articles'.
    """
    keywords_str = extract_pdf_keywords(file_path)
    if keywords_str:
        logger.info(f"Using extracted keywords: {keywords_str}")
    else:
        logger.info("No 'Keywords' section found in pages 1-3. Falling back to abstract extraction.")
        title, abstract = extract_title_and_abstract(file_path)
        if not abstract:
            abstract = extract_first_paragraph(file_path)
        if title or abstract:
            keywords_str = generate_keywords_from_title_abstract(title, abstract)
        else:
            logger.info("No title or abstract available for keyword generation.")
            return {'keywords_used': "", 'similar_articles': []}
    
    optimized_query = generate_optimized_query(keywords_str)
    if not optimized_query:
        optimized_query = " ".join(keywords_str.split()[:5])
        logger.info(f"Falling back to basic query: {optimized_query}")
    
    articles_ss = search_semantic_scholar(optimized_query)
    articles_pm = search_pubmed(optimized_query)
    combined_articles = articles_ss + articles_pm

    unique_articles = {}
    for article in combined_articles:
        article_title = article.get("title", "").strip()
        if not article_title:
            continue
        key = article_title.lower()
        if uploaded_title and uploaded_title.lower().strip() in key:
            continue
        if key in unique_articles:
            continue
        unique_articles[key] = article

    ranked_articles = []
    for article in unique_articles.values():
        # Count the number of keywords that appear in the article title.
        match_count = compute_keyword_match_count(keywords_str, article.get("title", ""))
        ranking_score = match_count if match_count > 0 else compute_similarity(keywords_str, article.get("title", ""))
        article["ranking_score"] = ranking_score
        ranked_articles.append(article)
    
    ranked_articles.sort(key=lambda x: x["ranking_score"], reverse=True)
    top_articles = ranked_articles[:5]
    logger.info(f"Found {len(top_articles)} similar articles after re-ranking.")
    return {'keywords_used': keywords_str, 'similar_articles': top_articles}
