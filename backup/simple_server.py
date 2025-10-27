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

# Model URN mapping cache
MODEL_URN_CACHE = {}

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

def build_model_urn_mapping():
    """Build mapping from viewable_guid to model URN"""
    global MODEL_URN_CACHE
    
    if not issues_cache['data']:
        return {}
    
    # Get unique viewables from issues
    unique_viewables = {}
    for issue in issues_cache['data']:
        vg = issue.get('viewable_guid')
        vn = issue.get('viewable_name', 'Model')
        if vg and vg not in unique_viewables:
            unique_viewables[vg] = vn
    
    print(f"\n📊 Found {len(unique_viewables)} unique models:")
    for vg, vn in unique_viewables.items():
        print(f"   - {vn}")
    
    # Get URNs from environment variables
    hofuf_urn = os.getenv("HOFUF_URN", "").strip()
    snowdon_urn = os.getenv("SNOWDON_STR_URN", "").strip()
    
    if hofuf_urn and snowdon_urn:
        print("✅ Using URNs from .env file")
        MODEL_URN_CACHE = {
            'd039209d-a250-1473-1dd9-a3953b7c2e9b': hofuf_urn,
            '5fbd4c90-ff9e-87ff-78ff-b3654b67f6e4': snowdon_urn
        }
    else:
        print("⚠️ Add HOFUF_URN and SNOWDON_STR_URN to .env file")
    
    return MODEL_URN_CACHE

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

@app.route('/api/model-urn-for-viewable')
def get_model_urn_for_viewable():
    """Get the model URN for a specific viewable_guid"""
    try:
        viewable_guid = request.args.get('viewable_guid')
        
        if not viewable_guid:
            return jsonify({'error': 'viewable_guid required'}), 400
        
        # Build mapping if not done
        if not MODEL_URN_CACHE:
            build_model_urn_mapping()
        
        # Get the URN
        model_urn = MODEL_URN_CACHE.get(viewable_guid)
        
        if not model_urn:
            print(f"   ❌ No URN found for viewable: {viewable_guid}")
            return jsonify({'error': 'URN not found for this viewable'}), 404
        
        # Get viewable name
        viewable_name = 'Model'
        if issues_cache['data']:
            for issue in issues_cache['data']:
                if issue.get('viewable_guid') == viewable_guid:
                    viewable_name = issue.get('viewable_name', 'Model')
                    if viewable_name == '{3D}':
                        viewable_name = 'Snowdon Structure'
                    if '.' in viewable_name:
                        viewable_name = viewable_name.rsplit('.', 1)[0]
                    break
        
        # Encode URN
        urn_encoded = base64.urlsafe_b64encode(
            model_urn.encode('utf-8')
        ).decode('utf-8').rstrip('=')
        
        print(f"   ✅ Returning URN for {viewable_name}")
        
        return jsonify({
            'urn': urn_encoded,
            'viewable_guid': viewable_guid,
            'viewable_name': viewable_name,
            'model_name': viewable_name
        })
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
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
            font-weight: 600;}
        /* Filter status bar */
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
        
        /* Excel-style filter headers */
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
        font-weight: bold;
    }

    /* Filter dropdown popup */
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
        color: #333;  /* ← Dark text */
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
        color: #333;  /* ← Dark text */
    }

    .filter-options {
        max-height: 200px;
        overflow-y: auto;
    }

    .filter-option {
        padding: 8px 12px;
        cursor: pointer;
        font-size: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
        color: #333;  /* ← Dark text */
    }

    .filter-option:hover {
        background: #f0f0f0;
    }

    .filter-option label {
        color: #333;  /* ← Dark text */
        cursor: pointer;
        user-select: none;
    }

    .filter-option input[type="checkbox"] {
        cursor: pointer;
    }
            
    </style>
