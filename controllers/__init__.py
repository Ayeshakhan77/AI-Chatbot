from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from flask_login import login_required, current_user, login_user, logout_user
from models import db, User, KnowledgeBase, ChatSession, ChatMessage, Feedback
from services import ChatService, AgentService, AdminService
import uuid

# Blueprints
customer_bp = Blueprint('customer', __name__)
agent_bp = Blueprint('agent', __name__)
admin_bp = Blueprint('admin', __name__)

chat_service = ChatService()
agent_service = AgentService()
admin_service = AdminService()

# Customer Routes
@customer_bp.route('/dashboard')
@login_required
def customer_dashboard():
    if current_user.role != 'customer':
        return redirect(url_for('unauthorized'))
    
    # Get or create active session
    active_session = ChatSession.query.filter_by(
        user_id=current_user.id, 
        status='active'
    ).first()
    
    if not active_session:
        active_session = chat_service.start_chat_session(current_user.id)
    
    return render_template('customer/dashboard.html', 
                         session_id=active_session.session_id)

@customer_bp.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    data = request.get_json()
    session_id = data.get('session_id')
    message = data.get('message')
    
    if not session_id or not message:
        return jsonify({'error': 'Missing parameters'}), 400
    
    response = chat_service.send_message(session_id, current_user.id, message)
    
    if response:
        return jsonify(response)
    else:
        return jsonify({'error': 'Session not found'}), 404

@customer_bp.route('/api/chat_history')
@login_required
def get_chat_history():
    session_id = request.args.get('session_id')
    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400
    
    history = chat_service.get_chat_history(session_id, current_user.id)
    return jsonify(history)

