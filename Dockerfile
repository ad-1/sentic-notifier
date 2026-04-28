FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml poetry.lock* ./

RUN pip install --no-cache-dir poetry \
	&& poetry config virtualenvs.create false \
	&& poetry install --no-root --only main

COPY ./sentic_notifier ./sentic_notifier

RUN chown -R app:app /app

USER app

CMD ["python", "-m", "sentic_notifier.main"]