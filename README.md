# Calop

## Backend architecture

`calop-backend` is a FastAPI service organised as MVC. Run it from that directory with `uvicorn app.main:app`.

```
app/
├── main.py          App setup: middleware, routers, error handling
├── models/          Model: database tables (User, Device, Capture)
├── views/           View: request and response shapes (Pydantic)
├── controllers/     Controller: HTTP routes and shared request dependencies
├── services/        Business rules, called by controllers
├── integrations/    Third-party clients behind interfaces
│   ├── auth/            AuthProvider → Supabase
│   └── storage/         ImageStorage → Cloudinary
├── core/            Settings, database session, API key security, errors
└── migrations/      Alembic migrations (run `alembic upgrade head` from calop-backend)
```

A request flows `controller → service → model / integration`, and the controller returns a view.
Services raise the errors in `core/exceptions.py`, and `main.py` turns them into `{"detail": message}` responses.

Some names are part of the public API, so changing them changes the API itself or its generated docs:

- route handler function names (they generate the OpenAPI `operationId`)
- Pydantic class names in `views/` (they are the OpenAPI schema names)
- route parameter names such as `x_api_key` or `weight` (they are the header and form field names)
- route handler docstrings (they are the endpoint descriptions)

Adding a return type annotation to a route handler also changes its response model, so handlers don't have them.
