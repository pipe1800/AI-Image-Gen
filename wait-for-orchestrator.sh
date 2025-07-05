#!/bin/sh

set -e

host="$1"

until nc -z "$host" 5672; do
  >&2 echo "Orchestrator is waiting for RabbitMQ..."
  sleep 1
done

>&2 echo "RabbitMQ is up - starting Orchestrator."
exec uvicorn orchestration_service:app --host 0.0.0.0 --port 8000
