AI Generation Service
Introduction
This project is a scalable, containerized application designed to generate AI images and videos through a web interface. It serves as a robust backend system that can route jobs to different AI providers based on the requested content type.

Technology Stack
The application is built using a microservices architecture, containerized with Docker for straightforward setup and deployment for testing.

Frontend: A simple UI built with HTML, Tailwind CSS, and JavaScript.

Backend API (Orchestrator): A central API using Python and FastAPI. It handles requests, manages jobs in the database, and routes tasks.

Background Workers (Adapters): Separate Python services that listen for jobs and interact with external AI provider APIs (Fal.ai and Pollo.ai).

Message Queue: RabbitMQ provides a reliable job queue between the orchestrator and the workers for asynchronous processing.

Database: Supabase (PostgreSQL) is used for storing job information, status, and results.

Containerization: The entire stack is managed and run by Docker and Docker Compose.

System Workflow
Request: The user submits a prompt and settings through the web UI.

Proxy: NGINX receives the request and proxies it to the Orchestrator service.

Job Creation: The Orchestrator creates a job record in the Supabase database with a pending status.

Queuing: The Orchestrator publishes the job details to the appropriate RabbitMQ queue based on the content type (fal_jobs or pollo_jobs).

Processing: The corresponding worker (FAL or Pollo adapter) picks up the job, updates its status to processing, and calls the external AI provider's API.

Completion: Upon receiving the result, the worker updates the job status to completed in the database and stores the result URL.

Polling: The UI polls the Orchestrator's /jobs/{job_id} endpoint. When a completed status is detected, it displays the final image and its metadata.

Project Notes
API Credentials: For ease of setup and testing, the necessary API keys have been pre-filled in the env file. This is done intentionally so you can run the project without needing to sign up for services. In a production environment, these secrets would be managed securely (e.g., using a secret manager) and would not be committed to the repository.

Video Generation (Mock Mode): The Pollo.ai video generation worker is currently set to POLLO_MOCK_MODE=True in the .env file to avoid incurring costs during testing, however the API communicatio is fully implemented. (Although not tested on a production env).

Local Setup and Installation
To run this project, you only need Docker Desktop installed. The setup is cross-platform and works on Windows, macOS, and Linux. Make sure to have Docker installed, if not you can download it using this link: https://www.docker.com/products/docker-desktop/

1. Configure Environment
In the project's root directory, rename the file env.example to .env.

2. Run the Application
Open a terminal in the project's root directory and run the following command:

docker-compose up --build

This command will build the container images and start all the services. The initial build may take a minute.

3. Access the UI
Once the services are running, open a web browser and navigate to:

http://localhost:8080

The user interface should be available and ready for use.
