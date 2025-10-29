from flask import Flask, render_template, redirect, url_for, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
from config import config
import os

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    
    # Login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register blueprints
    from controllers import customer_bp, agent_bp, admin_bp
    app.register_blueprint(customer_bp, url_prefix='/customer')
    app.register_blueprint(agent_bp, url_prefix='/agent')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    # Main routes
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.role == 'customer':
                return redirect(url_for('customer.customer_dashboard'))
            elif current_user.role == 'agent':
                return redirect(url_for('agent.agent_dashboard'))
            elif current_user.role == 'admin':
                return redirect(url_for('admin.admin_dashboard'))
        return redirect(url_for('login'))
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            user = User.query.filter_by(username=username).first()
            
            if user and check_password_hash(user.password_hash, password) and user.is_active:
                login_user(user)
                return redirect(url_for('index'))
            else:
                return render_template('login.html', error='Invalid credentials')
        
        return render_template('login.html')
    
    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))
    
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('role', 'customer')
            
            # Check if user exists
            if User.query.filter_by(username=username).first():
                return render_template('register.html', error='Username already exists')
            
            if User.query.filter_by(email=email).first():
                return render_template('register.html', error='Email already exists')
            
            # Create new user (only customers can self-register)
            if role not in ['customer']:
                role = 'customer'
            
            new_user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                role=role
            )
            
            db.session.add(new_user)
            db.session.commit()
            
            return redirect(url_for('login'))
        
        return render_template('register.html')
    
    @app.route('/unauthorized')
    def unauthorized():
        return render_template('unauthorized.html'), 403
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('500.html'), 500
    
    # Create tables and sample data
    with app.app_context():
        db.create_all()
        create_sample_data()
    
    return app

def create_sample_data():
    """Create sample data for testing"""
    # Check if admin user exists
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        admin_user = User(
            username='admin',
            email='admin@chatbot.com',
            password_hash=generate_password_hash('admin123'),
            role='admin'
        )
        db.session.add(admin_user)
    
    # Check if agent user exists
    agent = User.query.filter_by(role='agent').first()
    if not agent:
        agent_user = User(
            username='agent1',
            email='agent@chatbot.com',
            password_hash=generate_password_hash('agent123'),
            role='agent'
        )
        db.session.add(agent_user)
    
    # Check if knowledge base has entries
    kb_count = db.session.query(KnowledgeBase).count()
    if kb_count == 0:
        sample_data = [
            {
                'question': 'What are your business hours?',
                'answer': 'Our business hours are Monday to Friday, 9 AM to 6 PM EST.',
                'category': 'general',
                'tags': 'hours, timing, business hours'
            },
            {
                'question': 'How can I reset my password?',
                'answer': 'You can reset your password by clicking on "Forgot Password" on the login page.',
                'category': 'account',
                'tags': 'password, reset, account'
            },
            {
                'question': 'Where is your office located?',
                'answer': 'Our main office is located at 123 Business Street, Suite 100, City, State 12345.',
                'category': 'contact',
                'tags': 'location, office, address'
            },
            {
                'question': 'Do you offer refunds?',
                'answer': 'Yes, we offer refunds within 30 days of purchase. Please contact support for assistance.',
                'category': 'billing',
                'tags': 'refund, money back, return'
            },
            {
                'question': 'How can I contact support?',
                'answer': 'You can contact support via email at support@company.com or call us at 1-800-123-4567.',
                'category': 'contact',
                'tags': 'support, contact, help'
            }
        ]
        
        for data in sample_data:
            kb_item = KnowledgeBase(**data)
            db.session.add(kb_item)
    
    db.session.commit()

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)