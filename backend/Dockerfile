FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Utilisateur sans privilèges : l'API ne tourne jamais en root.
RUN groupadd --system app && useradd --system --gid app --no-create-home --shell /usr/sbin/nologin app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Le code appartient à root et reste en lecture seule pour l'utilisateur app.
COPY . .
USER app
EXPOSE 8000
# Migrations, données de démo (si la base est vide), puis l'API.
CMD ["sh", "-c", "alembic upgrade head && python -m seed.demo && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
