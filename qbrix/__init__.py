from qbrix._client import AsyncClient
from qbrix._client import AsyncQbrix
from qbrix._client import Client
from qbrix._client import Qbrix
from qbrix._config import QbrixConfig
from qbrix._mod_client import _load_client
from qbrix._mod_client import _reset_client
from qbrix._proxies import AgentProxy
from qbrix._proxies import ExperimentProxy
from qbrix._proxies import GateProxy
from qbrix._proxies import PolicyProxy
from qbrix._proxies import PoolProxy
from qbrix._version import __version__
from qbrix.resource.agent import AgentResource
from qbrix.resource.experiment import ExperimentResource
from qbrix.resource.gate import GateResource
from qbrix.resource.policy import PolicyResource
from qbrix.resource.pool import PoolResource
from qbrix.resource.runtime import RuntimeResource
from qbrix.exception import AuthenticationError
from qbrix.exception import BadGatewayError
from qbrix.exception import BadRequestError
from qbrix.exception import ConflictError
from qbrix.exception import ForbiddenError
from qbrix.exception import GatewayTimeoutError
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
from qbrix.model import Policy
from qbrix.model import PolicyParam
from qbrix.model import Pool
from qbrix.model import PoolCreate
from qbrix.model import PoolUpdate
from qbrix.model import SelectedArm
from qbrix.model import SelectResponse
from qbrix.model.policy import PolicyName
from qbrix.model.runtime import ServiceHealth
from qbrix.model.runtime import StreamSize

# module-level resource proxies — no explicit client instantiation required.
# reads QBRIX_API_KEY and QBRIX_BASE_URL from environment on first use.
pool: PoolResource = PoolProxy().__as_proxied__()  # type: ignore[assignment]
experiment: ExperimentResource = ExperimentProxy().__as_proxied__()  # type: ignore[assignment]
gate: GateResource = GateProxy().__as_proxied__()  # type: ignore[assignment]
agent: AgentResource = AgentProxy().__as_proxied__()  # type: ignore[assignment]
policy: PolicyResource = PolicyProxy().__as_proxied__()  # type: ignore[assignment]

__all__ = [
    "__version__",
    "AsyncClient",
    "AsyncQbrix",
    "Client",
    "Qbrix",
    "QbrixConfig",
    # module-level proxies
    "pool",
    "experiment",
    "gate",
    "agent",
    "policy",
    "_load_client",
    "_reset_client",
    # exceptions
    "AuthenticationError",
    "BadGatewayError",
    "BadRequestError",
    "ConflictError",
    "ForbiddenError",
    "GatewayTimeoutError",
    "InternalServerError",
    "NotFoundError",
    "QbrixAPIError",
    "QbrixConnectionError",
    "QbrixError",
    "QbrixTimeoutError",
    "RateLimitedError",
    "ServiceUnavailableError",
    # resources
    "AgentResource",
    "ExperimentResource",
    "GateResource",
    "PolicyResource",
    "PoolResource",
    "RuntimeResource",
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
    "Policy",
    "PolicyName",
    "PolicyParam",
    "Pool",
    "PoolCreate",
    "PoolUpdate",
    "SelectedArm",
    "SelectResponse",
    "ServiceHealth",
    "StreamSize",
]
