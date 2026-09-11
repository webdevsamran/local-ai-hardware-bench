"""KV-cache quantization is a memory setting, and must be reported as one.

The analytic model here was checked against llama.cpp on the reference machine
(RTX 3080 Ti Laptop, qwen2.5-0.5B-instruct-q4_K_M, 32768 context), by starting
llama-server at each cache dtype and reading device VRAM:

    dtype   predicted saving   measured saving   difference
    q8_0          180 MiB           178 MiB          -2
    q4_0          276 MiB           274 MiB          -2
    q5_1          240 MiB           270 MiB         +30
    q5_0          252 MiB           282 MiB         +30
    q4_1          264 MiB           294 MiB         +30

Two repetitions gave byte-identical readings, so these are allocations rather
than noise. The model is exact to 2 MiB for the dtypes with fast native CUDA
paths, and 30 MiB conservative for the other three -- because total device VRAM
includes compute buffers whose size depends on the cache type, not the cache
alone. That is the whole reason the analytic column exists beside the measured
one instead of in place of it.
"""

from __future__ import annotations

from aihwbench.analysis.kvcache import (
    BASELINE_CACHE_TYPE,
    BYTES_PER_MB,
    KV_CACHE_BYTES_PER_ELEMENT,
    NOISE_FLOOR_FRACTION,
    analyze_kv_cache_matrix,
    context_for_budget,
    kv_cache_bytes,
    kv_cache_bytes_per_token,
)

#: The reference model's geometry, as read from its own GGUF header.
QWEN = {
    "architecture": "qwen2",
    "block_count": 24,
    "head_count_kv": 2,
    "head_dim": 64,
    "context_length": 32768,
}


def _mib(value: int | None) -> float | None:
    return None if value is None else round(value / BYTES_PER_MB, 1)


# --- the analytic model ---------------------------------------------------


def test_the_cache_size_matches_what_llama_cpp_allocates():
    """Measured on the reference machine; see the module docstring."""
    assert _mib(kv_cache_bytes(QWEN, 32768, "f16", "f16")) == 384.0
    assert _mib(kv_cache_bytes(QWEN, 32768, "q8_0", "q8_0")) == 204.0
    assert _mib(kv_cache_bytes(QWEN, 32768, "q4_0", "q4_0")) == 108.0


def test_quantized_formats_cost_more_than_their_nominal_bit_width():
    """ggml blocks carry a scale, so q4_0 is 4.5 bits per value, not 4.

    Treating it as a flat 4 bits understates the cache by 12%, which is how a
    capacity estimate comes to promise a context that does not fit.
    """
    assert KV_CACHE_BYTES_PER_ELEMENT["q4_0"] == 18 / 32
    assert KV_CACHE_BYTES_PER_ELEMENT["q4_0"] > 0.5
    assert KV_CACHE_BYTES_PER_ELEMENT["q8_0"] > 1.0


def test_grouped_query_attention_is_not_confused_with_query_heads():
    """The reference model has 14 query heads and 2 KV heads.

    Sizing the cache from the query count would overstate it sevenfold.
    """
    from_kv_heads = kv_cache_bytes_per_token(QWEN)
    wrong = kv_cache_bytes_per_token({**QWEN, "head_count_kv": 14})
    assert wrong == from_kv_heads * 7


def test_k_and_v_are_sized_independently():
    """llama.cpp allows asymmetric settings and the K cache is the touchier one."""
    symmetric = kv_cache_bytes(QWEN, 32768, "q8_0", "q8_0")
    asymmetric = kv_cache_bytes(QWEN, 32768, "q8_0", "q4_0")
    assert asymmetric < symmetric
    # Exactly halfway between q8_0/q8_0 and q4_0/q4_0, since only V changed.
    both_small = kv_cache_bytes(QWEN, 32768, "q4_0", "q4_0")
    assert asymmetric == (symmetric + both_small) // 2


def test_the_cache_grows_linearly_with_context():
    """This is the entire point: the cost scales with the conversation."""
    short = kv_cache_bytes(QWEN, 2048)
    long = kv_cache_bytes(QWEN, 32768)
    assert long == short * 16


def test_at_full_context_the_cache_outweighs_the_weights():
    """The finding that makes this a memory feature rather than a footnote.

    The reference model's weights are 379 MB on disk. Its f16 KV cache at the
    context length the model itself declares is larger than that.
    """
    weights_bytes = 397_807_936
    assert kv_cache_bytes(QWEN, 32768, "f16", "f16") > weights_bytes


