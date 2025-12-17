# ==========================================
# COMPLETE BACKEND - JWT FIXED + Google Gemini
# ==========================================

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import stripe
import PyPDF2
import requests
import os
from datetime import datetime, timedelta
import google.generativeai as genai
from dotenv import load_dotenv

app = Flask(__name__)

# Configuration - CRITICAL ORDER!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///research_platform.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'a3700bc31eeedaca8123a66487b6ad26207bb61b403e091e67eafd89e1b8b7d9'
app.config['JWT_SECRET_KEY'] = 'bbf41c11650ce083c7d28c1ede73867b3f2c99faa7b871bf2a2a620be061d265'
app.config['JWT_TOKEN_LOCATION'] = ['headers']
app.config['JWT_IDENTITY_CLAIM'] = 'sub'
app.config['UPLOAD_FOLDER'] = 'uploads'

# CORS - Allow frontend to connect
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# Stripe Configuration (Optional)
stripe.api_key = os.getenv('STRIPE_API_ID') 
STRIPE_PRICE_ID = 'prod_TcRioCI9h4WXUa'

# Google Gemini API Configuration (FREE!)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')  # Get from https://makersuite.google.com/app/apikey
genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# DATABASE MODELS
# ==========================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_premium = db.Column(db.Boolean, default=False)
    premium_until = db.Column(db.DateTime, nullable=True)
    stripe_customer_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    papers = db.relationship('Paper', backref='user', lazy=True, cascade='all, delete-orphan')

