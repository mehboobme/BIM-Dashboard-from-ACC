"""
ACC Issues API Server for Power BI
Wraps your existing extraction logic in a REST API
Run this alongside your existing acc_issues_extractor.py

Requirements:
pip install flask flask-cors requests pandas python-dotenv pillow
"""

from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import requests
import pandas as pd
from datetime import datetime
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import sys
import os
from dotenv import load_dotenv
import threading
import time
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for Power BI

CLIENT_ID = os.getenv('APS_CLIENT_ID')
CLIENT_SECRET = os.getenv('APS_CLIENT_SECRET')
HUB_ID = os.getenv('HUB_ID')
PROJECT_ID = os.getenv('PROJECT_ID')

# Remove 'b.' prefix for API calls
PROJECT_ID_CLEAN = PROJECT_ID.replace("b.", "") if PROJECT_ID else None
HUB_ID_CLEAN = HUB_ID.replace("b.", "") if HUB_ID else None

# OAuth settings
CALLBACK_URL = "http://localhost:8080/"  # Changed to /callback
SCOPES = "data:read data:write"

# Global cache
cached_data = None
last_fetch_time = None
auth_code = None
server_running = True
user_cache = {}
three_legged_token_cache = None
token_expiry = None

def log(message):
    """Print log messages with timestamp"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
    sys.stdout.flush()

def get_two_legged_token():
    """Get 2-legged token for fetching user data"""
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
            return response.json().get("access_token")
        return None
    except:
        return None

def get_account_users(two_legged_token):
    """Fetch all account users"""
    url = f"https://developer.api.autodesk.com/hq/v1/accounts/{HUB_ID_CLEAN}/users"
    
    headers = {
        "Authorization": f"Bearer {two_legged_token}",
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
            name = user.get('name') or f"{first_name} {last_name}".strip() or user.get('email')
            
            if user_id and name:
                user_cache[user_id] = name
        
        log(f"✓ Cached {len(user_cache)} users")
        return True
        
    except Exception as e:
        log(f"⚠ Error fetching users: {str(e)}")
        return False

def get_user_name(user_id):
    """Get user name from cache"""
    if not user_id or user_id == "null" or pd.isna(user_id):
        return "Unassigned"
    
    return user_cache.get(user_id, f"Unknown User ({user_id[:8]})")

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
            
            success_html = """
            <html>
                <head>
                    <style>
                        body { font-family: Arial; text-align: center; padding: 50px; background: #f0f0f0; }
                        .success { color: #28a745; font-size: 24px; }
                    </style>
                </head>
                <body>
                    <h1 class="success">✓ Authorization Successful!</h1>
                    <p>You can close this window and return to Power BI.</p>
                </body>
            </html>
            """
            self.wfile.write(success_html.encode())
            server_running = False

def get_three_legged_token():
    """Get 3-legged token for issues data"""
    global auth_code, server_running, three_legged_token_cache, token_expiry
    
    # Check if we have a valid cached token
    if three_legged_token_cache and token_expiry and datetime.now() < token_expiry:
        log("Using cached 3-legged token")
        return three_legged_token_cache
    
    log("Getting new 3-legged token...")
    
    auth_code = None
    server_running = True
    
    try:
        server = HTTPServer(('localhost', 8080), OAuthHandler)
        server.timeout = 1
    except OSError as e:
        log(f"✗ Cannot start OAuth server: {e}")
        return None
    
    def run_server():
        global server_running
        while server_running:
            server.handle_request()
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    auth_url = (
        f"https://developer.api.autodesk.com/authentication/v2/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={CALLBACK_URL}"
        f"&scope={SCOPES}"
    )
    
    log("Opening browser for authentication...")
    
    try:
        webbrowser.open(auth_url)
    except:
        log(f"\n⚠ Please visit: {auth_url}\n")
    
    log("Waiting for authorization...")
    timeout = 120
    elapsed = 0
    
    while auth_code is None and elapsed < timeout:
        time.sleep(1)
        elapsed += 1
    
    server_running = False
    
    if auth_code is None:
        log("✗ Authorization timeout")
        return None
    
    log("✓ Authorization code received")
    
    # Exchange for token
    token_url = "https://developer.api.autodesk.com/authentication/v2/token"
    
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": CALLBACK_URL
    }
    
    try:
        response = requests.post(token_url, 
                                headers={"Content-Type": "application/x-www-form-urlencoded"},
                                data=data, timeout=30)
        
        if response.status_code == 200:
            token_data = response.json()
            token = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
            
            # Cache token and set expiry (subtract 5 minutes for safety)
            three_legged_token_cache = token
            token_expiry = datetime.now() + pd.Timedelta(seconds=expires_in - 300)
            
            log("✓ 3-legged token obtained")
            return token
        else:
            log(f"✗ Token exchange failed: {response.text}")
            return None
    except Exception as e:
        log(f"✗ Error: {str(e)}")
        return None

def get_issues(three_legged_token):
    """Fetch all issues"""
    log("Fetching issues from ACC...")
    
    url = f"https://developer.api.autodesk.com/construction/issues/v1/projects/{PROJECT_ID_CLEAN}/issues"
    
    headers = {
        "Authorization": f"Bearer {three_legged_token}",
        "Content-Type": "application/json"
    }
    
    all_issues = []
    offset = 0
    limit = 100
    
    while True:
        params = {"limit": limit, "offset": offset}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                issues = data.get('results', [])
                total = data.get('pagination', {}).get('totalResults', 0)
                
                all_issues.extend(issues)
                log(f"✓ Fetched {len(all_issues)} of {total} issues")
                
                if len(all_issues) >= total or len(issues) == 0:
                    break
                
                offset += limit
            else:
                log(f"✗ Error: {response.status_code}")
                break
                
        except Exception as e:
            log(f"✗ Error: {str(e)}")
            break
    
    return all_issues

def get_issue_comments(issue_id, three_legged_token):
    """Fetch comments for a specific issue"""
    url = f"https://developer.api.autodesk.com/construction/issues/v1/projects/{PROJECT_ID_CLEAN}/issues/{issue_id}/comments"
    
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

def process_issues_for_powerbi(issues, three_legged_token):
    """Process issues into Power BI friendly format"""
    log("Processing issues for Power BI...")
    
    # Fetch comments for all issues
    log("Fetching comments...")
    comments_by_issue = {}
    total_comments = 0
    
    for idx, issue in enumerate(issues, 1):
        issue_id = issue.get('id')
        
        if idx % 10 == 0:
            log(f"Progress: {idx}/{len(issues)} issues")
        
        comments = get_issue_comments(issue_id, three_legged_token)
        
        if comments:
            comments_by_issue[issue_id] = comments
            total_comments += len(comments)
    
    log(f"✓ Fetched {total_comments} total comments")
    
    # Process issues
    processed = []
    for issue in issues:
        issue_id = issue.get('id')
        
        # Extract pin coordinates
        linked_docs = issue.get('linkedDocuments', [])
        pin_x_local = None
        pin_y_local = None
        pin_z_local = None
        pin_x_global = None
        pin_y_global = None
        pin_z_global = None
        viewable_name = ""
        viewable_guid = ""
        
        if linked_docs:
            for doc in linked_docs:
                doc_type = doc.get('type', '')
                if 'Pushpin' in doc_type or 'pushpin' in doc_type.lower():
                    details = doc.get('details', {})
                    position = details.get('position', {})
                    viewable = details.get('viewable', {})
                    
                    pin_x_local = position.get('x')
                    pin_y_local = position.get('y')
                    pin_z_local = position.get('z')
                    
                    global_position = details.get('globalPosition', {})
                    if global_position:
                        pin_x_global = global_position.get('x')
                        pin_y_global = global_position.get('y')
                        pin_z_global = global_position.get('z')
                    
                    viewable_name = viewable.get('name', '')
                    viewable_guid = viewable.get('guid', '')
                    break
        
        # Get comments
        issue_comments = comments_by_issue.get(issue_id, [])
        
        # Get first 3 comments
        comment_1 = issue_comments[0].get('body', '') if len(issue_comments) > 0 else ''
        comment_2 = issue_comments[1].get('body', '') if len(issue_comments) > 1 else ''
        comment_3 = issue_comments[2].get('body', '') if len(issue_comments) > 2 else ''
        
        comment_1_by = get_user_name(issue_comments[0].get('createdBy')) if len(issue_comments) > 0 else ''
        comment_2_by = get_user_name(issue_comments[1].get('createdBy')) if len(issue_comments) > 1 else ''
        comment_3_by = get_user_name(issue_comments[2].get('createdBy')) if len(issue_comments) > 2 else ''
        
        # Build issue row
        issue_row = {
            'Issue_ID': issue.get('id', ''),
            'Display_ID': issue.get('displayId', ''),
            'Title': issue.get('title', ''),
            'Description': issue.get('description', ''),
            'Status': issue.get('status', ''),
            'Assigned_To': get_user_name(issue.get('assignedTo')),
            'Assigned_To_Type': issue.get('assignedToType', ''),
            'Due_Date': issue.get('dueDate', ''),
            'Start_Date': issue.get('startDate', ''),
            'Location': issue.get('locationDetails', ''),
            'Created_By': get_user_name(issue.get('createdBy')),
            'Created_At': issue.get('createdAt', ''),
            'Updated_By': get_user_name(issue.get('updatedBy')),
            'Updated_At': issue.get('updatedAt', ''),
            'Closed_By': get_user_name(issue.get('closedBy')),
            'Closed_At': issue.get('closedAt', ''),
            'Published': issue.get('published', False),
            'Comment_Count': len(issue_comments),
            'Comment_1': comment_1,
            'Comment_1_By': comment_1_by,
            'Comment_2': comment_2,
            'Comment_2_By': comment_2_by,
            'Comment_3': comment_3,
            'Comment_3_By': comment_3_by,
            'Pin_X_Local': pin_x_local,
            'Pin_Y_Local': pin_y_local,
            'Pin_Z_Local': pin_z_local,
            'Pin_X_Global': pin_x_global,
            'Pin_Y_Global': pin_y_global,
            'Pin_Z_Global': pin_z_global,
            'Pin_Viewable_Name': viewable_name,
            'Pin_Viewable_GUID': viewable_guid,
        }
        
        # Add custom attributes
        for attr in issue.get('customAttributes', []):
            attr_title = attr.get('title', 'Unknown')
            issue_row[f'Custom_{attr_title}'] = attr.get('value', '')
        
        processed.append(issue_row)
    
    return processed

def fetch_fresh_data():
    """Fetch fresh data from ACC"""
    global cached_data, last_fetch_time
    
    try:
        log("Starting fresh data fetch...")
        
        # Step 1: Get 2-legged token for users
        two_legged_token = get_two_legged_token()
        if not two_legged_token:
            raise Exception("Failed to get 2-legged token")
        
        # Step 2: Fetch users
        get_account_users(two_legged_token)
        
        # Step 3: Get 3-legged token
        three_legged_token = get_three_legged_token()
        if not three_legged_token:
            raise Exception("Failed to get 3-legged token")
        
        # Step 4: Fetch issues
        issues = get_issues(three_legged_token)
        if not issues:
            raise Exception("No issues found")
        
        # Step 5: Process for Power BI
        processed_data = process_issues_for_powerbi(issues, three_legged_token)
        
        # Cache the results
        cached_data = processed_data
        last_fetch_time = datetime.now()
        
        log(f"✓ Cached {len(processed_data)} processed issues")
        
        return processed_data
        
    except Exception as e:
        log(f"✗ Error fetching data: {str(e)}")
        raise

# ==================== API ENDPOINTS ====================

@app.route('/')
def home():
    """API home page"""
    return jsonify({
        "service": "ACC Issues API for Power BI",
        "version": "2.0",
        "status": "online",
        "endpoints": {
            "/api/issues": "Get all issues (JSON) - Use this in Power BI",
            "/api/issues/csv": "Get all issues (CSV format)",
            "/api/issues/refresh": "Force refresh from ACC",
            "/api/issues/status": "Get cache status",
            "/callback": "OAuth callback (do not use directly)"
        },
        "power_bi_url": "http://localhost:8080/api/issues"
    })

@app.route('/callback')
def oauth_callback():
    """OAuth callback endpoint"""
    return """
    <html>
        <head>
            <style>
                body { font-family: Arial; text-align: center; padding: 50px; background: #f0f0f0; }
                .success { color: #28a745; font-size: 24px; }
            </style>
        </head>
        <body>
            <h1 class="success">✓ Authorization Successful!</h1>
            <p>You can close this window.</p>
        </body>
    </html>
    """

@app.route('/api/issues', methods=['GET'])
def get_issues_endpoint():
    """Main endpoint for Power BI - Returns JSON"""
    global cached_data, last_fetch_time
    
    try:
        force_refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        if cached_data is None or force_refresh:
            log("Fetching fresh data from ACC...")
            data = fetch_fresh_data()
        else:
            log("Using cached data")
            data = cached_data
        
        return jsonify({
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "last_fetch": last_fetch_time.isoformat() if last_fetch_time else None,
            "count": len(data),
            "data": data
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/issues/csv', methods=['GET'])
def get_issues_csv():
    """Alternative endpoint - Returns CSV"""
    global cached_data
    
    try:
        if cached_data is None:
            data = fetch_fresh_data()
        else:
            data = cached_data
        
        df = pd.DataFrame(data)
        csv_data = df.to_csv(index=False)
        
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=acc_issues.csv'}
        )
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/issues/refresh', methods=['POST'])
def refresh_issues():
    """Force refresh data from ACC"""
    try:
        log("Manual refresh triggered...")
        data = fetch_fresh_data()
        
        return jsonify({
            "status": "success",
            "message": "Data refreshed successfully",
            "timestamp": datetime.now().isoformat(),
            "count": len(data)
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/issues/status', methods=['GET'])
def api_status():
    """Get API and cache status"""
    return jsonify({
        "status": "online",
        "cached_issues": len(cached_data) if cached_data else 0,
        "last_fetch": last_fetch_time.isoformat() if last_fetch_time else None,
        "user_cache_size": len(user_cache),
        "token_cached": three_legged_token_cache is not None,
        "token_expires": token_expiry.isoformat() if token_expiry else None,
        "timestamp": datetime.now().isoformat()
    })

if __name__ == '__main__':
    print("=" * 70)
    print("ACC Issues API Server for Power BI")
    print("=" * 70)
    print(f"\n🚀 Server starting at: http://localhost:8080")
    print("\n📊 Power BI Connection:")
    print("   URL: http://localhost:8080/api/issues")
    print("\n📝 Available Endpoints:")
    print("   GET  /api/issues          - Get issues (JSON)")
    print("   GET  /api/issues/csv      - Get issues (CSV)")
    print("   POST /api/issues/refresh  - Force refresh")
    print("   GET  /api/issues/status   - Check status")
    print("\n⚠️  Important:")
    print("   - First access will open browser for authentication")
    print("   - Token is cached for ~55 minutes")
    print("   - Data is cached until manual refresh")
    print("=" * 70)
    print("\n")
    
    app.run(host='0.0.0.0', port=8080, debug=False)