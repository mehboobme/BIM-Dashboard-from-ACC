"""
ACC Issues Fetcher with 3-Legged OAuth
Enhanced version with user names, thumbnails, and comments
Token is cached for reuse
Server-compatible: won't open browser if token is cached
"""

import requests
import os
import json
import webbrowser
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
import base64

load_dotenv()

CLIENT_ID = os.getenv('APS_CLIENT_ID')
CLIENT_SECRET = os.getenv('APS_CLIENT_SECRET')
PROJECT_ID = os.getenv('PROJECT_ID', '').replace("b.", "")
HUB_ID = os.getenv('HUB_ID', '').replace("b.", "")
CALLBACK_URL = "http://localhost:8080/"
TOKEN_CACHE_FILE = "token_cache.json"

# Check if running in server mode (no browser available)
SERVER_MODE = os.getenv('SERVER_MODE', 'false').lower() == 'true'

# Global caches
auth_code = None
server_running = True
user_cache = {}
two_legged_token_cache = None
two_legged_token_expiry = 0

class OAuthHandler(BaseHTTPRequestHandler):
    """Handle OAuth callback"""
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        global auth_code, server_running
        
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if 'code' in params:
            auth_code = params['code'][0]
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = """
            <html><body style='font-family: Arial; text-align: center; padding: 50px;'>
                <h1 style='color: #28a745;'>✓ Authorization Successful!</h1>
                <p>You can close this window and return to your terminal.</p>
                <script>setTimeout(() => window.close(), 3000);</script>
            </body></html>
            """
            self.wfile.write(html.encode())
            server_running = False

def load_cached_token():
    """Load token from cache file"""
    try:
        if os.path.exists(TOKEN_CACHE_FILE):
            with open(TOKEN_CACHE_FILE, 'r') as f:
                data = json.load(f)
                # Check if token is still valid (with 5 min buffer)
                if data.get('expires_at', 0) > time.time() + 300:
                    remaining_min = int((data['expires_at'] - time.time())/60)
                    if not SERVER_MODE:
                        print(f"✓ Using cached token (expires in {remaining_min} min)")
                    return data.get('access_token')
    except Exception as e:
        if not SERVER_MODE:
            print(f"⚠ Error reading token cache: {e}")
    return None

def save_token(token, expires_in):
    """Save token to cache file"""
    try:
        data = {
            'access_token': token,
            'expires_at': time.time() + expires_in
        }
        with open(TOKEN_CACHE_FILE, 'w') as f:
            json.dump(data, f)
        if not SERVER_MODE:
            print(f"✓ Token cached (valid for {expires_in//60} minutes)")
    except Exception as e:
        if not SERVER_MODE:
            print(f"⚠ Could not cache token: {e}")

