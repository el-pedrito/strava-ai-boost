#!/bin/bash
# Startup script launched by the Lambda Web Adapter (AWS_LAMBDA_EXEC_WRAPPER=/opt/bootstrap).
# Set PYTHONPATH so the uvicorn subprocess sees both the task root (coach_stream,
# shared + vendored deps) and the shared dependencies layer at /opt/python
# (aws_lambda_powertools, requests). Lambda's own PYTHONPATH is not inherited here.
export PYTHONPATH="/var/task:/opt/python:/opt/python/lib/python3.12/site-packages:${PYTHONPATH:-}"
# CWD is the asset root (/var/task) so `shared` and `coach_stream` imports resolve.
exec python -m uvicorn coach_stream.app:app --host 0.0.0.0 --port "${PORT:-8000}"
