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

@app.route('/thumbnail-table.html')
def thumbnail_table():
    """HTML table with clickable thumbnails - FIXED VERSION"""
    print("\n🖼️ /thumbnail-table.html called")
    
    try:
        if not issues_cache['data']:
            if FETCHER_AVAILABLE and fetch_all_issues:
                issues_cache['data'] = fetch_all_issues()
        
        issues = issues_cache['data'] or []
        issues_with_coords = [i for i in issues if i.get('pin_x') and i.get('pin_y') and i.get('pin_z')]
        
        print(f"   📍 Found {len(issues_with_coords)} issues with coordinates")
        
        # Start HTML with embedded styles
        html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', sans-serif;
            background: #f5f5f5;
            padding: 10px;
        }
        .thumbnail-table { 
            width: 100%; 
            border-collapse: collapse;
            background: white;
        }
        .thumbnail-table thead {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .thumbnail-table th {
            padding: 3px 3px;
            text-align: center;
            font-size: 12px;
            font-weight: 600;
            top: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            z-index: 100;
        }
        .thumbnail-table td {
            padding: 10px;
            border-bottom: 1px solid #e0e0e0;
            font-size: 11px;
        }
        .thumbnail-img {
            width: 70px;
            height: 52px;
            object-fit: cover;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
            border: 2px solid #ddd;
        }
        .thumbnail-img:hover {
            transform: scale(1.1);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            border-color: #667eea;
        }
        .clickable-row {
            cursor: pointer;
            transition: background 0.15s;
        }
        .clickable-row:hover {
            background: #f8f9fa;
        }
        .status-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 10px;
            font-weight: 600;
        }
        .status-open { background: #fff3cd; color: #856404; }
        .status-closed { background: #d4edda; color: #155724; }
        
        #debug-log {
            position: fixed;
            bottom: 10px;
            right: 10px;
            background: rgba(0,0,0,0.8);
            color: #0f0;
            padding: 8px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 9px;
            max-width: 250px;
            max-height: 150px;
            overflow-y: auto;
            z-index: 10000;
        }
         /* ========== ADD THESE FILTER STYLES ========== */
        .filter-container {
            background: white;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            gap: 15px;
            align-items: center;
            flex-wrap: wrap;
        }
        
        .filter-group {
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        
        .filter-group label {
            font-size: 11px;
            font-weight: 600;
            color: #666;
            text-transform: uppercase;
        }
        
        .filter-group select {
            padding: 8px 12px;
            border: 2px solid #e0e0e0;
            border-radius: 4px;
            font-size: 12px;
            background: white;
            cursor: pointer;
            min-width: 150px;
            transition: border-color 0.2s;
        }
        
        .filter-group select:hover {
            border-color: #667eea;
        }
        
        .filter-group select:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        .clear-filters-btn {
            padding: 8px 16px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 600;
            transition: background 0.2s;
            margin-top: 18px;
        }
        
        .clear-filters-btn:hover {
            background: #5568d3;
        }
        
        .filter-count {
            margin-top: 18px;
            padding: 8px 12px;
            background: #f5f5f5;
            border-radius: 4px;
            font-size: 12px;
            color: #666;
            font-weight: 600;
    </style>
</head>
<body>

    <div id="debug-log" style="display:none;">Loading...</div>
     <!-- ========== ADD FILTER CONTAINER HERE ========== -->
    <div class="filter-container">
        <div class="filter-group">
            <label>Status</label>
            <select id="filter-status">
                <option value="">All Status</option>
            </select>
        </div>
        
        <div class="filter-group">
            <label>Severity</label>
            <select id="filter-severity">
                <option value="">All Severity</option>
            </select>
        </div>
        
        <div class="filter-group">
            <label>Assigned To</label>
            <select id="filter-assigned">
                <option value="">All Assigned</option>
            </select>
        </div>
        
        <button class="clear-filters-btn" onclick="clearFilters()">Clear Filters</button>
        
        <div class="filter-count" id="filter-count">
            Showing <span id="visible-count">0</span> of <span id="total-count">0</span> issues
        </div>
    </div>
    <table class="thumbnail-table">
<thead>
            <tr>
                <th>Thumbnail</th>
                <th>ID</th>
                <th>Title</th>
                <th>Status</th>
                <th>Severity</th>
                <th>Assigned To</th>
                <th>Comments</th>
                <th>Comments By</th>
            </tr>
        </thead>
        <tbody>
"""
        
        # Add each row
        for idx, issue in enumerate(issues_with_coords):
            issue_id = issue.get('issue_id', '')
            display_id = issue.get('display_id', '')
            title = issue.get('title', 'Untitled')
            status = issue.get('status', 'Unknown')
            severity = issue.get('severity', 'N/A')
            assigned_to = issue.get('assigned_to', 'Unassigned')
            comments = issue.get('comment_1', '')
            comments_by = issue.get('comment_1_by', '')
            
            status_class = 'status-open'
            if 'closed' in status.lower():
                status_class = 'status-closed'
            
            img_id = f"img_{idx}"
            
            html += f"""
        <tr class="clickable-row" onclick="handleRowClick({idx})">
            <td>
                <img id="{img_id}" class="thumbnail-img" alt="{display_id}" />
            </td>
            <td><strong>{display_id}</strong></td>
            <td>{title}</td>
            <td><span class="status-badge {status_class}">{status}</span></td>
            <td>{severity}</td>
            <td>{assigned_to}</td>
            <td>{comments[:50] if comments else 'No comments'}</td>
            <td>{comments_by}</td>
        </tr>
"""
        
        html += """
        </tbody>
    </table>
    
    <script>
        const debugLog = document.getElementById('debug-log');
        
        function logDebug(msg) {
            console.log(msg);
            debugLog.innerHTML += msg + '<br>';
            debugLog.scrollTop = debugLog.scrollHeight;
        }
        
        // Store issue data
        const issuesData = [
"""
        
        # Add issue data as JavaScript array
        for issue in issues_with_coords:
            issue_id = issue.get('issue_id', '').replace("'", "\\'")
            title = issue.get('title', '').replace("'", "\\'")
            thumbnail = issue.get('thumbnail_base64', '')
            
            html += f"""
            {{
                issue_id: '{issue_id}',
                display_id: '{issue.get('display_id', '')}',
                title: '{title}',
                pin_x: {issue.get('pin_x', 0)},
                pin_y: {issue.get('pin_y', 0)},
                pin_z: {issue.get('pin_z', 0)},
                thumbnail: `{thumbnail}`
            }},
"""
        
        html += """
        ];
        
        // Load images after page loads
        window.onload = function() {
            logDebug('Page loaded');
            logDebug('Loading ' + issuesData.length + ' thumbnails...');
            
            issuesData.forEach((issue, idx) => {
                const img = document.getElementById('img_' + idx);
                if (img && issue.thumbnail) {
                    img.src = issue.thumbnail;
                    logDebug('Loaded img ' + idx);
                }
            });
            
            // Initialize Excel-style column filters
            initColumnFilters();  // ← CHANGED: Use initColumnFilters instead
            
            logDebug('All loaded!');
        };
        
        function handleRowClick(idx) {
            const issue = issuesData[idx];
            logDebug('Clicked: ' + issue.display_id);
            sendMessageToViewer(issue);
        }
        
        function sendMessageToViewer(issue) {
            logDebug('Sending message...');
            
            const message = {
                type: 'NAVIGATE_TO_ISSUE',
                issue_id: issue.issue_id,
                display_id: issue.display_id,
                pin_x: issue.pin_x,
                pin_y: issue.pin_y,
                pin_z: issue.pin_z,
                title: issue.title,
                timestamp: Date.now()
            };
            
            // Method 1: Post to parent
            try {
                parent.postMessage(message, '*');
                logDebug('Sent to parent');
            } catch(e) {
                logDebug('Parent failed: ' + e.message);
            }
            
            // Method 2: Post to top window
            try {
                window.top.postMessage(message, '*');
                logDebug('Sent to top');
            } catch(e) {
                logDebug('Top failed: ' + e.message);
            }
            
            // Method 3: Post to opener
            if (window.opener) {
                try {
                    window.opener.postMessage(message, '*');
                    logDebug('Sent to opener');
                } catch(e) {
                    logDebug('Opener failed: ' + e.message);
                }
            }
            
            logDebug('Message broadcast complete');
        }
        // Make columns resizable by dragging
function makeColumnsResizable() {
    const table = document.querySelector('.thumbnail-table');
    const cols = table.querySelectorAll('th');
    
    cols.forEach((col, index) => {
        const resizer = document.createElement('div');
        resizer.style.position = 'absolute';
        resizer.style.top = '0';
        resizer.style.right = '0';
        resizer.style.bottom = '0';
        resizer.style.width = '5px';
        resizer.style.cursor = 'col-resize';
        resizer.style.userSelect = 'none';
        resizer.style.zIndex = '1';
        
        resizer.addEventListener('mouseenter', () => {
            resizer.style.background = 'rgba(102, 126, 234, 0.5)';
        });
        
        resizer.addEventListener('mouseleave', () => {
            resizer.style.background = 'transparent';
        });
        
        resizer.addEventListener('mousedown', (e) => {
            e.preventDefault();
            const startX = e.pageX;
            const startWidth = col.offsetWidth;
            
            function onMouseMove(e) {
                const newWidth = startWidth + (e.pageX - startX);
                if (newWidth > 50) {  // Minimum width
                    col.style.width = newWidth + 'px';
                }
            }
            
            function onMouseUp() {
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
            }
            
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
        
        col.style.position = 'relative';
        col.appendChild(resizer);
    });
}

// Call after table loads
setTimeout(makeColumnsResizable, 500);
    </script>
</body>
</html>
"""
        
        return html
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return f"<html><body><h3>Error: {str(e)}</h3></body></html>", 500

@app.route('/powerbi-wrapper.html')
def powerbi_wrapper():
    """Wrapper page that contains both viewer and table - they can communicate directly"""
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { 
            height: 100vh;
            overflow: hidden;
            font-family: 'Segoe UI', sans-serif;
        }
        #container {
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        #viewer-frame {
            flex: 1;
            border: none;
            width: 100%;
        }
        #table-frame {
            flex: 1;
            border: none;
            width: 100%;
            border-top: 3px solid #667eea;
        }
        #status {
            position: fixed;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(102, 126, 234, 0.95);
            color: white;
            padding: 8px 16px;
            border-radius: 4px;
            font-size: 12px;
            z-index: 100000;
            display: none;
        }
        /* Filter header styles */
        .filterable-header {
            position: relative;
            cursor: pointer;
            user-select: none;
        }

        .filterable-header:hover {
            background: linear-gradient(135deg, #5568d3 0%, #6a4a9e 100%);
        }

        .filter-icon {
            font-size: 10px;
            margin-left: 5px;
            opacity: 0.7;
        }

        .filterable-header.filtered .filter-icon {
            color: #ffd700;
            opacity: 1;
        }

        /* Filter dropdown */
        .filter-dropdown {
            position: absolute;
            top: 100%;
            left: 0;
            background: white;
            border: 2px solid #667eea;
            border-radius: 4px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            z-index: 1000;
            min-width: 200px;
            max-height: 300px;
            overflow-y: auto;
            display: none;
        }

        .filter-dropdown.active {
            display: block;
        }

        .filter-search {
            width: calc(100% - 20px);
            padding: 8px;
            margin: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 12px;
        }

        .filter-option {
            padding: 8px 12px;
            cursor: pointer;
            font-size: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .filter-option:hover {
            background: #f0f0f0;
        }

        .filter-option input[type="checkbox"] {
            cursor: pointer;
        }

        .filter-actions {
            padding: 10px;
            border-top: 1px solid #ddd;
            display: flex;
            gap: 10px;
            justify-content: space-between;
        }

        .filter-btn {
            padding: 6px 12px;
            border: none;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            font-weight: 600;
        }

        .filter-btn-apply {
            background: #667eea;
            color: white;
        }

        .filter-btn-clear {
            background: #e0e0e0;
            color: #666;
        }

        .filter-status-bar {
            background: #f0f0f0;
            padding: 10px;
            margin-bottom: 10px;
            border-radius: 4px;
            font-size: 12px;
            display: none;
        }

        .filter-status-bar.active {
            display: block;
        }

        .filter-tag {
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 4px 8px;
            border-radius: 12px;
            margin-right: 8px;
            font-size: 11px;
        }

        .filter-tag .remove {
            margin-left: 6px;
            cursor: pointer;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div id="status">Connecting...</div>
    <div id="container">
        <iframe id="viewer-frame" src="http://localhost:5000"></iframe>
        <iframe id="table-frame" src="http://localhost:5000/thumbnail-table.html"></iframe>
    </div>
    
    <script>
        const statusDiv = document.getElementById('status');
        
        function showStatus(msg) {
            statusDiv.textContent = msg;
            statusDiv.style.display = 'block';
            setTimeout(() => {
                statusDiv.style.display = 'none';
            }, 3000);
        }
        
        // Listen for messages from the table iframe
        window.addEventListener('message', function(event) {
            console.log('🔵 Wrapper received:', event.data);
            
            if (event.data && event.data.type === 'NAVIGATE_TO_ISSUE') {
                console.log('✅ Relaying to viewer...');
                
                const viewerFrame = document.getElementById('viewer-frame');
                
                // Send message to viewer
                viewerFrame.contentWindow.postMessage(event.data, '*');
                
                
            }
        });
        
        // Notify when both iframes are loaded
        let viewerLoaded = false;
        let tableLoaded = false;
        
        document.getElementById('viewer-frame').onload = function() {
            viewerLoaded = true;
            console.log('✅ Viewer loaded');
            if (tableLoaded) showStatus('✅ Ready!');
        };
        
        document.getElementById('table-frame').onload = function() {
            tableLoaded = true;
            console.log('✅ Table loaded');
            if (viewerLoaded) showStatus('✅ Ready!');
        };
        // Populate filter dropdowns with unique values
        function initColumnFilters() {
            const statuses = [...new Set(issuesData.map(i => i.status))].filter(Boolean).sort();
            const severities = [...new Set(issuesData.map(i => i.severity))].filter(Boolean).sort();
            const assigned = [...new Set(issuesData.map(i => i.assigned_to))].filter(Boolean).sort();
            
            const statusSelect = document.getElementById('filter-status');
            const severitySelect = document.getElementById('filter-severity');
            const assignedSelect = document.getElementById('filter-assigned');
            
            statuses.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s;
                opt.textContent = s;
                statusSelect.appendChild(opt);
            });
            
            severities.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s;
                opt.textContent = s;
                severitySelect.appendChild(opt);
            });
            
            assigned.forEach(a => {
                const opt = document.createElement('option');
                opt.value = a;
                opt.textContent = a;
                assignedSelect.appendChild(opt);
            });
            
            // Add event listeners
            statusSelect.addEventListener('change', applyFilters);
            severitySelect.addEventListener('change', applyFilters);
            assignedSelect.addEventListener('change', applyFilters);
        }
        
        // Apply filters to table rows
        function applyFilters() {
            const statusFilter = document.getElementById('filter-status').value;
            const severityFilter = document.getElementById('filter-severity').value;
            const assignedFilter = document.getElementById('filter-assigned').value;
            
            let visibleCount = 0;
            
            issuesData.forEach((issue, idx) => {
                const row = document.querySelector(`tr[onclick*="handleRowClick(${idx})"]`);
                
                if (!row) return;
                
                const matchesStatus = !statusFilter || issue.status === statusFilter;
                const matchesSeverity = !severityFilter || issue.severity === severityFilter;
                const matchesAssigned = !assignedFilter || issue.assigned_to === assignedFilter;
                
                const shouldShow = matchesStatus && matchesSeverity && matchesAssigned;
                
                row.style.display = shouldShow ? 'table-row' : 'none';
                
                if (shouldShow) visibleCount++;
            });
            
            // Update count
            document.getElementById('visible-count').textContent = visibleCount;
            document.getElementById('total-count').textContent = issuesData.length;
            
            // Send filter to viewer
            sendFilterToViewer(statusFilter, severityFilter, assignedFilter);
        }
        
        // Clear all filters
        function clearFilters() {
            document.getElementById('filter-status').value = '';
            document.getElementById('filter-severity').value = '';
            document.getElementById('filter-assigned').value = '';
            applyFilters();
        }
        
        // Send filter message to viewer to update pushpins
        function sendFilterToViewer(status, severity, assigned) {
            const message = {
                type: 'FILTER_ISSUES',
                filters: {
                    status: status,
                    severity: severity,
                    assigned_to: assigned
                }
            };
            
            // Post to parent (wrapper)
            try {
                parent.postMessage(message, '*');
                window.top.postMessage(message, '*');
            } catch(e) {
                console.log('Could not send filter to viewer');
            }
        }
        // Excel-style column filters
        let activeFilters = {};
        let currentDropdown = null;

        // Initialize column filters
        function initColumnFilters() {
            const headers = document.querySelectorAll('.filterable-header');
            
            headers.forEach(header => {
                header.addEventListener('click', function(e) {
                    e.stopPropagation();
                    const column = this.dataset.column;
                    toggleFilterDropdown(this, column);
                });
            });
            
            // Close dropdown when clicking outside
            document.addEventListener('click', function() {
                if (currentDropdown) {
                    currentDropdown.remove();
                    currentDropdown = null;
                }
            });
        }

        function toggleFilterDropdown(headerElement, column) {
            // Close existing dropdown
            if (currentDropdown) {
                currentDropdown.remove();
                currentDropdown = null;
            }
            
            // Get unique values for this column
            const values = [...new Set(issuesData.map(item => item[column]))].filter(Boolean).sort();
            
            // Create dropdown
            const dropdown = document.createElement('div');
            dropdown.className = 'filter-dropdown active';
            dropdown.onclick = (e) => e.stopPropagation();
            
            // Search box
            dropdown.innerHTML = `
                <input type="text" class="filter-search" placeholder="Search..." onkeyup="filterDropdownOptions(this)">
                <div class="filter-options">
                    <div class="filter-option">
                        <input type="checkbox" id="select-all-${column}" checked onchange="toggleSelectAll('${column}')">
                        <label for="select-all-${column}"><strong>(Select All)</strong></label>
                    </div>
                    ${values.map(value => `
                        <div class="filter-option" data-value="${value}">
                            <input type="checkbox" id="filter-${column}-${value}" value="${value}" checked>
                            <label for="filter-${column}-${value}">${value}</label>
                        </div>
                    `).join('')}
                </div>
                <div class="filter-actions">
                    <button class="filter-btn filter-btn-apply" onclick="applyColumnFilter('${column}')">OK</button>
                    <button class="filter-btn filter-btn-clear" onclick="clearColumnFilter('${column}')">Clear</button>
                </div>
            `;
            
            // Position dropdown
            headerElement.style.position = 'relative';
            headerElement.appendChild(dropdown);
            currentDropdown = dropdown;
            
            // Pre-select based on active filters
            if (activeFilters[column]) {
                const checkboxes = dropdown.querySelectorAll('input[type="checkbox"]:not(#select-all-' + column + ')');
                checkboxes.forEach(cb => {
                    cb.checked = activeFilters[column].includes(cb.value);
                });
                updateSelectAll(column);
            }
        }

        function filterDropdownOptions(searchInput) {
            const searchTerm = searchInput.value.toLowerCase();
            const options = searchInput.parentElement.querySelectorAll('.filter-option:not(:first-child)');
            
            options.forEach(option => {
                const text = option.textContent.toLowerCase();
                option.style.display = text.includes(searchTerm) ? 'flex' : 'none';
            });
        }

        function toggleSelectAll(column) {
            const selectAll = document.getElementById('select-all-' + column);
            const checkboxes = document.querySelectorAll(`input[id^="filter-${column}-"]`);
            
            checkboxes.forEach(cb => {
                cb.checked = selectAll.checked;
            });
        }

        function updateSelectAll(column) {
            const selectAll = document.getElementById('select-all-' + column);
            const checkboxes = document.querySelectorAll(`input[id^="filter-${column}-"]`);
            const checkedCount = Array.from(checkboxes).filter(cb => cb.checked).length;
            
            selectAll.checked = checkedCount === checkboxes.length;
        }

        function applyColumnFilter(column) {
            const checkboxes = document.querySelectorAll(`input[id^="filter-${column}-"]:checked`);
            const selectedValues = Array.from(checkboxes).map(cb => cb.value);
            
            if (selectedValues.length === 0 || selectedValues.length === issuesData.filter(i => i[column]).length) {
                delete activeFilters[column];
            } else {
                activeFilters[column] = selectedValues;
            }
            
            applyAllFilters();
            updateFilterStatus();
            
            // Close dropdown
            if (currentDropdown) {
                currentDropdown.remove();
                currentDropdown = null;
            }
        }

        function clearColumnFilter(column) {
            delete activeFilters[column];
            applyAllFilters();
            updateFilterStatus();
            
            // Close dropdown
            if (currentDropdown) {
                currentDropdown.remove();
                currentDropdown = null;
            }
        }

        function applyAllFilters() {
            let visibleCount = 0;
            
            issuesData.forEach((issue, idx) => {
                const row = document.querySelector(`tr[onclick*="handleRowClick(${idx})"]`);
                if (!row) return;
                
                let shouldShow = true;
                
                // Check all active filters
                for (let column in activeFilters) {
                    if (!activeFilters[column].includes(issue[column])) {
                        shouldShow = false;
                        break;
                    }
                }
                
                row.style.display = shouldShow ? 'table-row' : 'none';
                if (shouldShow) visibleCount++;
            });
            
            // Update filtered column headers
            document.querySelectorAll('.filterable-header').forEach(header => {
                const column = header.dataset.column;
                if (activeFilters[column]) {
                    header.classList.add('filtered');
                } else {
                    header.classList.remove('filtered');
                }
            });
            
            // Send to viewer
            sendFiltersToViewer();
            
            console.log('Showing', visibleCount, 'of', issuesData.length, 'issues');
        }

        function updateFilterStatus() {
            let statusBar = document.querySelector('.filter-status-bar');
            
            if (!statusBar) {
                statusBar = document.createElement('div');
                statusBar.className = 'filter-status-bar';
                document.querySelector('.thumbnail-table').parentElement.insertBefore(
                    statusBar,
                    document.querySelector('.thumbnail-table')
                );
            }
            
            if (Object.keys(activeFilters).length === 0) {
                statusBar.classList.remove('active');
                return;
            }
            
            statusBar.classList.add('active');
            statusBar.innerHTML = '<strong>Active Filters:</strong> ' + 
                Object.entries(activeFilters).map(([column, values]) => {
                    const label = column.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
                    return `<span class="filter-tag">${label}: ${values.join(', ')} <span class="remove" onclick="clearColumnFilter('${column}')">×</span></span>`;
                }).join('');
        }

        function sendFiltersToViewer() {
            const message = {
                type: 'FILTER_ISSUES',
                filters: activeFilters
            };
            
            try {
                parent.postMessage(message, '*');
                window.top.postMessage(message, '*');
            } catch(e) {
                console.log('Could not send filter to viewer');
            }
        }

        // Initialize on load
        window.addEventListener('load', function() {
            // ... existing onload code ...
            
            initColumnFilters();
        });
    </script>
</body>
</html>
"""

@app.route('/api/debug/first-issue')
def debug_first_issue():
    """Debug endpoint - see what data is available"""
    try:
        if not issues_cache['data']:
            if FETCHER_AVAILABLE and fetch_all_issues:
                issues_cache['data'] = fetch_all_issues()
        
        issues = issues_cache['data'] or []
        
        if len(issues) > 0:
            first_issue = issues[0]
            return jsonify({
                'issue': first_issue,
                'available_fields': list(first_issue.keys()),
                'has_thumbnail_url': 'thumbnail_url' in first_issue,
                'has_thumbnail_base64': 'thumbnail_base64' in first_issue,
                'has_HTML_Image': 'HTML_Image' in first_issue,
            })
        
        return jsonify({'error': 'No issues found'})
    except Exception as e:
        return jsonify({'error': str(e)})


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
    print("   🖼️ http://localhost:5000/thumbnail-table.html  ← Thumbnail Table")
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