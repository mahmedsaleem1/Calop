import os
import sys
from pathlib import Path

# Importing app modules reads settings, so give them harmless values. The unit tests never touch a database or network.
for key, value in {
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/test",
    "SUPABASE_URL": "http://localhost",
    "SUPABASE_PUBLISHABLE_KEY": "x",
    "CLOUDINARY_CLOUD_NAME": "x",
    "CLOUDINARY_API_KEY": "x",
    "CLOUDINARY_API_SECRET": "x",
    "VISION_AI_API_KEY": "x",
    "VISION_AI_MODEL": "x",
}.items():
    os.environ.setdefault(key, value)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