</head>
<body>

    <div id="debug-log" style="display:none;">Loading...</div>
     <!-- ========== ADD FILTER CONTAINER HERE ========== -->
    
    <table class="thumbnail-table">
        <thead>
            <tr>
                <th>Thumbnail</th>
                <th class="filterable-header" data-column="display_id">
                    ID <span class="filter-icon">▼</span>
                </th>
                <th class="filterable-header" data-column="title">
                    Title <span class="filter-icon">▼</span>
                </th>
                <th class="filterable-header" data-column="status">
                    Status <span class="filter-icon">▼</span>
                </th>
                <th class="filterable-header" data-column="severity">
                    Severity <span class="filter-icon">▼</span>
                </th>
                <th class="filterable-header" data-column="assigned_to">
                    Assigned To <span class="filter-icon">▼</span>
                </th>
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
            
        # Get viewable info
            viewable_name = issue.get('viewable_name', 'Model')
            viewable_guid = issue.get('viewable_guid', '')
            if '.' in viewable_name:
                viewable_name = viewable_name.rsplit('.', 1)[0]
            
            html += f"""
            {{
                issue_id: '{issue_id}',
                display_id: '{issue.get('display_id', '')}',
                title: '{title}',
                status: '{issue.get('status', '')}',
                severity: '{issue.get('severity', '')}',
                assigned_to: '{issue.get('assigned_to', '')}',
                pin_x: {issue.get('pin_x', 0)},
                pin_y: {issue.get('pin_y', 0)},
                pin_z: {issue.get('pin_z', 0)},
                viewable_name: '{viewable_name}',
                viewable_guid: '{viewable_guid}',
                thumbnail: `{thumbnail}`
            }},
"""
        
        html += """
        ];
        
        // Load images after page loads
        window.onload = function(){
            logDebug('Page loaded');            
            issuesData.forEach((issue, idx) => {
                const img = document.getElementById('img_' + idx);
                if (img && issue.thumbnail) {
                    img.src = issue.thumbnail;
                    logDebug('Loaded img ' + idx);
                }
            });
                     
            logDebug('All loaded!');
        };
                            
        function handleRowClick(idx) {
            const issue = issuesData[idx];
            logDebug('Clicked: ' + issue.display_id);
            sendMessageToViewer(issue);
        }
        
        function sendMessageToViewer(issue) {
            console.log('🔵 CLICK DETECTED:', issue.display_id);
            console.log('   Viewable GUID:', issue.viewable_guid);
            console.log('   Viewable Name:', issue.viewable_name);
            logDebug('Sending message...');
            
            const message = {
                type: 'LOAD_MODEL_AND_NAVIGATE',
                issue_id: issue.issue_id,
                display_id: issue.display_id,
                pin_x: issue.pin_x,
                pin_y: issue.pin_y,
                pin_z: issue.pin_z,
                title: issue.title,
                viewable_name: issue.viewable_name,
                viewable_guid: issue.viewable_guid,
                timestamp: Date.now()
            };
            
            console.log('📤 Sending message:', message);
            
            // Method 1: Post to parent
            try {
                parent.postMessage(message, '*');
                console.log('✅ Sent to parent');
                logDebug('Sent to parent');
            } catch(e) {
                console.error('❌ Parent failed:', e);
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
        
        // ========== EXCEL-STYLE FILTER FUNCTIONS ==========
        let activeFilters = {};
        let currentDropdown = null;

        function initColumnFilters() {
            const headers = document.querySelectorAll('.filterable-header');
            
            headers.forEach(header => {
                header.addEventListener('click', function(e) {
                    e.stopPropagation();
                    const column = this.dataset.column;
                    toggleFilterDropdown(this, column);
                });
            });
            
            document.addEventListener('click', function() {
                if (currentDropdown) {
                    currentDropdown.remove();
                    currentDropdown = null;
                }
            });
            
            logDebug('Excel filters initialized');
        }

        function toggleFilterDropdown(headerElement, column) {
            if (currentDropdown) {
                currentDropdown.remove();
                currentDropdown = null;
            }
            
            const values = [...new Set(issuesData.map(item => item[column]))].filter(Boolean).sort();
            
            const dropdown = document.createElement('div');
            dropdown.className = 'filter-dropdown active';
            dropdown.onclick = (e) => e.stopPropagation();
            
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
            
            headerElement.appendChild(dropdown);
            currentDropdown = dropdown;
            
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
            
            const allValues = issuesData.map(i => i[column]).filter(Boolean);
            const uniqueValues = [...new Set(allValues)];
            
            if (selectedValues.length === 0 || selectedValues.length === uniqueValues.length) {
                delete activeFilters[column];
            } else {
                activeFilters[column] = selectedValues;
            }
            
            applyAllFilters();
            updateFilterStatus();
            
            if (currentDropdown) {
                currentDropdown.remove();
                currentDropdown = null;
            }
        }

        function clearColumnFilter(column) {
            delete activeFilters[column];
            applyAllFilters();
            updateFilterStatus();
            
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
                
                for (let column in activeFilters) {
                    if (!activeFilters[column].includes(issue[column])) {
                        shouldShow = false;
                        break;
                    }
                }
                
                row.style.display = shouldShow ? 'table-row' : 'none';
                if (shouldShow) visibleCount++;
            });
            
            document.querySelectorAll('.filterable-header').forEach(header => {
                const column = header.dataset.column;
                if (activeFilters[column]) {
                    header.classList.add('filtered');
                } else {
                    header.classList.remove('filtered');
                }
            });
            
            sendFiltersToViewer();
            
            logDebug('Showing ' + visibleCount + ' of ' + issuesData.length + ' issues');
        }

        function updateFilterStatus() {
            let statusBar = document.querySelector('.filter-status-bar');
            
            if (!statusBar) {
                statusBar = document.createElement('div');
                statusBar.className = 'filter-status-bar';
                const table = document.querySelector('.thumbnail-table');
                table.parentElement.insertBefore(statusBar, table);
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
                logDebug('Filters sent');
            } catch(e) {
                logDebug('Could not send filters');
            }
        }
        
        // ========== COLUMN RESIZING ==========
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
                        if (newWidth > 50) {
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
        
        // ========== INITIALIZE ON LOAD ==========
        window.addEventListener('load', function() {
            logDebug('Page loaded');
            
            // Load thumbnails
            issuesData.forEach((issue, idx) => {
                const img = document.getElementById('img_' + idx);
                if (img && issue.thumbnail) {
                    img.src = issue.thumbnail;
                    logDebug('Loaded img ' + idx);
                }
            });
            
            // Initialize filters
            initColumnFilters();
            logDebug('Filters initialized');
            
            // Make columns resizable
            makeColumnsResizable();
            
            logDebug('All loaded!');
        });
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
            color: #333;  /* ← ADD THIS LINE */
        }

        .filter-option label {
            color: #333;  /* ← ADD THIS BLOCK */
            cursor: pointer;
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
                        viewerFrame.contentWindow.postMessage(event.data, '*');
                        showStatus(`Navigating to ${event.data.display_id}`);
                    }
                    
                    if (event.data && event.data.type === 'FILTER_ISSUES') {
                        console.log('✅ Relaying filters to viewer...');
                        const viewerFrame = document.getElementById('viewer-frame');
                        viewerFrame.contentWindow.postMessage(event.data, '*');
                        showStatus(`Filtered: ${Object.keys(event.data.filters).length} columns`);
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
        
    </script>
</body>
</html>
"""