def test_geometry_the_header_did_not_state_yields_no_number():
    """A cache size from a guessed geometry would be quoted as a fact."""
    assert kv_cache_bytes_per_token({"block_count": None}) is None
    assert kv_cache_bytes_per_token({**QWEN, "head_dim": None}) is None


def test_an_unknown_dtype_yields_no_number():
    assert kv_cache_bytes_per_token(QWEN, "q3_k_m") is None


def test_a_budget_buys_more_context_when_the_cache_is_quantized():
    """The user-facing answer a tokens-per-second table cannot give."""
    budget = 1024 * BYTES_PER_MB
    at_f16 = context_for_budget(QWEN, budget, "f16", "f16")
    at_q4 = context_for_budget(QWEN, budget, "q4_0", "q4_0")
    assert at_f16 == 87381
    assert at_q4 / at_f16 > 3.5


def test_a_budget_of_nothing_buys_nothing():
    assert context_for_budget(QWEN, 0) is None
    assert context_for_budget(QWEN, -1) is None


def test_megabytes_are_binary_to_match_nvidia_smi():
    """`peak_vram_mb` is MiB; a decimal MB analytic figure would differ by 4.9%.

    That is enough to turn an exact match into an apparent discrepancy, in a
    report whose whole job is comparing those two columns.
    """
    assert BYTES_PER_MB == 1024 * 1024


# --- the report -----------------------------------------------------------


def _row(k: str, v: str, tps: float, vram: float) -> dict:
    return {
        "params": {"cache_type_k": k, "cache_type_v": v, "context_length": 32768},
        "metrics": {"generation_tokens_per_second": tps, "peak_vram_mb": vram},
        "run_id": f"r-{k}-{v}",
        "error": None,
    }


def test_the_report_leads_with_cache_size_and_orders_by_it():
    sweep = {
        "matrix": [
            _row("f16", "f16", 100.0, 2043),
            _row("q4_0", "q4_0", 98.0, 1769),
            _row("q8_0", "q8_0", 99.0, 1865),
        ]
    }
    report = analyze_kv_cache_matrix(sweep, QWEN)
    sizes = [c["kv_cache_mb"] for c in report["configurations"]]
    assert sizes == sorted(sizes)
    assert report["configurations"][0]["cache_type_k"] == "q4_0"


def test_a_throughput_difference_inside_the_noise_floor_is_not_a_difference():
    """Two runs of an identical configuration differed by 10% on this machine.

    Reporting a 2% difference as a result would be reporting the machine.
    """
    sweep = {"matrix": [_row("f16", "f16", 100.0, 2043), _row("q4_0", "q4_0", 98.0, 1769)]}
    report = analyze_kv_cache_matrix(sweep, QWEN)
    quantized = next(c for c in report["configurations"] if c["cache_type_k"] == "q4_0")
    assert quantized["throughput_change_percent"] == -2.0
    assert quantized["throughput_distinguishable"] is False
    assert "noise floor" in quantized["throughput_note"]


def test_a_throughput_difference_beyond_the_noise_floor_is_reported_as_real():
    sweep = {"matrix": [_row("f16", "f16", 100.0, 2043), _row("q4_0", "q4_0", 70.0, 1769)]}
    report = analyze_kv_cache_matrix(sweep, QWEN)
    quantized = next(c for c in report["configurations"] if c["cache_type_k"] == "q4_0")
    assert quantized["throughput_distinguishable"] is True
    assert "throughput_note" not in quantized


def test_device_vram_moving_more_than_the_cache_could_is_flagged():
    """Device VRAM is not the KV cache.

    `nvidia-smi` reports the whole card. A reading that moved far more than
    the cache can account for is measuring something else, and presenting it
    as a cache saving would be a fabrication.
    """
    sweep = {
        "matrix": [
            _row("f16", "f16", 100.0, 2043),
            # 800 MiB of movement for a cache that can only have saved 276.
            _row("q4_0", "q4_0", 100.0, 1243),
        ]
    }
    report = analyze_kv_cache_matrix(sweep, QWEN)
    quantized = next(c for c in report["configurations"] if c["cache_type_k"] == "q4_0")
    assert "measurement_note" in quantized
    assert "dominated by something other than the KV cache" in quantized["measurement_note"]


def test_a_sweep_without_an_f16_run_has_nothing_to_compare_against():
    sweep = {"matrix": [_row("q4_0", "q4_0", 98.0, 1769)]}
    report = analyze_kv_cache_matrix(sweep, QWEN)
    assert report["baseline"] is None
    assert "nothing to compare against" in report["unresolved"]


