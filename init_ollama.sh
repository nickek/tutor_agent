#!/bin/bash

echo "ollama - Pulling embedded model..."

docker exec -it ollama ollama pull nomic-embed-text:latest

echo "ollama - Successfully pulled embedded model!"