import os
import pika
import json
import time
from dotenv import load_dotenv
from supabase import create_client, Client
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Literal, Any, Dict

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_USER = os.getenv("RABBITMQ_USER")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS")
RABBITMQ_FAL_QUEUE = os.getenv("RABBITMQ_FAL_QUEUE", "fal_jobs")
RABBITMQ_POLLO_QUEUE = os.getenv("RABBITMQ_POLLO_QUEUE", "pollo_jobs")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("ORCHESTRATOR: Successfully connected to Supabase.")
except Exception as e:
    print(f"ORCHESTRATOR: Error connecting to Supabase: {e}")
    exit(1)

app = FastAPI()

class ImageSize(BaseModel):
    width: int
    height: int

class GenerationRequest(BaseModel):
    prompt: str
    type: Literal['image', 'video']
    negative_prompt: Optional[str] = ""
    num_images: Optional[int] = 1
    image_size: Optional[ImageSize] = Field(default_factory=lambda: ImageSize(width=1024, height=1024))
    num_inference_steps: Optional[int] = 25
    guidance_scale: Optional[float] = 7.5
    seed: Optional[int] = None
    nsfw: Optional[bool] = False
    output_format: Optional[str] = "jpeg"
    reuse_seed: Optional[bool] = False
    userId: Optional[str] = None

class GenerationResponse(BaseModel):
    jobId: str
    status: str
    provider: str

class JobStatusResponse(BaseModel):
    id: str
    status: str
    parameters: Optional[dict]
    result: Optional[dict]
    created_at: Any

def route_job(request: GenerationRequest):
    if request.type == 'image':
        return {"provider": "fal", "queue": RABBITMQ_FAL_QUEUE}
    elif request.type == 'video':
        return {"provider": "pollo", "queue": RABBITMQ_POLLO_QUEUE}
    raise HTTPException(status_code=400, detail=f"Unsupported generation type: {request.type}")

def publish_job_to_queue(queue_name: str, job_details: dict):
    connection = None
    for attempt in range(5):
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials)
            )
            channel = connection.channel()
            channel.queue_declare(queue=queue_name, durable=True)
            message_body = json.dumps(job_details)
            channel.basic_publish(
                exchange='', routing_key=queue_name, body=message_body,
                properties=pika.BasicProperties(delivery_mode=2)
            )
            print(f"ORCHESTRATOR: Successfully published job {job_details.get('jobId')} to queue '{queue_name}'.")
            return
        except pika.exceptions.AMQPConnectionError as e:
            print(f"ORCHESTRATOR: RabbitMQ connection failed: {e}. Attempt {attempt + 1}/5. Retrying...")
            time.sleep(5)
        except Exception as e:
            print(f"ORCHESTRATOR: An unexpected error occurred: {e}")
            break
        finally:
            if connection and connection.is_open:
                connection.close()
    print(f"ORCHESTRATOR: CRITICAL - Failed to publish job {job_details.get('jobId')}.")

@app.post("/v2/generate", response_model=GenerationResponse, status_code=202)
def create_routed_job(request: GenerationRequest, background_tasks: BackgroundTasks):
    routing_decision = route_job(request)
    provider, queue_name = routing_decision["provider"], routing_decision["queue"]
    try:
        job_payload = {
            "prompt": request.prompt, "user_id": request.userId,
            "parameters": request.dict(exclude={'prompt', 'userId', 'type'}),
            "routing": {"selectedProvider": provider}
        }
        db_response = supabase.table("jobs").insert(job_payload).execute()
        new_job = db_response.data[0]
        job_id = new_job.get("id")
        print(f"ORCHESTRATOR: Successfully created job {job_id} for provider '{provider}'.")
    except Exception as e:
        print(f"ORCHESTRATOR: Error creating job in Supabase: {e}")
        raise HTTPException(status_code=500, detail="Could not create job in database.")
    
    job_details_for_queue = request.dict()
    job_details_for_queue["jobId"] = job_id
    
    background_tasks.add_task(publish_job_to_queue, queue_name, job_details_for_queue)
    return GenerationResponse(jobId=job_id, status="pending", provider=provider)

@app.get("/v1/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    try:
        response = supabase.table("jobs").select("*").eq("id", job_id).single().execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not fetch job status.")

@app.get("/")
def read_root():
    return {"status": "Orchestration Service v9 is running"}
