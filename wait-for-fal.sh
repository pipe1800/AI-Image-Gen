#!/bin/sh

set -e

host="$1"

until nc -z "$host" 5672; do
  >&2 echo "FAL Adapter is waiting for RabbitMQ..."
  sleep 1
done

>&2 echo "RabbitMQ is up - starting FAL Adapter."
exec python fal_adapter_service.py
