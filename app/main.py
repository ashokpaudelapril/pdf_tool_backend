# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers.pdf import basic_tools # Existing router
from .routers.pdf import batch_tools # Existing router
from .routers.convert import conversion # NEW: Import the new conversion router
from .routers.pdf import advanced_tools

app = FastAPI(
    title="Secure PDF Toolkit API",
    description="A robust API for various PDF manipulation tasks, including security features, content redaction, and batch processing.",
    version="1.0.0",
)

# CORS configuration
origins = [
    "http://localhost:3000", # Your frontend URL
    "http://127.0.0.1:3000",
    "https://pdf-tool-jd00rb0i3-ashokpaudelaprils-projects.vercel.app",
    "https://pdf-tool-pink.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(basic_tools.router)
app.include_router(batch_tools.router)
app.include_router(advanced_tools.router)
app.include_router(conversion.router) # NEW: Include the conversion router

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the Secure PDF Toolkit API"}