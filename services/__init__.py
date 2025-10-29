import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize
import pickle
import os
from models import db, KnowledgeBase, ChatSession, ChatMessage
import threading
from flask import current_app

class ChatbotEngine:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ChatbotEngine, cls).__new__(cls)
                # Don't initialize here - wait for first use
            return cls._instance
    
    def _initialize(self):
        """Initialize only when needed and within app context"""
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        self.knowledge_vectors = None
        self.questions = []
        self.answers = []
        self._load_knowledge_base()
    
    def _load_knowledge_base(self):
        """Load knowledge base from database and train TF-IDF model"""
        # Use current_app context
        with current_app.app_context():
            knowledge_items = KnowledgeBase.query.filter_by(is_active=True).all()
            
            if not knowledge_items:
                self.questions = ["hello", "hi", "greetings"]
                self.answers = ["Hello! How can I help you today?", "Hi there! What can I assist you with?", "Greetings! How may I be of service?"]
            else:
                self.questions = [item.question for item in knowledge_items]
                self.answers = [item.answer for item in knowledge_items]
            
            if self.questions:
                self.knowledge_vectors = self.vectorizer.fit_transform(self.questions)
    
    def get_response(self, user_input, threshold=0.3):
        """Get chatbot response using TF-IDF and cosine similarity"""
        # Lazy initialization
        if self.knowledge_vectors is None:
            self._initialize()
            
        if not self.questions or self.knowledge_vectors is None:
            return "I'm still learning. Please contact a human agent for assistance.", 0.0, True
        
        # Transform user input
        input_vector = self.vectorizer.transform([user_input])
        
        # Calculate cosine similarities
        similarities = cosine_similarity(input_vector, self.knowledge_vectors)
        max_similarity = np.max(similarities)
        best_match_idx = np.argmax(similarities)
        
        if max_similarity >= threshold:
            return self.answers[best_match_idx], max_similarity, False
        else:
            return "I'm not sure I understand. Let me connect you with a human agent who can help.", max_similarity, True
    
    def retrain_model(self):
        """Retrain the model with updated knowledge base"""
        self._initialize()

class ChatService:
    def __init__(self):
        # Don't initialize chatbot here - do it lazily
        self.chatbot = None
    
    def _get_chatbot(self):
        """Get chatbot instance (lazy initialization)"""
        if self.chatbot is None:
            self.chatbot = ChatbotEngine()
        return self.chatbot
    
    def start_chat_session(self, user_id):
        """Start a new chat session"""
        import uuid
        session_id = str(uuid.uuid4())
        
        session = ChatSession(
            user_id=user_id,
            session_id=session_id,
            status='active'
        )
        db.session.add(session)
        db.session.commit()
        
        # Add welcome message
        welcome_msg = ChatMessage(
            session_id=session.id,
            message_type='bot',
            content="Hi! How may I help you?"
        )
        db.session.add(welcome_msg)
        db.session.commit()
        
        return session
    
    def send_message(self, session_id, user_id, message):
        """Process user message and return response"""
        session = ChatSession.query.filter_by(session_id=session_id, user_id=user_id).first()
        if not session:
            return None
        
        # Save user message
        user_msg = ChatMessage(
            session_id=session.id,
            message_type='user',
            content=message
        )
        db.session.add(user_msg)
        
        # Get chatbot response
        chatbot = self._get_chatbot()
        bot_response, similarity, needs_escalation = chatbot.get_response(message)
        
        # Save bot response
        bot_msg = ChatMessage(
            session_id=session.id,
            message_type='bot',
            content=bot_response,
            is_escalation_trigger=needs_escalation
        )
        db.session.add(bot_msg)
        
        # Escalate if needed
        if needs_escalation and session.status == 'active':
            session.status = 'escalated'
            session.escalated_at = db.func.now()
        
        db.session.commit()
        
        return {
            'user_message': message,
            'bot_response': bot_response,
            'similarity': float(similarity),
            'needs_escalation': needs_escalation,
            'session_status': session.status
        }
    
    def get_chat_history(self, session_id, user_id):
        """Get chat history for a session"""
        session = ChatSession.query.filter_by(session_id=session_id, user_id=user_id).first()
        if not session:
            return []
        
        messages = ChatMessage.query.filter_by(session_id=session.id).order_by(ChatMessage.timestamp).all()
        return [
            {
                'type': msg.message_type,
                'content': msg.content,
                'timestamp': msg.timestamp.isoformat(),
                'is_escalation': msg.is_escalation_trigger
            }
            for msg in messages
        ]

class AgentService:
    def get_escalated_sessions(self):
        """Get all escalated chat sessions"""
        return ChatSession.query.filter_by(status='escalated').order_by(ChatSession.escalated_at).all()
    
    def get_session_messages(self, session_id):
        """Get all messages for a session"""
        return ChatMessage.query.filter_by(session_id=session_id).order_by(ChatMessage.timestamp).all()
    
    def send_agent_message(self, session_id, message, agent_id):
        """Send message as agent"""
        session = ChatSession.query.get(session_id)
        if not session or session.status != 'escalated':
            return False
        
        agent_msg = ChatMessage(
            session_id=session_id,
            message_type='agent',
            content=message
        )
        db.session.add(agent_msg)
        db.session.commit()
        return True
    
    def close_session(self, session_id):
        """Close a chat session"""
        session = ChatSession.query.get(session_id)
        if session:
            session.status = 'closed'
            session.closed_at = db.func.now()
            db.session.commit()
            return True
        return False

class AdminService:
    def get_system_analytics(self):
        """Get system analytics and reports"""
        from sqlalchemy import func, desc
        
        total_chats = ChatSession.query.count()
        escalated_chats = ChatSession.query.filter_by(status='escalated').count()
        closed_chats = ChatSession.query.filter_by(status='closed').count()
        
        # Average feedback rating
        avg_rating = db.session.query(func.avg(Feedback.rating)).scalar() or 0
        
        # Chatbot success rate (non-escalated chats / total chats)
        successful_chats = ChatSession.query.filter(
            ChatSession.status == 'active',
            ChatSession.escalated_at.is_(None)
        ).count()
        
        success_rate = (successful_chats / total_chats * 100) if total_chats > 0 else 0
        
        # Recent activity
        recent_sessions = ChatSession.query.order_by(desc(ChatSession.created_at)).limit(10).all()
        
        return {
            'total_chats': total_chats,
            'escalated_chats': escalated_chats,
            'closed_chats': closed_chats,
            'active_chats': total_chats - closed_chats,
            'avg_rating': round(avg_rating, 2),
            'success_rate': round(success_rate, 2),
            'recent_sessions': recent_sessions
        }