@customer_bp.route('/api/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    data = request.get_json()
    session_id = data.get('session_id')
    rating = data.get('rating')
    comment = data.get('comment', '')
    
    chat_session = ChatSession.query.filter_by(
        session_id=session_id, 
        user_id=current_user.id
    ).first()
    
    if not chat_session:
        return jsonify({'error': 'Session not found'}), 404
    
    feedback = Feedback(
        session_id=chat_session.id,
        user_id=current_user.id,
        rating=rating,
        comment=comment
    )
    
    db.session.add(feedback)
    db.session.commit()
    
    return jsonify({'success': True})

# Agent Routes
@agent_bp.route('/dashboard')
@login_required
def agent_dashboard():
    if current_user.role != 'agent':
        return redirect(url_for('unauthorized'))
    
    escalated_sessions = agent_service.get_escalated_sessions()
    return render_template('agent/dashboard.html', 
                         sessions=escalated_sessions)

@agent_bp.route('/api/escalated_sessions')
@login_required
def get_escalated_sessions():
    if current_user.role != 'agent':
        return jsonify({'error': 'Unauthorized'}), 403
    
    sessions = agent_service.get_escalated_sessions()
    session_data = []
    
    for sess in sessions:
        session_data.append({
            'id': sess.id,
            'session_id': sess.session_id,
            'user_id': sess.user_id,
            'username': sess.user.username,
            'created_at': sess.created_at.isoformat(),
            'escalated_at': sess.escalated_at.isoformat() if sess.escalated_at else None,
            'message_count': len(sess.messages)
        })
    
    return jsonify(session_data)

@agent_bp.route('/api/session/<int:session_id>/messages')
@login_required
def get_session_messages(session_id):
    if current_user.role != 'agent':
        return jsonify({'error': 'Unauthorized'}), 403
    
    messages = agent_service.get_session_messages(session_id)
    message_data = []
    
    for msg in messages:
        message_data.append({
            'type': msg.message_type,
            'content': msg.content,
            'timestamp': msg.timestamp.isoformat(),
            'is_escalation': msg.is_escalation_trigger
        })
    
    return jsonify(message_data)

@agent_bp.route('/api/send_agent_message', methods=['POST'])
@login_required
def send_agent_message():
    if current_user.role != 'agent':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    session_id = data.get('session_id')
    message = data.get('message')
    
    if not session_id or not message:
        return jsonify({'error': 'Missing parameters'}), 400
    
    success = agent_service.send_agent_message(session_id, message, current_user.id)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to send message'}), 400

@agent_bp.route('/api/close_session', methods=['POST'])
@login_required
def close_session():
    if current_user.role != 'agent':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400
    
    success = agent_service.close_session(session_id)
    
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to close session'}), 400

# Admin Routes
@admin_bp.route('/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('unauthorized'))
    
    analytics = admin_service.get_system_analytics()
    knowledge_items = KnowledgeBase.query.all()
    users = User.query.all()
    
    return render_template('admin/dashboard.html',
                         analytics=analytics,
                         knowledge_items=knowledge_items,
                         users=users)

@admin_bp.route('/api/analytics')
@login_required
def get_analytics():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    analytics = admin_service.get_system_analytics()
    return jsonify(analytics)

@admin_bp.route('/api/knowledge_base', methods=['GET', 'POST', 'PUT', 'DELETE'])
@login_required
def manage_knowledge_base():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'GET':
        items = KnowledgeBase.query.all()
        return jsonify([{
            'id': item.id,
            'question': item.question,
            'answer': item.answer,
            'category': item.category,
            'tags': item.tags,
            'is_active': item.is_active
        } for item in items])
    
    elif request.method == 'POST':
        data = request.get_json()
        new_item = KnowledgeBase(
            question=data['question'],
            answer=data['answer'],
            category=data.get('category', 'general'),
            tags=data.get('tags', '')
        )
        db.session.add(new_item)
        db.session.commit()
        
        # Retrain chatbot model
        from services import ChatbotEngine
        chatbot = ChatbotEngine()
        chatbot.retrain_model()
        
        return jsonify({'success': True, 'id': new_item.id})
    
    elif request.method == 'PUT':
        data = request.get_json()
        item = KnowledgeBase.query.get(data['id'])
        if item:
            item.question = data['question']
            item.answer = data['answer']
            item.category = data.get('category', item.category)
            item.tags = data.get('tags', item.tags)
            item.is_active = data.get('is_active', item.is_active)
            db.session.commit()
            
            # Retrain chatbot model
            from services import ChatbotEngine
            chatbot = ChatbotEngine()
            chatbot.retrain_model()
            
            return jsonify({'success': True})
        return jsonify({'error': 'Item not found'}), 404
    
    elif request.method == 'DELETE':
        item_id = request.args.get('id')
        item = KnowledgeBase.query.get(item_id)
        if item:
            db.session.delete(item)
            db.session.commit()
            
            # Retrain chatbot model
            from services import ChatbotEngine
            chatbot = ChatbotEngine()
            chatbot.retrain_model()
            
            return jsonify({'success': True})
        return jsonify({'error': 'Item not found'}), 404

@admin_bp.route('/api/users', methods=['GET', 'POST', 'PUT', 'DELETE'])
@login_required
def manage_users():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'GET':
        users = User.query.all()
        return jsonify([{
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'is_active': user.is_active,
            'created_at': user.created_at.isoformat()
        } for user in users])
    
    elif request.method == 'POST':
        data = request.get_json()
        # In a real application, you would hash the password
        new_user = User(
            username=data['username'],
            email=data['email'],
            password_hash='temp_password',  # Should be properly hashed
            role=data['role']
        )
        db.session.add(new_user)
        db.session.commit()
        return jsonify({'success': True, 'id': new_user.id})
    
    elif request.method == 'PUT':
        data = request.get_json()
        user = User.query.get(data['id'])
        if user:
            user.username = data.get('username', user.username)
            user.email = data.get('email', user.email)
            user.role = data.get('role', user.role)
            user.is_active = data.get('is_active', user.is_active)
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'error': 'User not found'}), 404
    
    elif request.method == 'DELETE':
        user_id = request.args.get('id')
        user = User.query.get(user_id)
        if user and user.id != current_user.id:  # Prevent self-deletion
            db.session.delete(user)
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'error': 'User not found or cannot delete yourself'}), 404