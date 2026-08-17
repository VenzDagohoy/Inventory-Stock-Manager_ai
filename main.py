import os
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

    # ---------------------------------------------------------
    # Tool 1: Strictly Scoped Inventory Query
    # ---------------------------------------------------------
    def get_my_inventory() -> str:
        """Retrieves all products belonging strictly to the currently logged-in user from the database."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            # HARDCODED: The user_id parameter is strictly enforced here.
            cursor.execute(
                "SELECT id, name, price, stock, sold FROM products WHERE user_id = %s ORDER BY id ASC",
                (current_user_id,)
            )
            results = cursor.fetchall()
            conn.close()
            return str(results)
        except Exception as e:
            return f"Database error: {str(e)}"

    # ---------------------------------------------------------
    # Tool 2: Strictly Scoped Sales History Query
    # ---------------------------------------------------------
    def get_my_history() -> str:
        """Retrieves the daily sales history records belonging strictly to the currently logged-in user."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            # HARDCODED: The user_id parameter is strictly enforced here.
            cursor.execute(
                "SELECT record_date, total_sold, total_earnings, items_sold_details FROM daily_history WHERE user_id = %s ORDER BY record_date DESC",
                (current_user_id,)
            )
            results = cursor.fetchall()
            conn.close()
            return str(results)
        except Exception as e:
            return f"Database error: {str(e)}"

    # ---------------------------------------------------------
    # Tool 3: Strictly Scoped Action Command (Sell Product)
    # ---------------------------------------------------------
    def sell_product(product_id: int, quantity: int) -> str:
        """Sells a specified quantity of a product by its ID and updates the database safely."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Verify ownership using both product_id and current_user_id
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
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=request.message,
            config=types.GenerateContentConfig(
                tools=[get_my_inventory, get_my_history, sell_product],
                system_instruction=(
                    f"You are a store manager AI assistant for user ID {current_user_id}. "
                    "When the user asks about their inventory, products, stock, or items, you MUST call the `get_my_inventory` tool. "
                    "When the user asks about past sales or history, call the `get_my_history` tool. "
                    "When the user asks to sell an item, call the `sell_product` tool. "
                    "Never attempt to write or guess SQL queries. Only use the provided tools. "
                    "Use Philippine Peso (Php) as the currency. "
                    "Always summarize the final outcome in a friendly, concise, and conversational tone."
                )
            )
        )
        return {"reply": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))