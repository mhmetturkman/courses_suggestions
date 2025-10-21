from flask import Flask, request, jsonify
from datetime import datetime
import os
# استيراد الوحدة لطباعة الأخطاء
import logging

# إعداد logging لطباعة الأخطاء
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# قراءة بيانات Supabase من متغيرات البيئة
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

# تهيئة عميل Supabase مؤجلة
_supabase_client = None

def get_supabase_client():
    global _supabase_client
    if _supabase_client is None:
        try:
            from supabase import create_client
            _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            logging.info("Supabase client initialized successfully.")
        except Exception as e:
            # طباعة خطأ فشل تهيئة عميل Supabase
            logging.error(f"Error initializing Supabase client: {e}")
            raise
    return _supabase_client

@app.route('/courses_suggestions', methods=['GET'])
def list_suggestions():
    try:
        supabase = get_supabase_client()
        status_filter = request.args.get('status', None)  # يمكن أن يكون pending, approved, rejected
        logging.info(f"Received GET request for suggestions. Status filter: {status_filter}")

        query = supabase.table('courses_suggestions').select('*')
        if status_filter:
            query = query.eq('status', status_filter)
        
        result = query.order('created_at', desc=True).execute()
        logging.info(f"Successfully fetched {len(result.data)} suggestions from DB.")
        return jsonify(result.data)
    except Exception as e:
        # طباعة خطأ في دالة جلب الاقتراحات
        logging.error(f"Error in list_suggestions: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/courses_suggestions', methods=['POST'])
def create_suggestion():
    try:
        supabase = get_supabase_client()
        data = request.get_json()
        
        if not data:
            logging.warning("POST request failed: No JSON data received.")
            return jsonify({'error': 'Missing JSON data'}), 400
        
        name = data.get('name')
        proposer_username = data.get('proposer_username', 'anonymous')
        description = data.get('description')

        if not name or not description:
            logging.warning(f"POST request failed: Missing required fields (name: {name}, description: {description}).")
            return jsonify({'error': 'Missing required fields (name or description)'}), 400

        logging.info(f"Received POST request to create suggestion: {name} by {proposer_username}")

        response = supabase.table('courses_suggestions').insert({
            'name': name,
            'description': description,
            'proposer_username': proposer_username,
            'status': 'pending',
            'votes': 0,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }).execute()
        
        if response.data:
            logging.info(f"Suggestion created successfully with ID: {response.data[0].get('id')}")
            # قد يعيد Supabase البيانات التي تم إدخالها مع الـ ID
            return jsonify(response.data[0]), 201
        else:
            # حالة فشل إدخال غير متوقعة
            logging.error(f"Supabase insert failed, no data returned. Response: {response.json()}")
            return jsonify({'error': 'Failed to insert suggestion'}), 500

    except Exception as e:
        # طباعة خطأ عام في دالة إنشاء الاقتراح
        logging.error(f"Error in create_suggestion: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500


# مسار للموافقة على اقتراح
@app.route('/courses_suggestions/<int:suggestion_id>/approve', methods=['POST'])
def approve_suggestion(suggestion_id):
    try:
        supabase = get_supabase_client()
        logging.info(f"Received APPROVE request for suggestion ID: {suggestion_id}")

        # تحديث الحالة إلى approved
        supabase.table('courses_suggestions').update({
            'status': 'approved',
            'updated_at': datetime.utcnow().isoformat()
        }).eq('id', suggestion_id).execute()
        
        logging.info(f"Suggestion ID {suggestion_id} approved successfully.")
        return jsonify({'id': suggestion_id, 'status': 'approved'})
    except Exception as e:
        # طباعة خطأ في دالة الموافقة
        logging.error(f"Error in approve_suggestion for ID {suggestion_id}: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

# مسار لرفض اقتراح
@app.route('/courses_suggestions/<int:suggestion_id>/reject', methods=['POST'])
def reject_suggestion(suggestion_id):
    try:
        supabase = get_supabase_client()
        logging.info(f"Received REJECT request for suggestion ID: {suggestion_id}")

        # تحديث الحالة إلى rejected
        supabase.table('courses_suggestions').update({
            'status': 'rejected',
            'updated_at': datetime.utcnow().isoformat()
        }).eq('id', suggestion_id).execute()
        
        logging.info(f"Suggestion ID {suggestion_id} rejected successfully.")
        return jsonify({'id': suggestion_id, 'status': 'rejected'})
    except Exception as e:
        # طباعة خطأ في دالة الرفض
        logging.error(f"Error in reject_suggestion for ID {suggestion_id}: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500


@app.route('/courses_suggestions/<int:suggestion_id>/vote', methods=['POST'])
def vote_suggestion(suggestion_id):
    try:
        supabase = get_supabase_client()
        data = request.get_json()
        
        if not data:
            logging.warning(f"Vote request for ID {suggestion_id} failed: No JSON data received.")
            return jsonify({'error': 'Missing JSON data'}), 400

        voter_username = data.get('voter_username', 'anonymous')
        logging.info(f"Received VOTE request for suggestion ID: {suggestion_id} by {voter_username}")

        # تحقق إذا صوت المستخدم مسبقًا
        existing_vote = supabase.table('votes').select('id').eq('suggestion_id', suggestion_id).eq('voter_username', voter_username).execute()
        if existing_vote.data:
            logging.warning(f"Voter {voter_username} already voted for suggestion ID {suggestion_id}.")
            return jsonify({'error': 'Already voted'}), 400

        # تسجيل التصويت
        supabase.table('votes').insert({
            'suggestion_id': suggestion_id,
            'voter_username': voter_username,
            'created_at': datetime.utcnow().isoformat()
        }).execute()
        logging.info(f"Vote recorded for suggestion ID {suggestion_id}.")

        # زيادة عدد الأصوات في الجدول الرئيسي
        suggestion = supabase.table('courses_suggestions').select('votes').eq('id', suggestion_id).execute()
        if not suggestion.data:
            logging.warning(f"Suggestion ID {suggestion_id} not found during vote count update.")
            return jsonify({'error': 'Suggestion not found'}), 404

        new_votes = suggestion.data[0]['votes'] + 1
        supabase.table('courses_suggestions').update({'votes': new_votes, 'updated_at': datetime.utcnow().isoformat()}).eq('id', suggestion_id).execute()
        
        logging.info(f"Suggestion ID {suggestion_id} vote count updated to {new_votes}.")
        return jsonify({'votes': new_votes})
    except Exception as e:
        # طباعة خطأ عام في دالة التصويت
        logging.error(f"Error in vote_suggestion for ID {suggestion_id}: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

if __name__ == '__main__':
    # يتم تشغيل التطبيق محليًا، عادةً في Vercel يتم تجاهل هذا
    app.run(debug=True)
