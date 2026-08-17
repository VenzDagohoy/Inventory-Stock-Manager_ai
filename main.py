import os
import mysql.connector
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load your environment variables (.env)
load_dotenv()

app = FastAPI()

# Enable CORS so your vanilla JS frontend can talk to this service
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the Gemini Client
# It automatically picks up GOOGLE_API_KEY from your .env file
client = genai.Client()

# ---------------------------------------------------------
# Tool 1: Conversational Data Querying (Text-to-SQL)
# ---------------------------------------------------------
def execute_sql_query(query: str) -> str:
    """Executes a SELECT query on the inventory_db to retrieve sales history or product data.
    Tables available: 
    - products (id, user_id, name, price, stock, sold)
    - daily_history (id, user_id, record_date, total_sold, total_earnings, items_sold_details, created_at)
    """
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", 4000)), 
            user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"), database=os.getenv("DB_NAME")
        )
        cursor = conn.cursor(dictionary=True)
        
        # Security Guardrail: Force READ-ONLY for the query tool
        if not query.strip().upper().startswith("SELECT"):
            return "Error: Only SELECT queries are allowed for data retrieval."
            
        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()
        return str(results)
    except Exception as e:
        return f"Database error: {str(e)}"

# ---------------------------------------------------------
# Tool 2: Action-Oriented Commands
# ---------------------------------------------------------
def sell_product(product_id: int, quantity: int) -> str:
    """Sells a specified quantity of a product by its ID and updates the database."""
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", 4000)), 
            user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"), database=os.getenv("DB_NAME")
        )
        cursor = conn.cursor()
        
        # Verify stock exists
        cursor.execute("SELECT name, stock FROM products WHERE id = %s", (product_id,))
        product = cursor.fetchone()
        
        if not product:
            return f"Error: Product ID {product_id} not found."
        if product[1] < quantity:
            return f"Error: Cannot sell {quantity}. Only {product[1]} left in stock."
            
        # Execute the sale
        cursor.execute(
            "UPDATE products SET stock = stock - %s, sold = sold + %s WHERE id = %s", 
            (quantity, quantity, product_id)
        )
        conn.commit()
        conn.close()
        return f"Success! Recorded the sale of {quantity}x {product[0]}."
    except Exception as e:
        return f"Database error: {str(e)}"

# ---------------------------------------------------------
# Chat Session Setup
# ---------------------------------------------------------
# Create an automatic chat session with the defined tools
chat = client.chats.create(
    model="gemini-3.6-flash",
    config=types.GenerateContentConfig(
        tools=[execute_sql_query, sell_product],
        system_instruction=(
            "You are a helpful store manager assistant. "
            "When asked about data, use the execute_sql_query tool to find the exact numbers. "
            "When asked to sell an item, use the sell_product tool. "
            "Always summarize the final outcome in a friendly, concise, and conversational tone."
        )
    )
)

# Define the request format for FastAPI
class ChatRequest(BaseModel):
    message: str

# Create the endpoint
@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    # Send the user's text to the Gemini AI
    response = chat.send_message(request.message)
    # Return Gemini's natural language reply
    return {"reply": response.text}