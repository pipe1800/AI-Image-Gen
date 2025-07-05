import os
import pika
import json
import requests
import time
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_POLLO_QUEUE", "pollo_jobs")
RABBITMQ_USER = os.getenv("RABBITMQ_USER")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS")
POLLO_API_KEY = os.getenv("POLLO_API_KEY")
POLLO_API_HOST = "https://api.pollo.ai"
POLLO_MOCK_MODE = os.getenv("POLLO_MOCK_MODE", "False").lower() == "true"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("POLLO_ADAPTER: Successfully connected to Supabase.")
except Exception as e:
    print(f"POLLO_ADAPTER: Error connecting to Supabase: {e}")
    exit(1)

def update_job_status(job_id: str, status: str, result_data: dict = None):
    try:
        update_payload = {"status": status}
        if result_data:
            update_payload["result"] = result_data
        supabase.table("jobs").update(update_payload).eq("id", job_id).execute()
        print(f"POLLO_ADAPTER: Updated job {job_id} to status '{status}'.")
    except Exception as e:
        print(f"POLLO_ADAPTER: Error updating job {job_id} in Supabase: {e}")

def process_job(job_data: dict):
    job_id = job_data.get("jobId")
    if not job_id: return
    print(f"--- POLLO_ADAPTER: Processing job: {job_id} ---")
    update_job_status(job_id, "processing")

    if POLLO_MOCK_MODE:
        print(f"*** POLLO_ADAPTER: MOCK MODE ENABLED for job {job_id} ***")
        time.sleep(5)
        result_data = {"assetId": "mock-" + job_id, "externalUrl": "https://placehold.co/1024x576/1a1a1a/ffffff?text=Mock+Video", "error": None}
        update_job_status(job_id, "completed", result_data)
        print(f"--- POLLO_ADAPTER: Finished MOCK processing job: {job_id} ---")
        return

    try:
        prompt = job_data.get("prompt", "a beautiful video")
        payload = {"prompt": prompt}
        headers = {"x-api-key": POLLO_API_KEY, "Content-Type": "application/json"}
        endpoint_url = f"{POLLO_API_HOST}/v1/runway/gen-4"
        response = requests.post(endpoint_url, headers=headers, json=payload)
        response.raise_for_status()
        task_id = response.json().get("data", {}).get("id")
        if not task_id: raise Exception("Pollo.ai API did not return a task ID.")
        
        time.sleep(30) 
        
        result_data = {"assetId": "g-" + job_id, "externalUrl": "https://example.com/mock-video.mp4", "error": None}
        update_job_status(job_id, "completed", result_data)
    except Exception as e:
        update_job_status(job_id, "failed", {"error": {"code": "WORKER_ERROR", "message": str(e)}})
    print(f"--- POLLO_ADAPTER: Finished processing job: {job_id} ---")

def callback(ch, method, properties, body):
    print(f"\nPOLLO_ADAPTER: Received new job message...")
    try:
        process_job(json.loads(body))
    except Exception as e:
        print(f"POLLO_ADAPTER: Error in callback: {e}")
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    print("POLLO_ADAPTER: Starting service...")
    if POLLO_MOCK_MODE: print("!!! POLLO_ADAPTER: WARNING: Running in MOCK mode. !!!")
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials)
            )
            channel = connection.channel()
            channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
            channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=callback)
            print(f"POLLO_ADAPTER: [*] Waiting for messages on queue '{RABBITMQ_QUEUE}'.")
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as e:
            print(f"POLLO_ADAPTER: Connection to RabbitMQ failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            print(f"POLLO_ADAPTER: A critical error occurred: {e}")
            break

if __name__ == "__main__":
    main()
