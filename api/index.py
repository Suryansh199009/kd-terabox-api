from flask import Flask, request, jsonify, Response
import os
import json
import logging
import re
import random
import time
import requests
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# ====== 🇮🇳 ==============
# # © Developer = WOODcraft 
# ========================
# Configuration
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2
PORT = 3000

# Supported domains
SUPPORTED_DOMAINS = [
    "terabox.com",
    "1024terabox.com",
    "teraboxapp.com",
    "teraboxlink.com",
    "terasharelink.com",
    "terafileshare.com",
    "www.1024tera.com",
    "1024tera.com",
    "1024tera.cn",
    "teraboxdrive.com",
    "dubox.com"
]

# Regex pattern for Terabox URLs
TERABOX_URL_REGEX = r'^https:\/\/(www\.)?(terabox\.com|1024terabox\.com|teraboxapp\.com|teraboxlink\.com|terasharelink\.com|terafileshare\.com|1024tera\.com|1024tera\.cn|teraboxdrive\.com|dubox\.com)\/(s|sharing\/link)\/[A-Za-z0-9_\-]+'

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# TESTED COOKIES (Updated 2024-06-23)
COOKIES = {
    'ndut_fmt': '082E0D57C65BDC31F6FF293F5D23164958B85D6952CCB6ED5D8A3870CB302BE7',
    'ndus': 'Y-wWXKyteHuigAhC03Fr4bbee-QguZ4JC6UAdqap',
    '__bid_n': '196ce76f980a5dfe624207',
    '__stripe_mid': '148f0bd1-59b1-4d4d-8034-6275095fc06f99e0e6',
    '__stripe_sid': '7b425795-b445-47da-b9db-5f12ec8c67bf085e26',
    'browserid': 'veWFJBJ9hgVgY0eI9S7yzv66aE28f3als3qUXadSjEuICKF1WWBh4inG3KAWJsAYMkAFpH2FuNUum87q',
    'csrfToken': 'wlv_WNcWCjBtbNQDrHSnut2h',
    'lang': 'en',
    'PANWEB': '1',
    'ab_sr': '1.0.1_NjA1ZWE3ODRiYjJiYjZkYjQzYjU4NmZkZGVmOWYxNDg4MjU3ZDZmMTg0Nzg4MWFlNzQzZDMxZWExNmNjYzliMGFlYjIyNWUzYzZiODQ1Nzg3NWM0MzIzNWNiYTlkYTRjZTc0ZTc5ODRkNzg4NDhiMTljOGRiY2I4MzY4ZmYyNTU5ZDE5NDczZmY4NjJhMDgyNjRkZDI2MGY5M2Q5YzIyMg=='
}

# FIXED HEADERS AS REQUESTED
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Priority': 'u=0, i',
}

def get_headers():
    """Return fixed headers as requested"""
    return HEADERS

def validate_terabox_url(url):
    """Validate Terabox URL format"""
    try:
        return re.match(TERABOX_URL_REGEX, url) is not None
    except Exception:
        return False

def make_request(url, method='GET', headers=None, params=None, allow_redirects=True, cookies=None):
    """Make HTTP request with retry logic"""
    session = requests.Session()
    retries = 0
    last_exception = None
    
    while retries < MAX_RETRIES:
        try:
            response = session.request(
                method,
                url,
                headers=headers or get_headers(),
                params=params,
                cookies=cookies,
                allow_redirects=allow_redirects,
                timeout=REQUEST_TIMEOUT
            )
            
            # Handle rate limiting
            if response.status_code in [403, 429, 503]:
                logger.warning(f"Rate limited ({response.status_code}), retrying...")
                time.sleep(RETRY_DELAY * (2 ** retries))
                retries += 1
                continue
                
            response.raise_for_status()
            return response
        except (requests.ConnectionError, requests.Timeout) as e:
            logger.warning(f"Connection error: {str(e)}")
            time.sleep(RETRY_DELAY * (2 ** retries))
            retries += 1
            last_exception = e
        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            if retries == MAX_RETRIES - 1:
                raise
            time.sleep(RETRY_DELAY)
            retries += 1
            last_exception = e
            
    raise Exception(f"Max retries exceeded. Last error: {str(last_exception)}")