def test_an_empty_sweep_says_so_rather_than_reporting_an_empty_table():
    report = analyze_kv_cache_matrix({"matrix": []}, QWEN)
    assert report["configurations"] == []
    assert "no successful runs" in report["unresolved"]


def test_failed_rows_are_excluded():
    sweep = {
        "matrix": [
            _row("f16", "f16", 100.0, 2043),
            {**_row("q4_0", "q4_0", 0.0, 0.0), "error": "server failed to start"},
        ]
    }
    report = analyze_kv_cache_matrix(sweep, QWEN)
    assert [c["cache_type_k"] for c in report["configurations"]] == ["f16"]


def test_without_geometry_the_analytic_column_is_absent_not_guessed():
    sweep = {"matrix": [_row("f16", "f16", 100.0, 2043), _row("q4_0", "q4_0", 98.0, 1769)]}
    report = analyze_kv_cache_matrix(sweep, None)
    assert all(c["kv_cache_mb"] is None for c in report["configurations"])
    # The measured column still works; it just cannot be attributed.
    quantized = next(c for c in report["configurations"] if c["cache_type_k"] == "q4_0")
    assert quantized["measured_vram_saved_mb"] == 274.0


def test_a_row_without_explicit_cache_types_is_the_default_not_unknown():
    """llama.cpp's default is f16; a row that set nothing ran at f16."""
    sweep = {
        "matrix": [
            {
                "params": {"context_length": 32768},
                "metrics": {"generation_tokens_per_second": 100.0, "peak_vram_mb": 2043},
                "run_id": "r",
                "error": None,
            }
        ]
    }
    report = analyze_kv_cache_matrix(sweep, QWEN)
    assert report["configurations"][0]["is_baseline"] is True
    assert report["configurations"][0]["cache_type_k"] == BASELINE_CACHE_TYPE


def test_the_framing_says_memory_before_speed():
    """The module exists because the usual framing recommends the opposite."""
    report = analyze_kv_cache_matrix({"matrix": [_row("f16", "f16", 100.0, 2043)]}, QWEN)
    framing = report["framing"].lower()
    assert "memory" in framing
    assert framing.index("memory") < framing.index("throughput")
    assert NOISE_FLOOR_FRACTION == 0.10


# --- the inversion: a memory setting that costs memory ---------------------


def test_a_configuration_that_costs_more_than_the_baseline_is_named_as_such():
    """Measured, reproducibly, on the reference machine.

    `q8_0` for K with `f16` for V has a *smaller* cache than f16/f16 -- 294 MiB
    against 384 -- and used 836 MiB more device memory. Confirmed across two
    full sweeps and one direct llama-server measurement on an idle GPU, giving
    the same figures each time.

    A report built only on the analytic column would recommend this
    configuration to someone short of VRAM, and cost them 836 MiB.
    """
    sweep = {
        "matrix": [
            _row("f16", "f16", 382.3, 1022),
            _row("q8_0", "f16", 358.4, 1858),
        ]
    }
    report = analyze_kv_cache_matrix(sweep, QWEN)
    asymmetric = next(c for c in report["configurations"] if c["cache_type_k"] == "q8_0")
    assert asymmetric["kv_cache_mb"] < report["baseline"]["kv_cache_mb"]
    assert asymmetric["costs_more_than_baseline"] is True
    assert "MORE than f16/f16" in asymmetric["measurement_note"]
    assert "the cost is outside the cache" in asymmetric["measurement_note"]


def test_a_configuration_that_saves_memory_is_not_flagged():
    sweep = {"matrix": [_row("f16", "f16", 382.3, 1022), _row("q4_0", "q4_0", 382.4, 748)]}
    report = analyze_kv_cache_matrix(sweep, QWEN)
    good = next(c for c in report["configurations"] if c["cache_type_k"] == "q4_0")
    assert "costs_more_than_baseline" not in good
    assert good["measured_vram_saved_mb"] == 274.0


