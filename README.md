# FD Backend Monorepo

This repository contains the backend services for the FD platform, including restaurant, user, and delivery services.

## Table of Contents

- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup Instructions](#setup-instructions)
- [Environment Variables](#environment-variables)
- [Running the Services](#running-the-services)
- [Running Tests](#running-tests)
- [API Documentation](#api-documentation)
- [Contact](#contact)

---

## Project Structure

```
src/
├── app.py
├── requirements.txt
├── README.md
├── delivery-service/
│   └── routes/
├── restaurant-service/
│   ├── app.py
│   ├── routes/
│   └── schemas/
├── shared/
│   ├── config/
│   ├── models/
│   └── utils/
├── user-service/
│   ├── app.py
│   ├── models/
│   └── routes/
```

## Prerequisites

- Python 3.9+
- PostgreSQL (or your configured DB)
- [pipenv](https://pipenv.pypa.io/en/latest/) or `pip`
- (Optional) Docker & Docker Compose

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd fd-backend/src
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   - Copy `.env.example` to `.env` and update values as needed.
   - Example:
     ```
     DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/fd_db
     SECRET_KEY=your_secret_key
     ```

5. **Run database migrations (if any):**
   - (Describe migration tool here, e.g., Alembic, or manual SQL scripts.)

6. **Start the services:**
   - **Restaurant Service:**
     ```bash
     cd restaurant-service
     uvicorn app:app --reload --port 8002
     ```
   - **User Service:**
     ```bash
     cd ../user-service
     uvicorn app:app --reload --port 8001
     ```
   - **Delivery Service:**
     ```bash
     cd ../delivery-service
     uvicorn app:app --reload --port 8003
     ```

## Environment Variables

All services use a shared `.env` file in the `src/` directory. Key variables:
- `DATABASE_URL`
- `SECRET_KEY`
- (Add any other required variables)

## Running Tests

(Describe test setup if available, e.g., pytest)
```bash
pytest
```

## API Documentation

See [API_DOCS.md](API_DOCS.md) for a full list of endpoints, payloads, and responses. (only for validator please find in mail attachments)

## Contact

For support, open an issue or contact the maintainer.
