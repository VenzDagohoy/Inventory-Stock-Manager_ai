import os
import json
import mysql.connector
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = genai.Client()

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 4000)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

class ChatRequest(BaseModel):
    message: str
    user_id: int

@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    current_user_id = request.user_id

    # Tool 1: Strictly Scoped Inventory Query
    def get_my_inventory(check_type: str = "all") -> str:
        """Retrieves all products belonging to the user. Always pass check_type='all'."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, name, price, stock, sold FROM products WHERE user_id = %s ORDER BY id ASC",
                (current_user_id,)
            )
            results = cursor.fetchall()
            conn.close()
            return json.dumps(results, default=str)
        except Exception as e:
            return json.dumps({"error": f"Database error: {str(e)}"})

    # Tool 2: Strictly Scoped Sales History Query
    def get_my_history(check_type: str = "recent") -> str:
        """Retrieves the daily sales history records. Always pass check_type='recent'."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT record_date, total_sold, total_earnings, items_sold_details FROM daily_history WHERE user_id = %s ORDER BY record_date DESC",
                (current_user_id,)
            )
            results = cursor.fetchall()
            conn.close()
            return json.dumps(results, default=str)
        except Exception as e:
            return json.dumps({"error": f"Database error: {str(e)}"})

    # Tool 3: Strictly Scoped Action Command
    def sell_product(product_id: int, quantity: int) -> str:
        """Sells a specified quantity of a product by its ID and updates the database."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT name, stock FROM products WHERE id = %s AND user_id = %s",
                (product_id, current_user_id)
            )
            product = cursor.fetchone()
            
            if not product:
                return f"Error: Product ID #{product_id} was not found in your inventory."
            if product[1] < quantity:
                return f"Error: Cannot sell {quantity}. Only {product[1]} left in stock."
                
            cursor.execute(
                "UPDATE products SET stock = stock - %s, sold = sold + %s WHERE id = %s AND user_id = %s", 
                (quantity, quantity, product_id, current_user_id)
            )
            conn.commit()
            conn.close()
            return f"Success! Recorded the sale of {quantity}x {product[0]}."
        except Exception as e:
            return f"Database error: {str(e)}"

    try:
        chat = client.chats.create(
            model="gemini-1.5-flash",  
            config=types.GenerateContentConfig(
                tools=[get_my_inventory, get_my_history, sell_product],
                system_instruction=(
                    f"You are a store manager AI assistant. The current user ID is {current_user_id}. "
                    "When asked about inventory, stock, or products, ALWAYS call the get_my_inventory tool. "
                    "When asked about sales history, ALWAYS call the get_my_history tool. "
                    "When asked to sell an item, ALWAYS call the sell_product tool. "
                    "Use Philippine Peso (Php). Format responses clearly and conversationally."
                )
            )
        )
        
        response = chat.send_message(request.message)
        
        reply_text = response.text if response.text else "The action was completed, but no text was generated."
        return {"reply": reply_text}
    except Exception as e:
        print(f"Gemini API Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))