"""VCI audit — measure how much of an open-domain task can be cheaply, trustworthily
and densely verified.

Public surface (``pip install -e .`` then ``from vci import ...``)::

    from vci import Task, Candidate, Verdict      # the fixed data model
    from vci import decompose, decompose_file    # harness differential decomposer
    from vci import compute, compute_file         # pass@k / pass^k calculator

The CLI stays available as ``vci ...`` and ``python -m vci ...``.
"""
__version__ = "0.1.0"

from .schema import Candidate, Task, Verdict
from .harness_decomp import FACTORS, decompose, decompose_file
from .passk import (compute, compute_file, unbiased_pass_at_k,
                    unbiased_pass_pow_k)

__all__ = [
    "__version__",
    "Task", "Candidate", "Verdict",
    "FACTORS", "decompose", "decompose_file",
    "compute", "compute_file", "unbiased_pass_at_k", "unbiased_pass_pow_k",
]
