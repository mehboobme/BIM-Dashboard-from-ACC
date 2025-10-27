"""
Diagnostic Script - Check Model Status
This will help identify why property extraction is failing
"""

import requests
import base64
import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv('APS_CLIENT_ID')
CLIENT_SECRET = os.getenv('APS_CLIENT_SECRET')
VERSION_URN = os.getenv('VERSION_URN')
BASE_URL = "https://developer.api.autodesk.com"

def print_header(msg):
    print("\n" + "="*70)
    print(f"  {msg}")
    print("="*70)

def get_token():
    """Get access token"""
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
        print("✅ Token obtained successfully")
        return response.json()['access_token']
    else:
        print(f"❌ Token failed: {response.status_code}")
        print(response.text)
        return None

def encode_urn(urn):
    """Encode URN for API"""
    encoded = base64.urlsafe_b64encode(urn.encode('utf-8')).decode('utf-8')
    return encoded.rstrip('=')

def check_manifest(token, urn):
    """Check model manifest/translation status"""
    encoded_urn = encode_urn(urn)
    url = f"{BASE_URL}/modelderivative/v2/designdata/{encoded_urn}/manifest"
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"\n📦 Checking manifest for:")
    print(f"   Original URN: {urn}")
    print(f"   Encoded URN: {encoded_urn}")
    print(f"   URL: {url}")
    
    response = requests.get(url, headers=headers, timeout=30)
    
    print(f"\n   Status Code: {response.status_code}")
    
    if response.status_code == 200:
        manifest = response.json()
        
        print(f"   ✅ Manifest retrieved")
        print(f"\n   Translation Status: {manifest.get('status')}")
        print(f"   Progress: {manifest.get('progress')}")
        
        # Check for derivatives
        derivatives = manifest.get('derivatives', [])
        print(f"\n   Derivatives found: {len(derivatives)}")
        
        for i, deriv in enumerate(derivatives):
            print(f"\n   Derivative {i+1}:")
            print(f"      Status: {deriv.get('status')}")
            print(f"      Output Type: {deriv.get('outputType')}")
            
            children = deriv.get('children', [])
            print(f"      Children: {len(children)}")
            
            for j, child in enumerate(children):
                print(f"\n         Child {j+1}:")
                print(f"            Type: {child.get('type')}")
                print(f"            Role: {child.get('role')}")
                print(f"            GUID: {child.get('guid')}")
                print(f"            Name: {child.get('name')}")
        
        return manifest
    else:
        print(f"   ❌ Failed to get manifest")
        print(f"   Response: {response.text}")
        return None

def check_metadata(token, urn):
    """Check model metadata"""
    encoded_urn = encode_urn(urn)
    url = f"{BASE_URL}/modelderivative/v2/designdata/{encoded_urn}/metadata"
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"\n📋 Checking metadata...")
    
    response = requests.get(url, headers=headers, timeout=30)
    
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code == 200:
        metadata = response.json()
        print(f"   ✅ Metadata retrieved")
        
        if 'data' in metadata and 'metadata' in metadata['data']:
            viewables = metadata['data']['metadata']
            print(f"\n   Viewables found: {len(viewables)}")
            
            for i, viewable in enumerate(viewables):
                print(f"\n   Viewable {i+1}:")
                print(f"      Name: {viewable.get('name')}")
                print(f"      GUID: {viewable.get('guid')}")
                print(f"      Role: {viewable.get('role')}")
                print(f"      Type: {viewable.get('type')}")
            
            return viewables
        else:
            print("   ⚠️  No viewables in metadata")
            return []
    else:
        print(f"   ❌ Failed to get metadata")
        print(f"   Response: {response.text}")
        return None