def find_between(string, start, end):
    """Extract substring between two delimiters"""
    try:
        start_index = string.find(start) + len(start)
        end_index = string.find(end, start_index)
        return string[start_index:end_index]
    except Exception as e:
        logger.error(f"find_between error: {str(e)}")
        return None

def extract_tokens(html):
    """Extract jsToken and log_id from HTML content"""
    # Improved token extraction with regex as requested
    token_match = re.search(r'fn\(["\'](.*?)["\']\)', html)
    if not token_match:
        token_match = re.search(r'fn%28%22(.*?)%22%29', html)
    
    if not token_match:
        logger.error("Token extraction failed")
        raise Exception("Could not extract jsToken")
    
    js_token = token_match.group(1)
    
    # Improved log_id extraction
    log_id_match = re.search(r'dp-logid=([^&\'"]+)', html)
    if not log_id_match:
        logger.error("Log ID extraction failed")
        raise Exception("Could not extract log_id")
    
    log_id = log_id_match.group(1)

    return js_token, log_id

def get_surl(response_url):
    """Extract surl parameter from URL"""
    try:
        # First try to extract from URL parameters
        surl = find_between(response_url, 'surl=', '&')
        if surl:
            return surl
        
        # Then try to extract from path
        parsed = urlparse(response_url)
        if '/s/' in parsed.path:
            surl = parsed.path.split('/s/')[1].split('/')[0]
            return surl
        
        # Fallback to path parts
        path_parts = parsed.path.strip('/').split('/')
        if 's' in path_parts:
            s_index = path_parts.index('s')
            if len(path_parts) > s_index + 1:
                return path_parts[s_index + 1]
        
        # Final fallback to regex extraction
        surl_match = re.search(r'/(s|sharing/link)/([A-Za-z0-9_\-]+)', response_url)
        if surl_match:
            return surl_match.group(2)
        
        raise Exception("Could not extract surl from URL")
    except Exception as e:
        logger.error(f"surl extraction error: {str(e)}")
        raise

def get_direct_link(url, cookies):
    """Resolve direct download link by following redirects"""
    try:
        response = make_request(
            url,
            method='HEAD',
            allow_redirects=False,
            cookies=cookies
        )
        if 300 <= response.status_code < 400:
            return response.headers.get('Location', url)
        return url
    except Exception:
        return url

