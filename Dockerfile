FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY pyproject.toml README.md LICENSE ./
COPY sahapusulasi ./sahapusulasi
RUN pip install --no-cache-dir .
RUN mkdir -p /app/instance && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "sahapusulasi.api:app", "--host", "0.0.0.0", "--port", "8000"]