# Complete /powerbi-embed.html endpoint with ALL features
# Replace the existing @app.route('/powerbi-embed.html') function with this:

@app.route('/powerbi-embed.html')
def powerbi_embed():
    """Combined viewer + thumbnails with ALL custom settings + filters + comments"""
    
    # Get issues data
    if not issues_cache['data']:
        if FETCHER_AVAILABLE and fetch_all_issues:
            issues_cache['data'] = fetch_all_issues()
    
    issues = issues_cache['data'] or []
    issues_with_coords = [i for i in issues if i.get('pin_x') and i.get('pin_y') and i.get('pin_z')]
    
    # Start building HTML
    html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="https://developer.api.autodesk.com/modelderivative/v2/viewers/7.*/style.min.css">
    <script src="https://developer.api.autodesk.com/modelderivative/v2/viewers/7.*/viewer3D.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: Arial, sans-serif; 
            overflow: hidden;
        }
        
        #container {
            display: flex;
            flex-direction: column;
            height: 100vh;
            width: 100vw;
        }
        
        #viewer {
            flex: 1;
            position: relative;
            min-height: 50vh;
        }
        
        #table-container {
            flex: 1;
            overflow: auto;
            border-top: 3px solid #667eea;
            background: #f5f5f5;
            padding: 10px;
        }
        
        /* ========== MAKE AUTODESK INBUILT ICONS SMALLER ========== */
        .adsk-viewing-viewer .adsk-button,
        .adsk-control-group .adsk-button {
            width: 20px !important;
            height: 20px !important;
            min-width: 20px !important;
            min-height: 20px !important;
            margin: 1px !important;
            padding: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            overflow: visible !important;
            line-height: 20px !important;
        }

        .adsk-viewing-viewer .adsk-button .adsk-icon,
        .adsk-viewing-viewer .adsk-button svg,
        .adsk-viewing-viewer .adsk-button img,
        .adsk-control-group .adsk-button .adsk-icon,
        .adsk-control-group .adsk-button svg,
        .adsk-control-group .adsk-button img {
            transform: scale(0.1) !important;
            transform-origin: center center !important;
            flex-shrink: 0 !important;
        }

        .adsk-viewing-viewer .adsk-button .adsk-icon *,
        .adsk-viewing-viewer .adsk-button svg *,
        .adsk-control-group .adsk-button .adsk-icon *,
        .adsk-control-group .adsk-button svg * {
            transform: scale(1) !important;
        }

        .adsk-viewing-viewer .adsk-toolbar,
        .adsk-toolbar-group,
        .adsk-control-group {
            height: auto !important;
            padding: 1px !important;
        }

        .adsk-viewing-viewer .adsk-toolbar-group {
            display: flex !important;
            align-items: center !important;
        }

        .adsk-viewing-viewer .homeViewWrapper {
            width: 20px !important;
            height: 20px !important;
        }

        .adsk-viewing-viewer .homeViewWrapper canvas {
            width: 20px !important;
            height: 20px !important;
        }
        /* ========================================================= */

        /* ======= DROPDOWN MENU ======= */
        .dropdown {
            position: absolute;
            top: 25px;
            right: 10px;
            z-index: 100;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .dropdown-button {
            width: 25px;
            height: 25px;
            border: none;
            border-radius: 50px;
            background: #3498db;
            color: white;
            font-size: 12px;
            cursor: pointer;
            box-shadow: 0 4px 10px rgba(0,0,0,0.2);
            transition: background 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .dropdown-button:hover {
            background: #2980b9;
        }

        .dropdown-content {
            display: none;
            position: absolute;
            top: 25px;
            right: 0;
            background-color: rgba(255,255,255,0.97);
            min-width: 50px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.25);
            border-radius: 10px;
            overflow: hidden;
            font-size: 10px;
            animation: fadeIn 0.2s ease-in-out;
        }

        .dropdown-content button {
            display: flex;
            align-items: center;
            width: 100%;
            background: none;
            border: none;
            padding: 5px 5px;
            cursor: pointer;
            text-align: left;
            font-size: 10px;
            color: #333;
            transition: background 0.2s;
        }

        .dropdown-content button:hover {
            background: #f1f1f1;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-5px); }
            to { opacity: 1; transform: translateY(0); }
        }

        #status {
            position: absolute;
            top: 10px;
            left: 10px;
            z-index: 100;
            padding: 8px 12px;
            border-radius: 6px;
            color: white;
            background: #3498db;
            font-size: 15px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
            display: none;
        }

        #model-name {
            position: absolute;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 100;
            padding: 10px 20px;
            border-radius: 8px;
            color: white;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            font-size: 16px;
            font-weight: 600;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            text-align: center;
            letter-spacing: 0.5px;
        }

        #info {
            position: absolute;
            top: 2px;
            left: 2px;
            z-index: 100;
            background: rgba(255,255,255,0.95);
            border-radius: 8px;
            padding: 5px;
            width: 150px;
            max-height: 200px;
            overflow-y: auto;
            display: none;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
            font-size: 10px;
        }

        .error { background: #e74c3c !important; }
        .success { background: #2ecc71 !important; }

        /* ========== PUSHPIN STYLES ========== */
        .custom-pushpin {
            position: absolute;
            width: 15px;
            height: 15px;
            background: #e74c3c;
            border: 0px solid white;
            border-radius: 50%;
            cursor: pointer;
            box-shadow: 0 1px 2px rgba(0,0,0,0.4);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 12px;
            transition: all 0.2s;
            z-index: 50;
        }

        .custom-pushpin:hover {
            transform: scale(1.3);
            z-index: 1000;
            box-shadow: 0 4px 12px rgba(0,0,0,0.6);
        }

        .custom-pushpin.selected {
            background: #2ecc71;
            transform: scale(1.4);
            z-index: 1000;
        }

        /* ========== THUMBNAIL TABLE ========== */
        .thumbnail-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
        }
        
        .thumbnail-table th {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 3px;
            text-align: center;
            font-size: 12px;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        
        .thumbnail-table td {
            padding: 8px;
            border-bottom: 1px solid #e0e0e0;
            font-size: 11px;
        }
        
        .thumbnail-img {
            width: 70px;
            height: 52px;
            object-fit: cover;
            border-radius: 4px;
            cursor: pointer;
            border: 2px solid #ddd;
            transition: all 0.2s;
        }
        
        .thumbnail-img:hover {
            transform: scale(1.1);
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

        /* ========== EXCEL-STYLE FILTERS ========== */
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
            font-weight: bold;
        }

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
            color: #333;
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
            color: #333;
        }

        .filter-options {
            max-height: 200px;
            overflow-y: auto;
        }

        .filter-option {
            padding: 8px 12px;
            cursor: pointer;
            font-size: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            color: #333;
        }

        .filter-option:hover {
            background: #f0f0f0;
        }

        .filter-option label {
            color: #333;
            cursor: pointer;
            user-select: none;
        }

        .filter-actions {
            display: flex;
            gap: 5px;
            padding: 10px;
            border-top: 1px solid #e0e0e0;
        }

        .filter-btn {
            flex: 1;
            padding: 6px 12px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
            font-weight: 600;
        }

        .filter-btn-apply {
            background: #667eea;
            color: white;
        }

        .filter-btn-apply:hover {
            background: #5568d3;
        }

        .filter-btn-clear {
            background: #e0e0e0;
            color: #333;
        }

        .filter-btn-clear:hover {
            background: #d0d0d0;
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
    <div id="container">
        <div id="viewer">
            <div id="status">Initializing...</div>
            <div id="model-name">Loading model...</div>
            
            <!-- Dropdown Menu -->
            <div class="dropdown">
                <button class="dropdown-button">☰</button>
                <div class="dropdown-content" id="dropdownMenu">
                    <button onclick="resetView()">🔄 Reset View</button>
                    <button onclick="fitToView()">📐 Fit to View</button>
                    <button onclick="showAll()">👁️ Show All</button>
                    <button onclick="togglePushpins()">📍 Toggle Pushpins</button>
                    <button onclick="toggleInfo()">ℹ️ Info Panel</button>
                </div>
            </div>
            
            <div id="info"></div>
        </div>
        
        <div id="table-container">
            <table class="thumbnail-table">
                <thead>
                    <tr>
                        <th>Thumbnail</th>
                        <th class="filterable-header" data-column="display_id">
                            ID <span class="filter-icon">▼</span>
                        </th>
                        <th class="filterable-header" data-column="title">
                            Title <span class="filter-icon">▼</span>
                        </th>
                        <th class="filterable-header" data-column="status">
                            Status <span class="filter-icon">▼</span>
                        </th>
                        <th class="filterable-header" data-column="severity">
                            Severity <span class="filter-icon">▼</span>
                        </th>
                        <th class="filterable-header" data-column="assigned_to">
                            Assigned To <span class="filter-icon">▼</span>
                        </th>
                        <th>Comments</th>
                        <th>Comments By</th>
                    </tr>
                </thead>
                <tbody id="table-body"></tbody>
            </table>
        </div>
    </div>
    
    <script>
        let viewer = null;
        let currentModel = null;
        let currentModelUrn = null;
        let currentViewableGuid = null;
        let issuesData = [];
        let pushpins = [];
        let loadingModel = false;
        let pushpinsVisible = true;
        let selectedPushpin = null;
        let activeFilters = {};
        let currentDropdown = null;
        
        // Store issue data from server
        const allIssuesData = [
"""
    
    # Add issue data as JavaScript array
    for issue in issues_with_coords:
        # Pre-process strings to escape quotes (avoid backslash in f-string)
        # Convert to string first to avoid AttributeError
        issue_id = str(issue.get('issue_id', '')).replace("'", "&#39;")
        display_id = str(issue.get('display_id', '')).replace("'", "&#39;")
        title = str(issue.get('title', '')).replace("'", "&#39;")
        status = str(issue.get('status', '')).replace("'", "&#39;")
        severity = str(issue.get('severity', '')).replace("'", "&#39;")
        assigned_to = str(issue.get('assigned_to', '')).replace("'", "&#39;")
        comment_1 = str(issue.get('comment_1', '')).replace("'", "&#39;")
        comment_1_by = str(issue.get('comment_1_by', '')).replace("'", "&#39;")
        thumbnail = issue.get('thumbnail_base64', '')
        viewable_name = str(issue.get('viewable_name', 'Model'))
        viewable_guid = str(issue.get('viewable_guid', ''))
        if '.' in viewable_name:
            viewable_name = viewable_name.rsplit('.', 1)[0]
        
        pin_x = issue.get('pin_x', 0)
        pin_y = issue.get('pin_y', 0)
        pin_z = issue.get('pin_z', 0)
        
        html += f"""
            {{
                issue_id: '{issue_id}',
                display_id: '{display_id}',
                title: '{title}',
                status: '{status}',
                severity: '{severity}',
                assigned_to: '{assigned_to}',
                comment_1: '{comment_1}',
                comment_1_by: '{comment_1_by}',
                pin_x: {pin_x},
                pin_y: {pin_y},
                pin_z: {pin_z},
                viewable_name: '{viewable_name}',
                viewable_guid: '{viewable_guid}',
                thumbnail: `{thumbnail}`
            }},
"""
    
    html += """
        ];
        
        // Initialize viewer
        async function initViewer() {
            updateStatus('Getting access token...', 'status');
            
            try {
                const tokenResp = await fetch('/api/token');
                const tokenData = await tokenResp.json();
                
                const options = {
                    env: 'AutodeskProduction',
                    api: 'derivativeV2',
                    accessToken: tokenData.access_token
                };
                
                Autodesk.Viewing.Initializer(options, function() {
                    const viewerDiv = document.getElementById('viewer');
                    viewer = new Autodesk.Viewing.GuiViewer3D(viewerDiv);
                    viewer.start();
                    
                    updateStatus('Loading issues...', 'status');
                    loadIssuesTable();
                    initColumnFilters();
                });
            } catch(error) {
                console.error('Init error:', error);
                updateStatus('❌ Initialization failed', 'error');
            }
        }
        
        // Load issues and create table
        function loadIssuesTable() {
            issuesData = allIssuesData;
            const tbody = document.getElementById('table-body');
            tbody.innerHTML = '';
            
            issuesData.forEach((issue, idx) => {
                const row = document.createElement('tr');
                row.className = 'clickable-row';
                row.onclick = () => handleIssueClick(issue, idx);
                row.dataset.index = idx;
                
                const statusClass = issue.status.toLowerCase().includes('closed') ? 'status-closed' : 'status-open';
                const comments = issue.comment_1 || 'No comments';
                const commentsShort = comments.length > 50 ? comments.substring(0, 50) + '...' : comments;
                
                row.innerHTML = `
                    <td><img class="thumbnail-img" src="${issue.thumbnail || ''}" onerror="this.style.display='none'" /></td>
                    <td><strong>${issue.display_id}</strong></td>
                    <td>${issue.title}</td>
                    <td><span class="status-badge ${statusClass}">${issue.status}</span></td>
                    <td>${issue.severity || 'N/A'}</td>
                    <td>${issue.assigned_to || 'Unassigned'}</td>
                    <td>${commentsShort}</td>
                    <td>${issue.comment_1_by || ''}</td>
                `;
                
                tbody.appendChild(row);
            });
            
            updateStatus(`✅ Loaded ${issuesData.length} issues`, 'success');
            setTimeout(() => document.getElementById('status').style.display = 'none', 2000);
        }
        
        // Handle issue click - load model and navigate
        async function handleIssueClick(issue, idx) {
            if (loadingModel) {
                console.log('⏳ Model already loading...');
                return;
            }
            
            console.log('🔵 Issue clicked:', issue.display_id);
            
            try {
                updateStatus(`Getting model info...`, 'status');
                
                // Get model URN
                const response = await fetch(`/api/model-urn-for-viewable?viewable_guid=${issue.viewable_guid}`);
                const data = await response.json();
                
                if (!data.urn) {
                    updateStatus('❌ Model URN not found', 'error');
                    return;
                }
                
                console.log('📦 Model URN:', data.urn);
                
                // Update model name
                updateModelName(data.model_name || issue.viewable_name);
                
                // Check if different model
                if (currentModelUrn !== data.urn) {
                    console.log('🔄 Loading new model:', data.model_name);
                    loadingModel = true;
                    currentModelUrn = data.urn;
                    currentViewableGuid = issue.viewable_guid;
                    
                    updateStatus(`Loading ${data.model_name}...`, 'status');
                    
                    // Unload current model
                    if (currentModel) {
                        viewer.unloadModel(currentModel);
                        clearPushpins();
                    }
                    
                    // Load new model
                    const documentId = 'urn:' + data.urn;
                    Autodesk.Viewing.Document.load(documentId, 
                        (doc) => onModelLoadSuccess(doc, issue),
                        (errorCode, errorMsg) => {
                            console.error('❌ Failed:', errorCode, errorMsg);
                            updateStatus('❌ Failed to load model', 'error');
                            loadingModel = false;
                        }
                    );
                } else {
                    console.log('✅ Same model, navigating');
                    navigateToIssue(issue);
                }
                
            } catch(error) {
                console.error('❌ Error:', error);
                updateStatus('❌ Error: ' + error.message, 'error');
                loadingModel = false;
            }
        }
        
        function onModelLoadSuccess(doc, issue) {
            const viewable = doc.getRoot().getDefaultGeometry();
            
            viewer.loadDocumentNode(doc, viewable).then(model => {
                currentModel = model;
                loadingModel = false;
                
                console.log('✅ Model loaded');
                updateStatus('✅ Model loaded', 'success');
                
                // Create pushpins for this model
                createPushpinsForCurrentModel();
                
                // Navigate to issue
                setTimeout(() => navigateToIssue(issue), 500);
            }).catch(error => {
                console.error('❌ Error loading model:', error);
                updateStatus('❌ Error loading model', 'error');
                loadingModel = false;
            });
        }
        
        // Navigate to issue location
        function navigateToIssue(issue) {
            if (issue.pin_x && issue.pin_y && issue.pin_z) {
                const x = parseFloat(issue.pin_x);
                const y = parseFloat(issue.pin_y);
                const z = parseFloat(issue.pin_z);
                
                if (!isNaN(x) && !isNaN(y) && !isNaN(z)) {
                    const position = new THREE.Vector3(x, y, z);
                    focusOnPosition(position);
                    
                    // Highlight the pushpin
                    const pushpin = pushpins.find(p => p.issue && p.issue.issue_id === issue.issue_id);
                    if (pushpin) {
                        selectPushpin(pushpin.element, position, pushpin.issue);
                    }
                    
                    updateStatus(`✅ Navigated to Issue ${issue.display_id}`, 'success');
                    setTimeout(() => document.getElementById('status').style.display = 'none', 2000);
                }
            }
        }
        
        function focusOnPosition(position) {
            const distance = 30;
            const camera = viewer.navigation.getCamera();
            const direction = camera.position.clone().sub(position).normalize();
            const newPos = position.clone().add(direction.multiplyScalar(distance));
            
            viewer.navigation.setView(newPos, position);
            viewer.navigation.setVerticalFov(40, true);
        }
        
        // Create pushpins for current model
        function createPushpinsForCurrentModel() {
            clearPushpins();
            
            if (!currentViewableGuid) return;
            
            // Apply filters to determine which pushpins to show
            let modelIssues = issuesData.filter(issue => 
                issue.viewable_guid === currentViewableGuid &&
                issue.pin_x && issue.pin_y && issue.pin_z
            );
            
            // Apply active filters
            for (let column in activeFilters) {
                modelIssues = modelIssues.filter(issue => 
                    activeFilters[column].includes(issue[column])
                );
            }
            
            console.log(`📍 Creating ${modelIssues.length} pushpins for current model`);
            
            modelIssues.forEach((issue) => {
                const position = new THREE.Vector3(
                    parseFloat(issue.pin_x),
                    parseFloat(issue.pin_y),
                    parseFloat(issue.pin_z)
                );
                
                const pushpinDiv = document.createElement('div');
                pushpinDiv.className = 'custom-pushpin';
                pushpinDiv.textContent = issue.display_id;
                pushpinDiv.title = issue.title;
                
                pushpinDiv.onclick = (e) => {
                    e.stopPropagation();
                    selectPushpin(pushpinDiv, position, issue);
                    focusOnPosition(position);
                };
                
                viewer.container.appendChild(pushpinDiv);
                
                function updatePosition() {
                    if (!viewer || !viewer.impl) return;
                    const screenPoint = viewer.worldToClient(position);
                    if (screenPoint) {
                        pushpinDiv.style.left = (screenPoint.x - 7.5) + 'px';
                        pushpinDiv.style.top = (screenPoint.y - 7.5) + 'px';
                        pushpinDiv.style.display = pushpinsVisible ? 'flex' : 'none';
                    }
                }
                
                viewer.addEventListener(Autodesk.Viewing.CAMERA_CHANGE_EVENT, updatePosition);
                updatePosition();
                
                pushpins.push({ element: pushpinDiv, position: position, issue: issue });
            });
        }
        
        function selectPushpin(element, position, issue) {
            if (selectedPushpin) {
                selectedPushpin.classList.remove('selected');
            }
            
            element.classList.add('selected');
            selectedPushpin = element;
            
            showIssueDetails(issue);
        }
        
        function showIssueDetails(issue) {
            let info = `<strong>${issue.title || 'Issue'}</strong><br>`;
            info += `<small>ID: ${issue.display_id}</small><br><br>`;
            info += `<strong>Status:</strong> ${issue.status}<br>`;
            info += `<strong>Severity:</strong> ${issue.severity || 'N/A'}<br>`;
            info += `<strong>Assigned:</strong> ${issue.assigned_to || 'Unassigned'}<br>`;
            
            if (issue.comment_1) {
                info += `<br><strong>Comment:</strong><br>${issue.comment_1.substring(0, 100)}<br>`;
                info += `<strong>By:</strong> ${issue.comment_1_by}<br>`;
            }
            
            const infoDiv = document.getElementById('info');
            infoDiv.innerHTML = info;
            infoDiv.style.display = 'block';
        }
        
        function clearPushpins() {
            pushpins.forEach(pin => {
                if (pin.element && pin.element.parentNode) {
                    pin.element.parentNode.removeChild(pin.element);
                }
            });
            pushpins = [];
            selectedPushpin = null;
        }
        
        function updateModelName(name) {
            const modelNameDiv = document.getElementById('model-name');
            if (modelNameDiv && name) {
                let modelName = name;
                if (modelName.includes('.')) {
                    modelName = modelName.split('.')[0];
                }
                modelNameDiv.textContent = modelName;
            }
        }
        
        function updateStatus(msg, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.textContent = msg;
            statusDiv.style.display = 'block';
            
            statusDiv.className = '';
            if (type === 'error') statusDiv.classList.add('error');
            if (type === 'success') statusDiv.classList.add('success');
        }
        
        // Dropdown menu functions
        function resetView() {
            if (viewer) {
                viewer.clearSelection();
                viewer.showAll();
                viewer.fitToView();
            }
            if (selectedPushpin) {
                selectedPushpin.classList.remove('selected');
                selectedPushpin = null;
            }
            closeDropdown();
        }
        
        function fitToView() {
            if (viewer) viewer.fitToView();
            closeDropdown();
        }
        
        function showAll() {
            if (viewer) {
                viewer.showAll();
                viewer.fitToView();
            }
            closeDropdown();
        }
        
        function togglePushpins() {
            pushpinsVisible = !pushpinsVisible;
            pushpins.forEach(pin => {
                if (pin.element) {
                    pin.element.style.display = pushpinsVisible ? 'flex' : 'none';
                }
            });
            closeDropdown();
        }
        
        function toggleInfo() {
            const infoDiv = document.getElementById('info');
            infoDiv.style.display = infoDiv.style.display === 'none' ? 'block' : 'none';
            closeDropdown();
        }
        
        function closeDropdown() {
            document.getElementById('dropdownMenu').style.display = 'none';
        }
        
        // Dropdown toggle
        const dropdownButton = document.querySelector('.dropdown-button');
        const dropdownMenu = document.getElementById('dropdownMenu');
        
        dropdownButton.addEventListener('click', (e) => {
            e.stopPropagation();
            dropdownMenu.style.display = dropdownMenu.style.display === 'block' ? 'none' : 'block';
        });
        
        window.addEventListener('click', () => dropdownMenu.style.display = 'none');
        
        // ========== EXCEL-STYLE FILTER FUNCTIONS ==========
        function initColumnFilters() {
            const headers = document.querySelectorAll('.filterable-header');
            
            headers.forEach(header => {
                header.addEventListener('click', function(e) {
                    e.stopPropagation();
                    const column = this.dataset.column;
                    toggleFilterDropdown(this, column);
                });
            });
            
            document.addEventListener('click', function() {
                if (currentDropdown) {
                    currentDropdown.remove();
                    currentDropdown = null;
                }
            });
        }

        function toggleFilterDropdown(headerElement, column) {
            if (currentDropdown) {
                currentDropdown.remove();
                currentDropdown = null;
            }
            
            const values = [...new Set(allIssuesData.map(item => item[column]))].filter(Boolean).sort();
            
            const dropdown = document.createElement('div');
            dropdown.className = 'filter-dropdown active';
            dropdown.onclick = (e) => e.stopPropagation();
            
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
            
            headerElement.appendChild(dropdown);
            currentDropdown = dropdown;
            
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
            
            const allValues = allIssuesData.map(i => i[column]).filter(Boolean);
            const uniqueValues = [...new Set(allValues)];
            
            if (selectedValues.length === 0 || selectedValues.length === uniqueValues.length) {
                delete activeFilters[column];
            } else {
                activeFilters[column] = selectedValues;
            }
            
            applyAllFilters();
            updateFilterStatus();
            
            if (currentDropdown) {
                currentDropdown.remove();
                currentDropdown = null;
            }
        }

        function clearColumnFilter(column) {
            delete activeFilters[column];
            applyAllFilters();
            updateFilterStatus();
            
            if (currentDropdown) {
                currentDropdown.remove();
                currentDropdown = null;
            }
        }

        function applyAllFilters() {
            let visibleCount = 0;
            const tbody = document.getElementById('table-body');
            const rows = tbody.querySelectorAll('tr');
            
            rows.forEach((row, idx) => {
                const issue = allIssuesData[idx];
                if (!issue) return;
                
                let shouldShow = true;
                
                for (let column in activeFilters) {
                    if (!activeFilters[column].includes(issue[column])) {
                        shouldShow = false;
                        break;
                    }
                }
                
                row.style.display = shouldShow ? 'table-row' : 'none';
                if (shouldShow) visibleCount++;
            });
            
            // Update filtered issuesData for pushpins
            if (Object.keys(activeFilters).length > 0) {
                issuesData = allIssuesData.filter(issue => {
                    for (let column in activeFilters) {
                        if (!activeFilters[column].includes(issue[column])) {
                            return false;
                        }
                    }
                    return true;
                });
            } else {
                issuesData = allIssuesData;
            }
            
            // Update filter icons
            document.querySelectorAll('.filterable-header').forEach(header => {
                const column = header.dataset.column;
                if (activeFilters[column]) {
                    header.classList.add('filtered');
                } else {
                    header.classList.remove('filtered');
                }
            });
            
            // Recreate pushpins with filtered data
            if (currentModel && currentViewableGuid) {
                createPushpinsForCurrentModel();
            }
            
            console.log(`Showing ${visibleCount} of ${allIssuesData.length} issues`);
        }

        function updateFilterStatus() {
            let statusBar = document.querySelector('.filter-status-bar');
            
            if (!statusBar) {
                statusBar = document.createElement('div');
                statusBar.className = 'filter-status-bar';
                const table = document.querySelector('.thumbnail-table');
                table.parentElement.insertBefore(statusBar, table);
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
        
        // Initialize on load
        window.addEventListener('load', initViewer);
    </script>
</body>
</html>
"""
    
    return html

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
    print(f"   HOFUF_URN: {'✅' if os.getenv('HOFUF_URN') else '❌'}")
    print(f"   SNOWDON_URN: {'✅' if os.getenv('SNOWDON_STR_URN') else '❌'}")
    print(f"   Issues Fetcher: {'✅' if FETCHER_AVAILABLE else '❌'}")
    
    # Pre-load issues and build URN mapping
    if FETCHER_AVAILABLE and fetch_all_issues:
        try:
            print("\n📥 Pre-loading issues...")
            issues_cache['data'] = fetch_all_issues()
            issues_cache['timestamp'] = time.time()
            print(f"   ✅ Loaded {len(issues_cache['data'])} issues")
            
            # Build URN mapping
            build_model_urn_mapping()
            
        except Exception as e:
            print(f"   ⚠️ Could not preload: {e}")
    
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