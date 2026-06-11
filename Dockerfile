FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e . --break-system-packages
EXPOSE 8002
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]
