# Import all models here so SQLAlchemy's relationship string resolution works.
# The order matters: base models before those that reference them.
from app.models.user import User, UserRole          # noqa: F401
from app.models.case import Case, CaseMember        # noqa: F401
from app.models.evidence import EvidenceItem, ParsingJob, ParsedRecord, EvidenceProcessingJob  # noqa: F401
from app.models.audit import AuditEvent, CaseNote   # noqa: F401
