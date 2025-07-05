import os
import pika
import json
import requests
import time
from dotenv import load_dotenv
from supabase import create_client, Client
from typing import Optional

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_FAL_QUEUE", "fal_jobs")
RABBITMQ_USER = os.getenv("RABBITMQ_USER")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS")
FAL_AI_API_KEY = os.getenv("FAL_AI_API_KEY")
FAL_AI_MODEL_URL = "https://fal.run/fal-ai/stable-diffusion-v3-medium"

last_used_seed: Optional[int] = None

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("FAL_ADAPTER: Successfully connected to Supabase.")
except Exception as e:
    print(f"FAL_ADAPTER: Error connecting to Supabase: {e}")
    exit(1)

def update_job_status(job_id: str, status: str, result_data: dict = None):
    try:
        update_payload = {"status": status}
        if result_data:
            update_payload["result"] = result_data
        supabase.table("jobs").update(update_payload).eq("id", job_id).execute()
        print(f"FAL_ADAPTER: Updated job {job_id} to status '{status}'.")
    except Exception as e:
        print(f"FAL_ADAPTER: Error updating job {job_id} in Supabase: {e}")

def process_job(job_data: dict):
    global last_used_seed
    job_id = job_data.get("jobId")
    if not job_id: return
    print(f"--- FAL_ADAPTER: Processing job: {job_id} ---")
    update_job_status(job_id, "processing")
    try:
        payload = {
            "prompt": job_data.get("prompt", "a beautiful landscape")
        }

        if job_data.get("negative_prompt"):
            payload["negative_prompt"] = job_data["negative_prompt"]
        
        payload["num_images"] = job_data.get("num_images", 1)
        payload["image_size"] = job_data.get("image_size", {"width": 1024, "height": 1024})
        payload["num_inference_steps"] = job_data.get("num_inference_steps", 28)
        payload["guidance_scale"] = job_data.get("guidance_scale", 7.5)
        payload["enable_safety_checker"] = not job_data.get("nsfw", False)
        payload["format"] = job_data.get("output_format", "jpeg")

        seed = job_data.get("seed")
        if job_data.get("reuse_seed", False) and last_used_seed is not None:
            seed = last_used_seed
        
        if seed is not None:
            payload["seed"] = seed

        headers = {"Authorization": f"Key {FAL_AI_API_KEY}", "Content-Type": "application/json"}
        
        print(f"FAL_ADAPTER: Sending request to {FAL_AI_MODEL_URL} for job {job_id} with payload: {json.dumps(payload)}")
        response = requests.post(FAL_AI_MODEL_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        response_data = response.json()
        
        if "seed" in response_data:
            last_used_seed = response_data["seed"]
            print(f"FAL_ADAPTER: Storing last used seed: {last_used_seed}")

        print(f"FAL_ADAPTER: Successfully received result from FAL.ai for job {job_id}.")
        update_job_status(job_id, "completed", response_data)

    except Exception as e:
        print(f"FAL_ADAPTER: Error processing job {job_id}: {e}")
        update_job_status(job_id, "failed", {"error": {"code": "WORKER_ERROR", "message": str(e)}})
    print(f"--- FAL_ADAPTER: Finished processing job: {job_id} ---")

def callback(ch, method, properties, body):
    print(f"\nFAL_ADAPTER: Received new job message...")
    try:
        process_job(json.loads(body))
    except Exception as e:
        print(f"FAL_ADAPTER: Error in callback: {e}")
    ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    print("FAL_ADAPTER: Starting service...")
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials)
            )
            channel = connection.channel()
            channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
            channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=callback)
            print(f"FAL_ADAPTER: [*] Waiting for messages on queue '{RABBITMQ_QUEUE}'.")
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as e:
            print(f"FAL_ADAPTER: Connection to RabbitMQ failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            print(f"FAL_ADAPTER: A critical error occurred: {e}")
            break

if __name__ == "__main__":
    main()