def get_2_legged_token():
    """Get 2-legged token for user data"""
    global two_legged_token_cache, two_legged_token_expiry
    
    # Check cache
    if two_legged_token_cache and time.time() < two_legged_token_expiry:
        return two_legged_token_cache
    
    url = "https://developer.api.autodesk.com/authentication/v2/token"
    
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
        "scope": "account:read data:read"
    }
    
    try:
        response = requests.post(url, 
                                headers={"Content-Type": "application/x-www-form-urlencoded"},
                                data=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            two_legged_token_cache = result.get("access_token")
            two_legged_token_expiry = time.time() + result.get("expires_in", 3600) - 60
            return two_legged_token_cache
    except:
        pass
    return None

def fetch_account_users():
    """Fetch all account users and cache names"""
    global user_cache
    
    if not HUB_ID:
        if not SERVER_MODE:
            print("⚠ HUB_ID not set, user names won't be resolved")
        return
    
    token = get_2_legged_token()
    if not token:
        if not SERVER_MODE:
            print("⚠ Could not get 2-legged token for users")
        return
    
    url = f"https://developer.api.autodesk.com/hq/v1/accounts/{HUB_ID}/users"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    all_users = []
    offset = 0
    limit = 100
    
    try:
        while True:
            params = {"limit": limit, "offset": offset}
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if isinstance(data, list):
                    users = data
                elif 'results' in data:
                    users = data['results']
                else:
                    break
                
                all_users.extend(users)
                
                if len(users) < limit:
                    break
                    
                offset += limit
            else:
                break
        
        # Build user cache
        for user in all_users:
            user_id = (user.get('uid') or user.get('id') or 
                      user.get('autodeskId') or user.get('userId'))
            
            first_name = user.get('firstName', '')
            last_name = user.get('lastName', '')
            name = user.get('name') or f"{first_name} {last_name}".strip() or user.get('email', '')
            
            if user_id and name:
                user_cache[user_id] = name
        
        if not SERVER_MODE:
            print(f"✓ Cached {len(user_cache)} user names")
        
    except Exception as e:
        if not SERVER_MODE:
            print(f"⚠ Error fetching users: {str(e)}")

def get_user_name(user_id):
    """Get user name from cache or return ID"""
    if not user_id or user_id == "null":
        return "Unassigned"
    
    return user_cache.get(user_id, user_id)

def download_thumbnail_base64(snapshot_urn, three_legged_token):
    """Download thumbnail and return as base64 data URL for embedding"""
    if not snapshot_urn or snapshot_urn == "":
        return None
    
    try:
        # Check if it's an OSS URN
        if "urn:adsk.objects:os.object:" in snapshot_urn:
            # Extract bucket and object key
            urn_part = snapshot_urn.replace("urn:adsk.objects:os.object:", "")
            parts = urn_part.split("/", 1)
            
            if len(parts) == 2:
                bucket_key = parts[0]
                object_key = parts[1]
                
                # Get signed download URL
                url = f"https://developer.api.autodesk.com/oss/v2/buckets/{bucket_key}/objects/{object_key}/signeds3download"
                
                headers = {
                    "Authorization": f"Bearer {three_legged_token}"
                }
                
                response = requests.get(url, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    signed_url_data = response.json()
                    download_url = signed_url_data.get('url')
                    
                    if download_url:
                        # Download the actual image
                        img_response = requests.get(download_url, timeout=30)
                        
                        if img_response.status_code == 200:
                            # Convert to base64
                            img_base64 = base64.b64encode(img_response.content).decode('utf-8')
                            # Return as data URL
                            return f"data:image/jpeg;base64,{img_base64}"
        else:
            # Try Model Derivative API
            encoded_urn = requests.utils.quote(snapshot_urn, safe='')
            
            url = f"https://developer.api.autodesk.com/modelderivative/v2/designdata/{encoded_urn}/thumbnail"
            
            headers = {
                "Authorization": f"Bearer {three_legged_token}"
            }
            
            params = {
                "width": 600,
                "height": 800
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                # Convert to base64
                img_base64 = base64.b64encode(response.content).decode('utf-8')
                return f"data:image/png;base64,{img_base64}"
        
        return None
        
    except Exception as e:
        if not SERVER_MODE:
            print(f"  ⚠ Error downloading thumbnail: {str(e)}")
        return None

def get_3_legged_token():
    """Get 3-legged OAuth token (opens browser once)"""
    global auth_code, server_running
    
    # Try cached token first
    cached = load_cached_token()
    if cached:
        return cached
    
    # If in server mode and no cached token, can't proceed
    if SERVER_MODE:
        raise Exception(
            "No cached token available. Please run authentication first:\n"
            "   python acc_issues_fetcher_simple.py"
        )
    
    print("\n🔐 Authentication Required")
    print("Opening browser for authorization...")
    
    auth_code = None
    server_running = True
    
    # Start callback server
    try:
        server = HTTPServer(('localhost', 8080), OAuthHandler)
        server.timeout = 1
    except OSError as e:
        print(f"❌ Cannot start server on port 8080: {e}")
        print("   Make sure port 8080 is not in use")
        return None
    
    def run_server():
        global server_running
        while server_running:
            server.handle_request()
    
    import threading
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Open browser for auth
    auth_url = (
        f"https://developer.api.autodesk.com/authentication/v2/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={CALLBACK_URL}"
        f"&scope=data:read"
    )
    
    try:
        webbrowser.open(auth_url)
    except:
        print(f"\n⚠ Could not open browser automatically")
        print(f"   Please visit: {auth_url}\n")
    
    # Wait for callback
    print("Waiting for authorization (max 2 minutes)...")
    timeout = 120
    elapsed = 0
    
    while auth_code is None and elapsed < timeout:
        time.sleep(1)
        elapsed += 1
        if elapsed % 15 == 0:
            print(f"  Still waiting... ({elapsed}s)")
    
    server_running = False
    
    if auth_code is None:
        print("❌ Authorization timeout")
        return None
    
    print("✓ Authorization code received")
    
    # Exchange code for token
    token_url = "https://developer.api.autodesk.com/authentication/v2/token"
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": CALLBACK_URL
    }
    
    response = requests.post(
        token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=30
    )
    
    if response.status_code == 200:
        result = response.json()
        token = result['access_token']
        expires_in = result.get('expires_in', 3600)
        
        # Cache the token
        save_token(token, expires_in)
        
        print("✓ Access token obtained\n")
        return token
    else:
        print(f"❌ Token exchange failed: {response.text}")
        return None

def get_issue_comments(issue_id, three_legged_token):
    """Fetch comments for a specific issue"""
    url = f"https://developer.api.autodesk.com/construction/issues/v1/projects/{PROJECT_ID}/issues/{issue_id}/comments"
    
    headers = {
        "Authorization": f"Bearer {three_legged_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('results', [])
        return []
    except:
        return []

def fetch_all_issues():
    """
    Fetch all issues from ACC with user names and thumbnails
    Returns list of issue dictionaries for Power BI
    """
    if not SERVER_MODE:
        print(f"Fetching issues from project: {PROJECT_ID}")
    
    # Get tokens
    token = get_3_legged_token()
    if not token:
        raise Exception("Could not get access token")
    
    # Fetch users for name resolution
    if not SERVER_MODE:
        print("Fetching user names...")
    fetch_account_users()
    
    url = f"https://developer.api.autodesk.com/construction/issues/v1/projects/{PROJECT_ID}/issues"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    all_issues = []
    offset = 0
    limit = 100
    
    while True:
        params = {"limit": limit, "offset": offset}
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            issues = data.get('results', [])
            total = data.get('pagination', {}).get('totalResults', 0)
            
            all_issues.extend(issues)
            if not SERVER_MODE:
                print(f"✓ Fetched {len(all_issues)} of {total} issues")
            
            if len(all_issues) >= total or len(issues) == 0:
                break
            
            offset += limit
            
        elif response.status_code == 401:
            # Token expired - delete cache
            if os.path.exists(TOKEN_CACHE_FILE):
                os.remove(TOKEN_CACHE_FILE)
            raise Exception("Token expired. Please run: python acc_issues_fetcher_simple.py")
        else:
            raise Exception(f"API Error {response.status_code}: {response.text[:200]}")
    
    # Transform to Power BI format
    if not SERVER_MODE:
        print(f"\nProcessing {len(all_issues)} issues with thumbnails and comments...")
    
    transformed = []
    
    for idx, issue in enumerate(all_issues, 1):
        issue_id = issue.get('id')
        
        # Show progress
        if not SERVER_MODE and idx % 10 == 0:
            print(f"  Processing {idx}/{len(all_issues)}...")
        
        # Extract pin coordinates
        pin_x = ""
        pin_y = ""
        pin_z = ""
        object_id = ""
        viewable_name = ""
        viewable_guid = ""
        
        linked_docs = issue.get('linkedDocuments', [])
        for doc in linked_docs:
            if 'Pushpin' in doc.get('type', ''):
                details = doc.get('details', {})
                position = details.get('position', {})
                viewable = details.get('viewable', {})
                
                pin_x = position.get('x', '')
                pin_y = position.get('y', '')
                pin_z = position.get('z', '')
                object_id = details.get('objectId', '')
                viewable_name = viewable.get('name', '')
                viewable_guid = viewable.get('guid', '')
                break
        
        # Get thumbnail as base64 data URL
        snapshot_urn = issue.get('snapshotUrn')
        thumbnail_data = None
        if snapshot_urn:
            thumbnail_data = download_thumbnail_base64(snapshot_urn, token)
        
        # Get comments
        comments = get_issue_comments(issue_id, token)
        comment_count = len(comments)
        
        # Get first 3 comments
        comment_1 = comments[0].get('body', '') if len(comments) > 0 else ''
        comment_2 = comments[1].get('body', '') if len(comments) > 1 else ''
        comment_3 = comments[2].get('body', '') if len(comments) > 2 else ''
        
        comment_1_by = get_user_name(comments[0].get('createdBy')) if len(comments) > 0 else ''
        comment_2_by = get_user_name(comments[1].get('createdBy')) if len(comments) > 1 else ''
        comment_3_by = get_user_name(comments[2].get('createdBy')) if len(comments) > 2 else ''
        
        # Map severity
        status = issue.get('status', 'open')
        root_cause = issue.get('rootCauseId', '')
        
        # Simple severity mapping
        severity = 'Medium'
        if 'high' in str(root_cause).lower() or 'critical' in str(root_cause).lower():
            severity = 'High'
        elif 'low' in str(root_cause).lower():
            severity = 'Low'
        
        transformed.append({
            'issue_id': issue.get('id'),
            'display_id': issue.get('displayId'),
            'title': issue.get('title'),
            'description': issue.get('description', ''),
            'status': status,
            'severity': severity,
            'assigned_to': get_user_name(issue.get('assignedTo')),
            'assigned_to_id': issue.get('assignedTo', ''),
            'assigned_to_type': issue.get('assignedToType', ''),
            'created_by': get_user_name(issue.get('createdBy')),
            'created_by_id': issue.get('createdBy', ''),
            'updated_by': get_user_name(issue.get('updatedBy')),
            'closed_by': get_user_name(issue.get('closedBy')),
            'created_at': issue.get('createdAt'),
            'updated_at': issue.get('updatedAt'),
            'due_date': issue.get('dueDate'),
            'closed_at': issue.get('closedAt'),
            'location': issue.get('locationDetails', ''),
            'published': issue.get('published', True),
            'pin_x': pin_x,
            'pin_y': pin_y,
            'pin_z': pin_z,
            'objectId': object_id,
            'viewable_name': viewable_name,
            'viewable_guid': viewable_guid,
            'thumbnail_url': snapshot_urn,
            'thumbnail_base64': thumbnail_data,  # Base64 data URL for Power BI
            'root_cause_id': root_cause,
            'comment_count': comment_count,
            'comment_1': comment_1,
            'comment_1_by': comment_1_by,
            'comment_2': comment_2,
            'comment_2_by': comment_2_by,
            'comment_3': comment_3,
            'comment_3_by': comment_3_by,
        })
    
    if not SERVER_MODE:
        print(f"✓ Processed {len(transformed)} issues\n")
    
    return transformed

if __name__ == "__main__":
    print("="*60)
    print("ACC Issues Fetcher - Authentication")
    print("="*60)
    
    if not all([CLIENT_ID, CLIENT_SECRET, PROJECT_ID]):
        print("❌ Missing credentials in .env")
        print("   Required: APS_CLIENT_ID, APS_CLIENT_SECRET, PROJECT_ID")
        exit(1)
    
    if not HUB_ID:
        print("⚠ HUB_ID not set - user IDs won't resolve to names")
    
    try:
        issues = fetch_all_issues()
        
        if issues:
            print(f"✓ Success! {len(issues)} issues fetched")
            print(f"\nFirst issue sample:")
            first = issues[0]
            print(f"  ID: {first.get('display_id')}")
            print(f"  Title: {first.get('title')}")
            print(f"  Status: {first.get('status')}")
            print(f"  Severity: {first.get('severity')}")
            print(f"  Assigned to: {first.get('assigned_to')}")
            print(f"  Created by: {first.get('created_by')}")
            print(f"  Comments: {first.get('comment_count')}")
            print(f"  Has thumbnail: {'Yes' if first.get('thumbnail_base64') else 'No'}")
            
            print(f"\n✓ Token cached successfully!")
            print(f"   You can now start the server: python simple_server.py")
        else:
            print("❌ No issues fetched")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("="*60)