def check_properties(token, urn, guid):
    """Check if properties can be retrieved"""
    encoded_urn = encode_urn(urn)
    url = f"{BASE_URL}/modelderivative/v2/designdata/{encoded_urn}/metadata/{guid}/properties"
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"\n🔧 Checking properties for GUID: {guid}...")
    
    response = requests.get(url, headers=headers, timeout=60)
    
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code == 200:
        properties = response.json()
        
        if 'data' in properties and 'collection' in properties['data']:
            collection = properties['data']['collection']
            print(f"   ✅ Properties retrieved")
            print(f"   Objects with properties: {len(collection)}")
            
            if len(collection) > 0:
                print(f"\n   Sample object (first one):")
                first_obj = collection[0]
                print(f"      Object ID: {first_obj.get('objectid')}")
                print(f"      Name: {first_obj.get('name')}")
                print(f"      Properties count: {len(first_obj.get('properties', {}))}")
                
                # Show first few properties
                props = first_obj.get('properties', {})
                if props:
                    print(f"\n      Sample properties:")
                    for key, value in list(props.items())[:5]:
                        print(f"         {key}: {value}")
            
            return True
        else:
            print("   ⚠️  No property collection found")
            print(f"   Response structure: {list(properties.keys())}")
            return False
    else:
        print(f"   ❌ Failed to get properties")
        print(f"   Response: {response.text[:500]}")
        return False

def main():
    print_header("MODEL DIAGNOSTIC TOOL")
    
    print(f"\n📋 Configuration:")
    print(f"   CLIENT_ID: {CLIENT_ID[:20]}..." if CLIENT_ID else "   ❌ CLIENT_ID not set")
    print(f"   CLIENT_SECRET: {'*' * 20}..." if CLIENT_SECRET else "   ❌ CLIENT_SECRET not set")
    print(f"   VERSION_URN: {VERSION_URN}")
    
    if not all([CLIENT_ID, CLIENT_SECRET, VERSION_URN]):
        print("\n❌ Missing credentials in .env file")
        return
    
    # Step 1: Get token
    print_header("STEP 1: Authentication")
    token = get_token()
    if not token:
        return
    
    # Step 2: Check manifest
    print_header("STEP 2: Check Manifest")
    manifest = check_manifest(token, VERSION_URN)
    if not manifest:
        print("\n⚠️  Cannot proceed without manifest")
        print("\n💡 Possible solutions:")
        print("   1. Check if VERSION_URN is correct")
        print("   2. Model might need to be translated first")
        print("   3. Try a different URN format")
        return
    
    # Step 3: Check metadata
    print_header("STEP 3: Check Metadata")
    viewables = check_metadata(token, VERSION_URN)
    
    if not viewables:
        print("\n⚠️  No viewables found")
        print("\n💡 Possible solutions:")
        print("   1. Model translation might not be complete")
        print("   2. Try starting translation manually")
        return
    
    # Step 4: Check properties for each viewable
    print_header("STEP 4: Check Properties")
    
    success_count = 0
    for i, viewable in enumerate(viewables):
        guid = viewable.get('guid')
        name = viewable.get('name', 'Unknown')
        
        print(f"\n{'='*70}")
        print(f"Testing viewable {i+1}/{len(viewables)}: {name}")
        print(f"{'='*70}")
        
        if check_properties(token, VERSION_URN, guid):
            success_count += 1
            print(f"\n✅ Viewable {i+1} has accessible properties!")
        else:
            print(f"\n❌ Viewable {i+1} properties not accessible")
    
    # Summary
    print_header("DIAGNOSTIC SUMMARY")
    print(f"\n✅ Token: OK")
    print(f"✅ Manifest: OK")
    print(f"✅ Metadata: OK ({len(viewables)} viewables)")
    print(f"{'✅' if success_count > 0 else '❌'} Properties: {success_count}/{len(viewables)} viewables accessible")
    
    if success_count == 0:
        print("\n❌ ISSUE FOUND: No viewables have accessible properties")
        print("\n💡 Recommendations:")
        print("   1. The model might be a 2D drawing (no 3D properties)")
        print("   2. Translation might not be complete")
        print("   3. Try using a different model/version")
        print("\n📝 Your VERSION_URN:")
        print(f"   {VERSION_URN}")
        print("\n   This URN has '?version=1' which might be causing issues")
        print("   Try removing the version parameter:")
        print(f"   {VERSION_URN.split('?')[0]}")
    else:
        print(f"\n✅ SUCCESS: {success_count} viewable(s) have properties")
        print("\n💡 Next steps:")
        print("   1. Update config.py to use the working GUID")
        print("   2. Run: python main.py --full")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()