FROM python:3.12-slim

WORKDIR /opt/applylens/apps/api

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations

RUN mkdir -p /opt/applylens/apps/api/storage/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
