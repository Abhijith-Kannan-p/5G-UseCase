FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" python-multipart pillow psutil \
    && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
# Bake the ResNet50 weights into the image so the lab server needs no internet.
RUN python -c "import torchvision; torchvision.models.resnet50(weights=torchvision.models.ResNet50_Weights.DEFAULT)"
COPY app.py .
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
