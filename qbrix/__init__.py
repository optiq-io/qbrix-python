from qbrix._client import AsyncQbrix
from qbrix._client import Qbrix
from qbrix._config import QbrixConfig
from qbrix._mod_client import _load_client
from qbrix._mod_client import _reset_client
from qbrix._proxies import AgentProxy
from qbrix._proxies import ExperimentProxy
from qbrix._proxies import GateProxy
from qbrix._proxies import PoolProxy
from qbrix._version import __version__
from qbrix.resource.agent import AgentResource
from qbrix.resource.experiment import ExperimentResource
from qbrix.resource.gate import GateResource
from qbrix.resource.pool import PoolResource
from qbrix.exception import AuthenticationError
from qbrix.exception import BadRequestError
from qbrix.exception import ConflictError
from qbrix.exception import ForbiddenError
from qbrix.exception import InternalServerError
from qbrix.exception import NotFoundError
from qbrix.exception import QbrixAPIError
from qbrix.exception import QbrixConnectionError
from qbrix.exception import QbrixError
from qbrix.exception import QbrixTimeoutError
from qbrix.exception import RateLimitedError
from qbrix.exception import ServiceUnavailableError
from qbrix.model import Arm
from qbrix.model import ArmCreate
from qbrix.model import Context
from qbrix.model import Experiment
from qbrix.model import ExperimentCreate
from qbrix.model import ExperimentUpdate
from qbrix.model import GateConfig
from qbrix.model import GateCreate
from qbrix.model import GateRule
from qbrix.model import PaginatedResponse
from qbrix.model import Pool
from qbrix.model import PoolCreate
from qbrix.model import PoolUpdate
from qbrix.model import SelectedArm
from qbrix.model import SelectResponse

# module-level resource proxies — no explicit client instantiation required.
# reads QBRIX_API_KEY and QBRIX_BASE_URL from environment on first use.
pool: PoolResource = PoolProxy().__as_proxied__()  # type: ignore[assignment]
experiment: ExperimentResource = ExperimentProxy().__as_proxied__()  # type: ignore[assignment]
gate: GateResource = GateProxy().__as_proxied__()  # type: ignore[assignment]
agent: AgentResource = AgentProxy().__as_proxied__()  # type: ignore[assignment]

__all__ = [
    "__version__",
    "AsyncQbrix",
    "Qbrix",
    "QbrixConfig",
    # module-level proxies
    "pool",
    "experiment",
    "gate",
    "agent",
    "_load_client",
    "_reset_client",
    # exceptions
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "ForbiddenError",
    "InternalServerError",
    "NotFoundError",
    "QbrixAPIError",
    "QbrixConnectionError",
    "QbrixError",
    "QbrixTimeoutError",
    "RateLimitedError",
    "ServiceUnavailableError",
    # models
    "Arm",
    "ArmCreate",
    "Context",
    "Experiment",
    "ExperimentCreate",
    "ExperimentUpdate",
    "GateConfig",
    "GateCreate",
    "GateRule",
    "PaginatedResponse",
    "Pool",
    "PoolCreate",
    "PoolUpdate",
    "SelectedArm",
    "SelectResponse",
]
