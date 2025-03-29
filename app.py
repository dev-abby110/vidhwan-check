import base64
from io import BytesIO
from flask import Flask, render_template, request, jsonify
import qrcode
from web3 import Web3
import hashlib

app = Flask(__name__, static_url_path='/static')

# Connect to Ganache
ganache_url = "http://127.0.0.1:8545"
web3 = Web3(Web3.HTTPProvider(ganache_url))

# Set contract address and ABI (replace with your contract details)
contract_address = "0x34005CF103E7546451cc9c43357942d12ca78540"
contract_abi = [
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": False,
                "internalType": "string",
                "name": "certificateHash",
                "type": "string"
            }
        ],
        "name": "CertificatePublished",
        "type": "event"
    },
    {
        "inputs": [
            {
                "internalType": "string",
                "name": "",
                "type": "string"
            }
        ],
        "name": "certificates",
        "outputs": [
            {"internalType": "string", "name": "awardeeName", "type": "string"},
            {"internalType": "string", "name": "certificateName", "type": "string"},
            {"internalType": "string", "name": "certificateCode", "type": "string"},
            {"internalType": "string", "name": "certificateHash", "type": "string"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function",
        "constant": True
    },
    {
        "inputs": [
            {"internalType": "string", "name": "awardeeName", "type": "string"},
            {"internalType": "string", "name": "certificateName", "type": "string"},
            {"internalType": "string", "name": "certificateCode", "type": "string"},
            {"internalType": "string", "name": "certificateHash", "type": "string"}
        ],
        "name": "publishCertificate",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "string", "name": "certificateHash", "type": "string"}
        ],
        "name": "verifyCertificate",
        "outputs": [
            {"internalType": "bool", "name": "", "type": "bool"},
            {
                "components": [
                    {"internalType": "string", "name": "awardeeName", "type": "string"},
                    {"internalType": "string", "name": "certificateName", "type": "string"},
                    {"internalType": "string", "name": "certificateCode", "type": "string"},
                    {"internalType": "string", "name": "certificateHash", "type": "string"},
                    {"internalType": "uint256", "name": "timestamp", "type": "uint256"}
                ],
                "internalType": "tuple",
                "name": "",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function",
        "constant": True
    }
]

# Create contract instance
contract = web3.eth.contract(address=contract_address, abi=contract_abi)


default_account = "0x24af5Ae5400781935b5d26611c671432AE41D098"


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/verify')
def verify():
    return render_template('verify.html')

@app.route('/login')
def login():
    return render_template('login.html')
@app.route('/login_admin')
def login_admin():
    return render_template('login-admin.html')

@app.route('/admin_login', methods=['POST'])
def admin_login():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Invalid input'}), 400

    username = data['username']
    password = data['password']

    # Check for hardcoded admin credentials
    if username == "admin" and password == "admin":
        return jsonify({'success': True, 'message': 'Login successful'})
    else:
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/publish', methods=['POST'])
def publish():
    data = request.get_json()
    required_fields = ["awardee_name", "certificate_name", "certificate_code"]
    
    # Validation checks
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    # Generate certificate hash
    certificate_hash = hashlib.sha512(
        f"{data['certificate_code']}:{data['certificate_name']}".encode()
    ).hexdigest().lower()

    try:
        # Generate QR code with verification URL
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        verification_url = f"{request.url_root}verify?certificate_hash={certificate_hash}"
        qr.add_data(verification_url)
        qr.make(fit=True)
        
        # Convert QR code to base64
        img_buffer = BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(img_buffer, format="PNG")
        qr_base64 = base64.b64encode(img_buffer.getvalue()).decode("utf-8")

        # Publish to blockchain
        tx_hash = contract.functions.publishCertificate(
            data['awardee_name'],
            data['certificate_name'],
            data['certificate_code'],
            certificate_hash
        ).transact({'from': default_account})

        web3.eth.wait_for_transaction_receipt(tx_hash)

        return jsonify({
            "message": "Certificate published successfully",
            "certificate_hash": certificate_hash,
            "qr_code": qr_base64  # Include QR code in response
        }), 201

    except Exception as e:
        return jsonify({"error": f"Failed to publish certificate: {str(e)}"}), 500
    
# In app.py, update the verify_certificate route:

@app.route('/verify_certificate', methods=['GET'])
def verify_certificate():
    certificate_hash = request.args.get('certificate_hash')
    if not certificate_hash:
        return jsonify({"verified": False, "message": "Missing certificate hash"}), 400

    try:
        # Explicit blockchain connection check
        if not web3.is_connected():
            return jsonify({
                "verified": False,
                "message": "Blockchain connection error"
            }), 500

        # Call the smart contract's verifyCertificate function
        verified, cert_data = contract.functions.verifyCertificate(certificate_hash).call()

        if not verified:
            return jsonify({
                "verified": False,
                "message": "Certificate not found on blockchain"
            }), 200

        # Extract certificate data from the tuple returned by the contract
        certificate = {
            "awardee_name": cert_data[0],  # Index 0 = awardeeName
            "certificate_name": cert_data[1],  # Index 1 = certificateName
            "certificate_code": cert_data[2],  # Index 2 = certificateCode
            "certificate_hash": cert_data[3],  # Index 3 = certificateHash
            "timestamp": cert_data[4]  # Index 4 = timestamp
        }

        return jsonify({
            "verified": True,
            "certificate": certificate
        }), 200

    except Exception as e:
        print(f"Verification error: {str(e)}")
        return jsonify({
            "verified": False,
            "message": f"Verification failed: {str(e)}"
        }), 500
    
if __name__ == "__main__":
    app.run(debug=True)
