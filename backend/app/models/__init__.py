# Import all models to ensure they are registered with SQLAlchemy
from app.core.database import Base

# Import all model classes
try:
    from app.models.repository import Repository
except ImportError:
    pass

try:
    from app.models.code_file import CodeFile
except ImportError:
    pass

try:
    from app.models.code_entity import CodeEntity
except ImportError:
    pass

try:
    from app.models.search_index import SearchIndex
except ImportError:
    pass

try:
    from app.models.session import Session
except ImportError:
    pass

# Ensure all models are available for import
__all__ = ["Base", "Repository", "CodeFile", "CodeEntity", "SearchIndex", "Session"]
