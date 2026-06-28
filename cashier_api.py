import os
from flask import Flask, request, jsonify
import psycopg2

app = Flask(__name__)

def get_db_connection():
    # Automatically pulls the live database URL from your production server variables
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        # Fallback to local string just in case
        return psycopg2.connect("dbname=wahlah_production user=postgres password=secret host=localhost")
    return psycopg2.connect(db_url)

@app.route("/api/v1/payments/withdraw", methods=["POST"])
def request_withdrawal():
    data = request.json
    user_id = data.get("user_id")
    amount = float(data.get("redeem_amount"))
    payout_method = data.get("payout_method")
    wallet_addr = data.get("wallet_address")
    tip = float(data.get("tip_amount", 0.00))
    total_deduction = amount + tip

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # High-security row lock prevents any double-spending or asset leakage
        cursor.execute("SELECT sweeps_coins_balance FROM user_wallets WHERE user_id = %s FOR UPDATE;", (user_id,))
        balance = cursor.fetchone()
        if not balance or float(balance[0]) < total_deduction:
            return jsonify({"status": "error", "message": "Insufficient balance"}), 400

        # Deduct the balance and move the transaction into the pending queue
        cursor.execute("UPDATE user_wallets SET sweeps_coins_balance = sweeps_coins_balance - %s WHERE user_id = %s;", (total_deduction, user_id))
        cursor.execute("""
            INSERT INTO withdrawal_requests (user_id, amount, payout_method, wallet_address, tip_amount, status) 
            VALUES (%s, %s, %s, %s, %s, 'pending');
        """, (user_id, amount, payout_method, wallet_addr, tip))
        conn.commit()
        return jsonify({"status": "success", "message": "Logged for Cashier review."}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    # Standard production port
    app.run(port=5000, debug=False)