def process_terabox_url(url):
    """Process Terabox URL and return file information"""
    # Step 1: Fetch initial page
    response = make_request(url, cookies=COOKIES)
    html = response.text
    
    # Step 2: Extract tokens
    js_token, log_id = extract_tokens(html)
    
    # Step 3: Get surl
    surl = get_surl(response.url)
    
    # Step 4: Prepare API request
    params = {
        'app_id': '250528',
        'web': '1',
        'channel': 'dubox',
        'clienttype': '0',
        'jsToken': js_token,
        'dplogid': log_id,
        'page': '1',
        'num': '20',
        'order': 'time',
        'desc': '1',
        'site_referer': response.url,
        'shorturl': surl,
        'root': '1'
    }
    
    # Step 5: Fetch file list
    response2 = make_request(
        'https://www.1024tera.com/share/list',
        params=params,
        cookies=COOKIES
    )
    response_data2 = response2.json()
    
    # Check if valid file list exists
    if 'list' not in response_data2 or not response_data2['list']:
        logger.error("No files found in API response")
        raise Exception("No files found in shared link")
    
    file_list = response_data2['list']
    logger.info(f"Found {len(file_list)} files")
    
    # Step 6: Handle directories (folder handling as requested)
    if file_list and file_list[0].get('isdir') == "1":
        folder_params = params.copy()
        folder_params.update({
            'dir': file_list[0]['path'],
            'order': 'asc',
            'by': 'name',
        })
        folder_params.pop('desc', None)
        folder_params.pop('root', None)
        
        # Fetch folder contents
        folder_response = make_request(
            'https://www.1024tera.com/share/list',
            params=folder_params,
            cookies=COOKIES
        )
        folder_data = folder_response.json()
        
        if 'list' not in folder_data or not folder_data['list']:
            logger.error("No files found in folder")
            raise Exception("No files found in directory")
        
        # Process all files in folder (skip sub-folders)
        folder_contents = []
        for item in folder_data['list']:
            if item.get('isdir') != "1":
                folder_contents.append(item)
        file_list = folder_contents
        logger.info(f"Found {len(file_list)} files in folder")
    
    # Step 7: Process files
    results = []
    for file in file_list:
        dlink = file.get('dlink', '')
        if not dlink:
            continue
            
        # Get direct download link
        direct_link = get_direct_link(dlink, COOKIES)
        
        # Format size
        size_bytes = file.get('size', 0)
        size_str = "Unknown"
        if size_bytes:
            try:
                size_bytes = int(size_bytes)
                if size_bytes >= 1024**3:  # GB
                    size_str = f"{size_bytes / (1024**3):.2f} GB"
                elif size_bytes >= 1024**2:  # MB
                    size_str = f"{size_bytes / (1024**2):.2f} MB"
                elif size_bytes >= 1024:  # KB
                    size_str = f"{size_bytes / 1024:.2f} KB"
                else:
                    size_str = f"{size_bytes} bytes"
            except Exception:
                pass
        
        results.append({
            "file_name": file.get("server_filename", "Unknown"),
            "size": size_str,
            "size_bytes": size_bytes,
            "download_url": dlink,
            "direct_download_url": direct_link,
            "is_directory": file.get("isdir", "0") == "1",
            "modify_time": file.get("server_mtime", 0),
            "thumbnails": file.get("thumbs", {})
        })
    
    return results

def extract_thumbnail_dimensions(url: str) -> str:
    """Extract thumbnail dimensions from URL"""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    size_param = params.get('size', [''])[0]
    
    if size_param:
        parts = size_param.replace('c', '').split('_u')
        if len(parts) == 2:
            return f"{parts[0]}x{parts[1]}"
    return "original"

@app.route('/api', methods=['GET'])
def api_handler():
    """API endpoint for processing Terabox URLs"""
    start_time = time.time()
    url = request.args.get('url')
    if not url:
        return jsonify({
            "status": "error",
            "message": "URL parameter is required",
            "usage": "/api?url=TERABOX_SHARE_URL"
        }), 400
    
    if not validate_terabox_url(url):
        return jsonify({
            "status": "error",
            "message": "Invalid Terabox URL format",
            "supported_domains": SUPPORTED_DOMAINS,
            "url": url
        }), 400
    
    try:
        logger.info(f"Processing URL: {url}")
        files = process_terabox_url(url)
        
        if not files:
            return jsonify({
                "status": "error",
                "message": "No files found or link is empty",
                "url": url
            }), 404
        
        return jsonify({
            "status": "success",
            "url": url,
            "files": files,
            "processing_time": f"{time.time() - start_time:.2f}s",
            "file_count": len(files),
            "cookies": "valid"
        })
    except Exception as e:
        logger.error(f"API error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Service error: {str(e)}",
            "solution": "Try again later or contact support",
            "url": url,
            "developer": "@Farooq_is_king"
        }), 500

@app.route('/')
def home():
    """Home endpoint with service information"""
    return jsonify({
        "status": "API Running",
        "developer": "@Farooq_is_king",
        "usage": "/api?url=TERABOX_SHARE_URL",
        "supported_domains": SUPPORTED_DOMAINS,
        "cookie_status": "valid",
        "note": "Service optimized for Terabox link processing"
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 3000))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)
