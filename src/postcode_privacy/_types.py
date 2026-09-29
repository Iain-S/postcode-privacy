"""Shared type aliases."""

from typing import Any, TypeAlias

import numpy as np
import numpy.typing as npt

# Grid references arrive from ONSPD as integer metres, but synthetic geometry in
# tests and diagnostics is naturally floating point. Both are valid input.
Coordinates: TypeAlias = npt.NDArray[np.integer[Any]] | npt.NDArray[np.floating[Any]]

Edges: TypeAlias = npt.NDArray[np.int64]
