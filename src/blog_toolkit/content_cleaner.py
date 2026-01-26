"""HTML content cleaning utilities."""

import logging
import re
from html import unescape
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def is_html(content: Optional[str]) -> bool:
    """
    Detect if content contains HTML markup.
    
    Args:
        content: Content string to check
    
    Returns:
        True if content appears to contain HTML, False otherwise
    """
    if not content:
        return False
    
    # Simple heuristic: look for HTML tags
    # Check for common HTML patterns
    html_pattern = re.compile(r'<[a-z][\s\S]*?>', re.IGNORECASE)
    return bool(html_pattern.search(content))


def clean_html(html_content: str, preserve_structure: bool = True) -> str:
    """
    Convert HTML content to clean plain text.
    
    Args:
        html_content: HTML content to clean
        preserve_structure: If True, preserve paragraph breaks and list structure
    
    Returns:
        Clean plain text content
    """
    if not html_content:
        return ""
    
    try:
        # Parse HTML
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
            element.decompose()
        
        # Remove common ad/embed elements
        for element in soup.find_all(["iframe", "embed", "object", "ins"]):
            element.decompose()
        
        if preserve_structure:
            # Preserve structure: paragraphs, lists, headings
            text_parts = []
            
            for element in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre"]):
                text = element.get_text(separator=" ", strip=True)
                if text:
                    # Add extra spacing for block elements
                    if element.name in ["p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre"]:
                        text_parts.append(text)
                        text_parts.append("")  # Double newline for paragraphs
                    elif element.name == "li":
                        text_parts.append(f"• {text}")
                    else:
                        text_parts.append(text)
            
            # If no structured elements found, get all text
            if not text_parts:
                text = soup.get_text(separator="\n", strip=True)
            else:
                text = "\n".join(text_parts)
        else:
            # Simple text extraction
            text = soup.get_text(separator=" ", strip=True)
        
        # Decode HTML entities
        text = unescape(text)
        
        # Clean up whitespace
        # Replace multiple spaces with single space
        text = re.sub(r' +', ' ', text)
        # Replace multiple newlines (more than 2) with double newline
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Remove leading/trailing whitespace from each line
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        # Remove empty lines at start/end
        text = text.strip()
        
        return text
        
    except Exception as e:
        logger.error(f"Error cleaning HTML: {e}")
        # Fallback: try to extract text without parsing
        # Remove HTML tags using regex (less reliable but safer)
        text = re.sub(r'<[^>]+>', '', html_content)
        text = unescape(text)
        return text.strip()
