"""
Complete Server - Issues + 3D Viewer
Final version with all endpoints
Run this file only: python simple_server.py
"""

from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
import os
import base64
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
CLIENT_ID = os.getenv("APS_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("APS_CLIENT_SECRET", "").strip()
VERSION_URN = os.getenv("VERSION_URN", "").strip()
BASE_URL = "https://developer.api.autodesk.com"

# ============= MISSING VARIABLES - NOW ADDED =============
# Token cache for 3D viewer (2-legged OAuth)
token_cache = {
    'token': None,
    'expires_at': 0
}

# Issues cache (to avoid fetching too often)
issues_cache = {
    'data': None,
    'timestamp': 0
}

# Cache duration: 5 minutes
CACHE_DURATION = 300
# =========================================================

# Import issues fetcher
FETCHER_AVAILABLE = False
fetch_all_issues = None

try:
    from acc_issues_fetcher_simple import fetch_all_issues
    FETCHER_AVAILABLE = True
    print("✓ Issues fetcher imported successfully")
except ImportError as e:
    print(f"⚠ Issues fetcher not available: {e}")
except Exception as e:
    print(f"⚠ Error importing fetcher: {e}")


def get_access_token():
    """Get access token for 3D viewer (2-legged OAuth)"""
    if token_cache['token'] and time.time() < token_cache['expires_at']:
        return token_cache['token']
    
    import requests
    url = f"{BASE_URL}/authentication/v2/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
        "scope": "data:read viewables:read"
    }
    
    response = requests.post(
        url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=30
    )
    
    if response.status_code == 200:
        result = response.json()
        token_cache['token'] = result['access_token']
        token_cache['expires_at'] = time.time() + result.get('expires_in', 3600) - 60
        return result['access_token']
    
    return None


@app.route('/')
def index():
    """Serve 3D viewer HTML"""
    try:
        html_file = os.path.join(os.path.dirname(__file__), 'forge_viewer_powerbi.html')
        if os.path.exists(html_file):
            return send_file(html_file)
        return jsonify({'error': 'Viewer HTML not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/token', methods=['GET', 'POST'])
def get_token_endpoint():
    """Token for 3D viewer (2-legged OAuth for viewing)"""
    try:
        if token_cache['token'] and time.time() < token_cache['expires_at']:
            remaining = int(token_cache['expires_at'] - time.time())
            return jsonify({
                'access_token': token_cache['token'],
                'expires_in': remaining
            })
        
        token = get_access_token()
        if token:
            remaining = int(token_cache['expires_at'] - time.time())
            return jsonify({
                'access_token': token,
                'expires_in': remaining
            })
        return jsonify({'error': 'Failed to get token'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/model-urn', methods=['GET'])
def get_model_urn():
    """Return model URN"""
    try:
        if not VERSION_URN:
            return jsonify({'error': 'VERSION_URN not set'}), 500
        
        urn_encoded = base64.urlsafe_b64encode(
            VERSION_URN.encode('utf-8')
        ).decode('utf-8').rstrip('=')
        
        return jsonify({
            'urn': urn_encoded,
            'version_urn': VERSION_URN
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/issues')
def api_issues():
    """MAIN ENDPOINT - Get all issues for Power BI"""
    print("\n📋 /api/issues called")
    
    try:
        # Check cache
        should_refresh = (
            issues_cache['data'] is None or 
            time.time() - issues_cache['timestamp'] > CACHE_DURATION
        )
        
        if should_refresh:
            print("   Fetching fresh issues...")
            
            if not FETCHER_AVAILABLE or not fetch_all_issues:
                print("   ❌ Fetcher not available")
                return jsonify({
                    'error': 'Issues fetcher not available',
                    'message': 'Check acc_issues_fetcher_simple.py'
                }), 500
            
            try:
                issues_data = fetch_all_issues()
                issues_cache['data'] = issues_data
                issues_cache['timestamp'] = time.time()
                print(f"   ✅ Got {len(issues_data)} issues")
            except Exception as e:
                print(f"   ❌ Fetch failed: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({
                    'error': str(e),
                    'message': 'Failed to fetch issues'
                }), 500
        else:
            age = int(time.time() - issues_cache['timestamp'])
            print(f"   Using cache ({len(issues_cache['data'])} issues, {age}s old)")
        
        return jsonify(issues_cache['data'])
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/issues/stats')
def api_stats():
    """Get issue statistics"""
    try:
        if not issues_cache['data']:
            api_issues()
        
        issues = issues_cache['data'] or []
        return jsonify({
            'total': len(issues),
            'open': len([i for i in issues if i.get('status', '').lower() == 'open']),
            'closed': len([i for i in issues if i.get('status', '').lower() == 'closed']),
            'high': len([i for i in issues if i.get('severity', '').lower() == 'high']),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'issues_cached': bool(issues_cache['data']),
        'issues_count': len(issues_cache['data']) if issues_cache['data'] else 0,
        'fetcher_available': FETCHER_AVAILABLE
    })


@app.route('/api/refresh', methods=['GET', 'POST'])
def refresh():
    """Force refresh"""
    issues_cache['data'] = None
    issues_cache['timestamp'] = 0
    token_cache['token'] = None
    token_cache['expires_at'] = 0
    return jsonify({'success': True, 'message': 'Cache cleared'})


if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 COMPLETE SERVER - ISSUES + 3D VIEWER")
    print("="*70)
    
    print("\n📋 Status:")
    print(f"   CLIENT_ID: {'✅' if CLIENT_ID else '❌'}")
    print(f"   CLIENT_SECRET: {'✅' if CLIENT_SECRET else '❌'}")
    print(f"   VERSION_URN: {'✅' if VERSION_URN else '❌'}")
    print(f"   Issues Fetcher: {'✅' if FETCHER_AVAILABLE else '❌'}")
    
    print("\n🌐 Endpoints:")
    print("   📊 http://localhost:5000/api/issues  ← FOR POWER BI")
    print("   📺 http://localhost:5000              ← 3D Viewer")
    print("   ✅ http://localhost:5000/health       ← Status")
    
    print("\n💡 Power BI Setup:")
    print("   Get Data → Web → http://localhost:5000/api/issues")
    
    print("\n📍 All Routes:")
    for rule in app.url_map.iter_rules():
        methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        print(f"   {methods:6} {rule.rule}")
    
    print("\n" + "="*70)
    print("⚡ Starting server on port 5000...")
    print("="*70 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)