"""
HTML cleaning utilities
"""
import re
from html import unescape


def clean_html_description(html_text: str) -> str:
    """
    Clean HTML from description field
    
    Args:
        html_text: HTML string like "<p><strong>text</strong></p>"
        
    Returns:
        Plain text
    """
    if not html_text:
        return ""
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', html_text)
    
    # Unescape HTML entities
    text = unescape(text)
    
    # Clean up whitespace
    text = ' '.join(text.split())
    
    return text.strip()