class Paper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    summary = db.Column(db.Text, nullable=True)
    research_gaps = db.Column(db.Text, nullable=True)
    future_work = db.Column(db.Text, nullable=True)
    key_findings = db.Column(db.Text, nullable=True)
    methodology = db.Column(db.Text, nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def extract_text_from_pdf(file):
    """Extract text from PDF"""
    try:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception as e:
        print(f"PDF Error: {str(e)}")
        return ""

def analyze_with_gemini_rest(text, analysis_type="summary"):
    """Use Gemini SDK (Cleaner and faster than manual requests)"""
    text = text[:6000]  # Limit text size
    
    prompts = {
        "summary": f"Analyze this research paper and provide a comprehensive summary in 200 words:\n\n{text}",
        "key_findings": f"Extract and list 4-5 main findings from this research paper:\n\n{text}",
        "methodology": f"Describe the research methodology used in this paper:\n\n{text}",
        "research_gaps": f"Identify 3-5 research gaps and limitations in this paper:\n\n{text}",
        "future_work": f"Suggest 4-5 specific areas for future research based on this paper:\n\n{text}"
    }
    
    try:
        # Initialize the model
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Generate content
        response = model.generate_content(prompts.get(analysis_type, prompts["summary"]))
        
        # Return text
        return response.text
        
    except Exception as e:
        print(f"Gemini SDK Error: {str(e)}")
        return f"Error: {str(e)}"

def analyze_paper_with_ai(text):
    """Complete paper analysis"""
    if not text or len(text) < 100:
        return {
            'summary': 'Error: Could not extract text from PDF',
            'key_findings': 'Error: Could not extract text from PDF',
            'methodology': 'Error: Could not extract text from PDF',
            'research_gaps': 'Error: Could not extract text from PDF',
            'future_work': 'Error: Could not extract text from PDF'
        }
    
    print("🤖 Starting AI analysis with Gemini...")
    
    return {
        'summary': analyze_with_gemini_rest(text, "summary"),
        'key_findings': analyze_with_gemini_rest(text, "key_findings"),
        'methodology': analyze_with_gemini_rest(text, "methodology"),
        'research_gaps': analyze_with_gemini_rest(text, "research_gaps"),
        'future_work': analyze_with_gemini_rest(text, "future_work")
    }

# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.route('/api/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        print(f"📝 Signup attempt: {data.get('email')}")
        
        if User.query.filter_by(email=data['email']).first():
            print(f"❌ Email exists: {data['email']}")
            return jsonify({'error': 'Email already exists'}), 400
        
        hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        
        new_user = User(
            email=data['email'],
            password=hashed_password,
            name=data['name']
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        access_token = create_access_token(identity=str(new_user.id))
        print(f"✅ User created: {new_user.email}, ID: {new_user.id}")
        print(f"✅ Token created: {access_token[:30]}...")
        
        return jsonify({
            'message': 'User created successfully',
            'access_token': access_token,
            'user': {
                'id': new_user.id,
                'email': new_user.email,
                'name': new_user.name,
                'is_premium': new_user.is_premium
            }
        }), 201
        
    except Exception as e:
        print(f"❌ Signup error: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        print(f"🔐 Login attempt: {data.get('email')}")
        
        user = User.query.filter_by(email=data['email']).first()
        
        if user and bcrypt.check_password_hash(user.password, data['password']):
            access_token = create_access_token(identity=str(user.id))
            print(f"✅ Login successful: {user.email}")
            print(f"✅ Token created: {access_token[:30]}...")
            
            return jsonify({
                'access_token': access_token,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'name': user.name,
                    'is_premium': user.is_premium
                }
            })
        
        print(f"❌ Invalid credentials for: {data.get('email')}")
        return jsonify({'error': 'Invalid credentials'}), 401
        
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/user', methods=['GET'])
@jwt_required()
def get_user():
    try:
        user_id = int(get_jwt_identity())
        print(f"👤 Getting user: {user_id}")
        
        user = User.query.get(user_id)
        
        if not user:
            print(f"❌ User not found: {user_id}")
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'is_premium': user.is_premium,
            'premium_until': user.premium_until.isoformat() if user.premium_until else None
        })
        
    except Exception as e:
        print(f"❌ Get user error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ==========================================
# PAPER ROUTES
# ==========================================

@app.route('/api/papers', methods=['GET'])
@jwt_required()
def get_papers():
    try:
        user_id = int(get_jwt_identity())
        print(f"📄 Getting papers for user: {user_id}")
        
        papers = Paper.query.filter_by(user_id=user_id).order_by(Paper.uploaded_at.desc()).all()
        
        print(f"✅ Found {len(papers)} papers")
        
        return jsonify([{
            'id': p.id,
            'title': p.title,
            'filename': p.filename,
            'uploaded_at': p.uploaded_at.isoformat(),
            'summary': p.summary[:200] + '...' if p.summary and len(p.summary) > 200 else p.summary
        } for p in papers])
        
    except Exception as e:
        print(f"❌ Get papers error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload-paper', methods=['POST'])
@jwt_required()
def upload_paper():
    try:
        user_id = int(get_jwt_identity())
        print(f"📤 Upload attempt by user: {user_id}")
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check limits
        user_papers = Paper.query.filter_by(user_id=user_id).count()
        if not user.is_premium and user_papers >= 3:
            return jsonify({'error': 'Free users can only upload 3 papers. Upgrade to premium!'}), 403
        
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are allowed'}), 400
        
        # Save file
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        timestamp = datetime.utcnow().timestamp()
        safe_filename = f"{user_id}_{int(timestamp)}_{file.filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        file.save(filepath)
        
        print(f"✓ File saved: {filepath}")
        
        # Extract text
        with open(filepath, 'rb') as f:
            text = extract_text_from_pdf(f)
        
        print(f"✓ Extracted {len(text)} characters")
        
        if not text or len(text) < 100:
            return jsonify({'error': 'Could not extract text from PDF'}), 400
        
        # Analyze
        analysis = analyze_paper_with_ai(text)
        
        # Save
        paper = Paper(
            user_id=user_id,
            title=file.filename.replace('.pdf', ''),
            filename=file.filename,
            filepath=filepath,
            summary=analysis['summary'],
            key_findings=analysis['key_findings'],
            methodology=analysis['methodology'],
            research_gaps=analysis['research_gaps'],
            future_work=analysis['future_work']
        )
        
        db.session.add(paper)
        db.session.commit()
        
        print(f"✅ Paper saved with ID: {paper.id}")
        
        return jsonify({
            'message': 'Paper uploaded and analyzed successfully',
            'paper_id': paper.id,
            'analysis': {
                'summary': paper.summary,
                'key_findings': paper.key_findings,
                'methodology': paper.methodology,
                'research_gaps': paper.research_gaps,
                'future_work': paper.future_work
            }
        }), 201
        
    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/papers/<int:paper_id>', methods=['GET'])
@jwt_required()
def get_paper(paper_id):
    try:
        user_id = int(get_jwt_identity())
        paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
        
        if not paper:
            return jsonify({'error': 'Paper not found'}), 404
        
        return jsonify({
            'id': paper.id,
            'title': paper.title,
            'filename': paper.filename,
            'uploaded_at': paper.uploaded_at.isoformat(),
            'summary': paper.summary,
            'key_findings': paper.key_findings,
            'methodology': paper.methodology,
            'research_gaps': paper.research_gaps,
            'future_work': paper.future_work
        })
    except Exception as e:
        print(f"❌ Get paper error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/papers/<int:paper_id>', methods=['DELETE'])
@jwt_required()
def delete_paper(paper_id):
    try:
        user_id = int(get_jwt_identity())
        paper = Paper.query.filter_by(id=paper_id, user_id=user_id).first()
        
        if not paper:
            return jsonify({'error': 'Paper not found'}), 404
        
        if os.path.exists(paper.filepath):
            os.remove(paper.filepath)
        
        db.session.delete(paper)
        db.session.commit()
        
        return jsonify({'message': 'Paper deleted successfully'})
    except Exception as e:
        print(f"❌ Delete error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ==========================================
# STRIPE ROUTES (Optional)
# ==========================================

@app.route('/api/create-checkout-session', methods=['POST'])
@jwt_required()
def create_checkout_session():
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        
        checkout_session = stripe.checkout.Session.create(
            customer_email=user.email,
            payment_method_types=['card'],
            line_items=[{'price': STRIPE_PRICE_ID, 'quantity': 1}],
            mode='subscription',
            success_url='http://localhost:3000/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url='http://localhost:3000/pricing',
            metadata={'user_id': user_id}
        )
        return jsonify({'checkout_url': checkout_session.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ==========================================
# INITIALIZE & RUN
# ==========================================

with app.app_context():
    db.create_all()
    print("✅ Database initialized!")

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Research Platform Backend")
    print("=" * 60)
    print(f"📁 Database: research_platform.db")
    print(f"📤 Upload: {app.config['UPLOAD_FOLDER']}")
    print(f"🤖 AI: Google Gemini")
    print(f"🔑 Gemini Key: {'✅ SET' if GEMINI_API_KEY != 'YOUR_GEMINI_API_KEY' else '❌ NOT SET'}")
    print("=" * 60)
    app.run(debug=True, port=5000, host='127.0.0.1')