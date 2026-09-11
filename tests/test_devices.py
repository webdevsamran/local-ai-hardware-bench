"""Which devices the *runtime* sees, and how a split is expressed over them.

This machine has two GPUs -- an Intel Iris Xe and an RTX 3080 Ti, both
enumerated by Vulkan -- and a CUDA build of llama.cpp offloads to exactly one.
A multi-GPU sweep planned from the hardware inventory would request a split the
runtime cannot perform, and llama.cpp's answer to an over-long `--tensor-split`
is to ignore the extra entries rather than refuse. The run then proceeds and
produces a real measurement of a configuration nobody asked for.

A `ggml-rpc-server` counts as a device, which is what makes a two-device split
exercisable on a one-GPU machine. It validates the code path and nothing about
multi-GPU performance: the RPC device in that arrangement is the same card over
TCP loopback.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aihwbench.devices import SPLIT_MODES, parse_device_list, validate_tensor_split

#: Real `llama-server --rpc ... --list-devices` output from the reference machine.
REAL_LISTING = """Available devices:
  CUDA0: NVIDIA GeForce RTX 3080 Ti Laptop GPU (16383 MiB, 15239 MiB free)
  RPC0: 127.0.0.1:50053 (16383 MiB, 15239 MiB free)
"""


def test_it_reads_the_devices_llama_cpp_actually_prints():
    devices = parse_device_list(REAL_LISTING)
    assert [d["id"] for d in devices] == ["CUDA0", "RPC0"]
    assert devices[0]["description"].startswith("NVIDIA")
    assert devices[0]["total_mib"] == 16383
    assert devices[0]["free_mib"] == 15239


def test_a_remote_device_is_distinguished_from_a_local_one():
    """Its memory is somebody else's machine, which a result should say."""
    devices = parse_device_list(REAL_LISTING)
    assert devices[0]["kind"] == "local"
    assert devices[1]["kind"] == "rpc"


def test_device_order_is_preserved():
    """`--tensor-split` is positional.

    The first fraction goes to the first device listed, so a set of fractions
    read against a reordered list silently measures a different split.
    """
    assert [d["id"] for d in parse_device_list(REAL_LISTING)] == ["CUDA0", "RPC0"]


def test_output_with_no_devices_yields_none():
    assert parse_device_list("Available devices:\n") == []
    assert parse_device_list("") == []


def test_unrelated_log_lines_are_not_read_as_devices():
    noisy = "load_backend: loaded CUDA backend from ggml-cuda.dll\n" + REAL_LISTING
    assert len(parse_device_list(noisy)) == 2


# --- the split has to match the devices ------------------------------------


def test_a_split_matching_the_device_count_is_accepted():
    verdict = validate_tensor_split("0.5,0.5", 2)
    assert verdict["valid"] is True
    assert verdict["normalized"] == [0.5, 0.5]


def test_shares_are_normalized_so_the_result_can_say_what_ran():
    """llama.cpp normalizes internally; `7,3` is the same split as `0.7,0.3`."""
    assert validate_tensor_split("7,3", 2)["normalized"] == [0.7, 0.3]


def test_too_many_shares_are_refused_rather_than_silently_truncated():
    """The defect this guards.

    llama.cpp ignores the extras and runs anyway, so the benchmark measures a
    split nobody requested and the number looks perfectly reasonable.
    """
    verdict = validate_tensor_split("0.5,0.5", 1)
    assert verdict["valid"] is False
    assert "2 share(s) for 1 device(s)" in verdict["reason"]


def test_too_few_shares_are_refused():
    verdict = validate_tensor_split("1.0", 2)
    assert verdict["valid"] is False


def test_shares_summing_to_zero_are_refused():
    """No device would hold anything, and llama.cpp would fall back."""
    assert validate_tensor_split("0,0", 2)["valid"] is False


def test_a_negative_share_is_refused():
    assert validate_tensor_split("1.5,-0.5", 2)["valid"] is False


def test_a_non_numeric_split_is_refused():
    assert validate_tensor_split("half,half", 2)["valid"] is False


def test_the_split_modes_are_the_ones_llama_cpp_accepts():
    assert SPLIT_MODES == ("none", "layer", "row")


# --- wiring ------------------------------------------------------------------


def test_the_rpc_flag_precedes_the_list_request():
    """llama.cpp acts on `--list-devices` as it parses it and exits.

    With the flags the other way round the remote device is absent from a list
    that otherwise looks complete -- which was a real bug here, and the kind
    that reads as "there is no second device" rather than as a fault.
    """
    import inspect

    from aihwbench import devices

    source = inspect.getsource(devices.device_inventory)
    rpc_at = source.index('"--rpc"')
    list_at = source.index('"--list-devices"', rpc_at - 400 if rpc_at > 400 else 0)
    assert source.index("command = [executable]") < rpc_at
    assert rpc_at < source.rindex('command.append("--list-devices")')
    assert list_at is not None


def test_the_backend_declares_the_multi_device_axes():
    from aihwbench.backends.llama_cpp import TUNABLE_AXES

    for axis in ("rpc_servers", "tensor_split", "split_mode", "main_gpu"):
        assert axis in TUNABLE_AXES


def test_the_backend_puts_them_on_the_command_line():
    import inspect

    from aihwbench.backends import llama_cpp

    source = inspect.getsource(llama_cpp.LlamaServerHandle.__enter__)
    for flag in ("--rpc", "--tensor-split", "--split-mode", "--main-gpu"):
        assert flag in source, f"{flag} is declared but never reaches the command line"


def test_an_unknown_split_mode_is_refused_before_launch():
    from aihwbench.backends.base import BackendError, BenchmarkConfig
    from aihwbench.backends.llama_cpp import _split_mode

    with pytest.raises(BackendError, match="unknown split mode"):
        _split_mode(BenchmarkConfig(model="m", extra={"split_mode": "diagonal"}))


# --- the recorded validation -------------------------------------------------


def test_the_validation_artifact_refuses_to_be_read_as_a_result():
    """Both devices in that run are the same card over loopback.

    A throughput ordering from it would be an artifact, so the file says so and
    names the column such that it cannot be used by accident.
    """
    path = Path("results/measurements/multi-device-tensor-split-validation.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["kind"] == "code-path-validation"
    assert "NOT a multi-GPU performance result" in doc["$comment"]
    for row in doc["configurations"]:
        assert "NOT_A_RESULT" in "".join(row)


def test_the_validation_shows_the_split_actually_changed_allocation():
    """VRAM is deterministic, so differing figures prove the flag took effect.

    A split that llama.cpp was ignoring could not move device memory.
    """
    path = Path("results/measurements/multi-device-tensor-split-validation.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    vram = {row["tensor_split"]: row["peak_vram_mib"] for row in doc["configurations"]}
    assert len(set(vram.values())) == len(vram), "every split allocated differently"


def test_it_is_not_filed_as_a_sweep():
    """The dashboard globs `results/sweeps/sweep-*.json` for curves.

    A validation artifact landing there would be charted as a finding.
    """
    assert not list(Path("results/sweeps").glob("*tensor-split*"))