def test_the_measured_sweep_reproduces_its_published_findings():
    """Guards the two claims `docs/results/kv-cache-rtx3080ti.md` makes."""
    import json
    from pathlib import Path

    path = Path("results/sweeps/sweep-llama.cpp-kvcache.json")
    sweep = json.loads(path.read_text(encoding="utf-8"))
    report = analyze_kv_cache_matrix(sweep, QWEN)
    by_pair = {(c["cache_type_k"], c["cache_type_v"]): c for c in report["configurations"]}

    # 1. Symmetric q4_0 is strictly best: smallest cache, least VRAM, and a
    #    throughput difference inside the noise floor.
    best = by_pair[("q4_0", "q4_0")]
    assert best["kv_cache_saved_percent"] == 71.9
    assert best["throughput_distinguishable"] is False
    assert best["peak_vram_mb"] < report["baseline"]["peak_vram_mb"]

    # 2. Quantizing K while V stays f16 costs memory rather than saving it.
    for pair in (("q8_0", "f16"), ("q4_0", "f16")):
        assert by_pair[pair]["costs_more_than_baseline"] is True

    # 3. A quantized V that does not match K costs throughput, heavily.
    for pair in (("f16", "q8_0"), ("f16", "q4_0"), ("q8_0", "q4_0"), ("q4_0", "q8_0")):
        entry = by_pair[pair]
        assert entry["throughput_distinguishable"] is True
        assert entry["throughput_change_percent"] < -50


def test_the_inversion_note_points_at_the_flag_when_flash_attention_was_left_to_auto():
    """`auto` is the default and is not a synonym for `on`.

    Measured: the same dtype pair cost 940 MiB more at `auto` than at `on`.
    A note that says only "something outside the cache costs more" is true and
    useless; naming the flag is the part a reader can act on.
    """
    sweep = {
        "matrix": [
            _row("f16", "f16", 382.3, 1022),
            _row("q8_0", "f16", 358.4, 1858),
        ]
    }
    report = analyze_kv_cache_matrix(sweep, QWEN)
    note = next(c for c in report["configurations"] if c["cache_type_k"] == "q8_0")[
        "measurement_note"
    ]
    assert "--flash-attn on" in note


def test_the_note_does_not_blame_flash_attention_when_it_was_already_requested():
    """Attributing it anyway would send the reader to re-run a flag they set."""
    rows = [_row("f16", "f16", 382.3, 1022), _row("q8_0", "f16", 358.4, 1858)]
    for row in rows:
        row["params"]["flash_attn"] = "on"
    report = analyze_kv_cache_matrix({"matrix": rows}, QWEN)
    note = next(c for c in report["configurations"] if c["cache_type_k"] == "q8_0")[
        "measurement_note"
    ]
    assert "--flash-attn on" not in note
    assert "already requested" in note


# --- flash attention decides whether the cache arithmetic holds -------------


def _flash_measurement() -> dict:
    import json
    from pathlib import Path

    path = Path("results/measurements/kv-cache-flash-attention-vram.json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_with_flash_attention_on_the_analytic_model_holds_everywhere():
    """Nine configurations, all within 30 MiB of the computed cache size.

    This is what validates the analytic column: it is not checked against one
    convenient point but against every combination of K and V dtype, on an
    idle card, with the offsets consistent rather than scattered.
    """
    doc = _flash_measurement()
    deviations = [
        row["measured_device_vram_mib_flash_on"] - row["predicted_device_vram_mib"]
        for row in doc["configurations"]
    ]
    assert len(deviations) == 9
    assert max(abs(d) for d in deviations) <= 30


def test_auto_declines_flash_attention_exactly_where_k_is_quantized_and_v_is_not():
    """The two cases, and only those two.

    Everywhere else `auto` already chooses `on`, which is why the default looks
    harmless until the one time it is not.
    """
    doc = _flash_measurement()
    disagreeing = {
        (row["cache_type_k"], row["cache_type_v"])
        for row in doc["configurations"]
        if row["flash_auto_chose_off"]
    }
    assert disagreeing == {("q8_0", "f16"), ("q4_0", "f16")}
    for row in doc["configurations"]:
        quantized_k = row["cache_type_k"] != "f16"
        v_is_f16 = row["cache_type_v"] == "f16"
        assert row["flash_auto_chose_off"] == (quantized_k and v_is_f16)


def test_the_penalty_is_the_same_size_in_both_cases():
    """910 MiB twice is an allocation, not measurement scatter."""
    doc = _flash_measurement()
    penalties = [
        row["measured_device_vram_mib_flash_auto"] - row["measured_device_vram_mib_flash_on"]
        for row in doc["configurations"]
        if row["flash_auto_chose_off"]
    ]
    assert penalties == [940, 940]


def test_the_measurement_records_that_the_card_was_idle():
    """A VRAM reading taken beside another process measures both."""
    doc = _flash_measurement()
    assert doc["gpu_idle_before_and_after_mib"] == 0
    assert "no reading includes a leftover" in doc["method"]


def test_the_measurement_does_not_claim_to_be_a_benchmark():
    """No tokens were generated, so it must not read as a throughput result."""
    doc = _flash_measurement()
    assert doc["kind"] == "memory-measurement"
    assert "no throughput was measured" in doc["$comment"]
