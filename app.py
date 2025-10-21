from flask import Flask, request, jsonify
from datetime import datetime
import os

app = Flask(__name__)

# قراءة بيانات Supabase من متغيرات البيئة
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

# تهيئة عميل Supabase مؤجلة
_supabase_client = None

def get_supabase_client():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client

@app.route('/courses_suggestions', methods=['GET'])
def list_suggestions():
    supabase = get_supabase_client()
    status_filter = request.args.get('status', None)  # يمكن أن يكون pending, approved, rejected
    query = supabase.table('courses_suggestions').select('*')
    if status_filter:
        query = query.eq('status', status_filter)
    result = query.order('created_at', desc=True).execute()
    return jsonify(result.data)

@app.route('/courses_suggestions', methods=['POST'])
def create_suggestion():
    supabase = get_supabase_client()
    data = request.get_json()
    name = data.get('name')
    proposer_username = data.get('proposer_username', 'anonymous')

    existing = supabase.table('courses_suggestions').select('id').eq('name', name).eq('status', 'pending').execute()
    if existing.data:
        return jsonify({'error': 'Suggestion already pending'}), 400

    insert_data = {
        'name': name,
        'proposer_username': proposer_username,
        'status': 'pending',
        'votes': 0,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }

    new_suggestion = supabase.table('courses_suggestions').insert(insert_data).execute()
    return jsonify(new_suggestion.data[0])

@app.route('/courses_suggestions/<int:suggestion_id>/approve', methods=['POST'])
def approve_suggestion(suggestion_id):
    supabase = get_supabase_client()
    # جلب السجل
    suggestion = supabase.table('courses_suggestions').select('*').eq('id', suggestion_id).execute()
    if not suggestion.data:
        return jsonify({'error': 'Suggestion not found'}), 404
    
    if suggestion.data[0]['status'] != 'pending':
        return jsonify({'error': 'Already processed'}), 400

    # تحديث الحالة إلى approved
    supabase.table('courses_suggestions').update({
        'status': 'approved',
        'updated_at': datetime.utcnow().isoformat()
    }).eq('id', suggestion_id).execute()

    return jsonify({'id': suggestion_id, 'status': 'approved'})

@app.route('/courses_suggestions/<int:suggestion_id>/reject', methods=['POST'])
def reject_suggestion(suggestion_id):
    supabase = get_supabase_client()
    suggestion = supabase.table('courses_suggestions').select('*').eq('id', suggestion_id).execute()
    if not suggestion.data:
        return jsonify({'error': 'Suggestion not found'}), 404

    if suggestion.data[0]['status'] != 'pending':
        return jsonify({'error': 'Already processed'}), 400

    supabase.table('courses_suggestions').update({
        'status': 'rejected',
        'updated_at': datetime.utcnow().isoformat()
    }).eq('id', suggestion_id).execute()

    return jsonify({'id': suggestion_id, 'status': 'rejected'})

@app.route('/courses_suggestions/<int:suggestion_id>/vote', methods=['POST'])
def vote_suggestion(suggestion_id):
    supabase = get_supabase_client()
    data = request.get_json()
    voter_username = data.get('voter_username', 'anonymous')

    # تحقق إذا صوت المستخدم مسبقًا
    existing_vote = supabase.table('votes').select('id').eq('suggestion_id', suggestion_id).eq('voter_username', voter_username).execute()
    if existing_vote.data:
        return jsonify({'error': 'Already voted'}), 400

    # تسجيل التصويت
    supabase.table('votes').insert({
        'suggestion_id': suggestion_id,
        'voter_username': voter_username,
        'created_at': datetime.utcnow().isoformat()
    }).execute()

    # زيادة عدد الأصوات في الجدول الرئيسي
    suggestion = supabase.table('courses_suggestions').select('votes').eq('id', suggestion_id).execute()
    if not suggestion.data:
        return jsonify({'error': 'Suggestion not found'}), 404

    new_votes = suggestion.data[0]['votes'] + 1
    supabase.table('courses_suggestions').update({'votes': new_votes, 'updated_at': datetime.utcnow().isoformat()}).eq('id', suggestion_id).execute()

    return jsonify({'id': suggestion_id, 'votes': new_votes})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
