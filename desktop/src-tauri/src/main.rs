// AIHWBench desktop shell.
//
// This file is deliberately small, and it should stay that way.
//
// Every command here shells out to the `aihwbench` CLI and returns its JSON
// unchanged. The GUI does not parse results, does not compute metrics, and does
// not decide whether two results are comparable. If it did any of those, there
// would be two implementations of the benchmark — and they would drift in the
// direction nobody checks, because the GUI is what people use and the CLI is
// what has tests.
//
// The one thing this adds is reach. The people who most need to know whether
// their laptop can run a model are the least likely to install a Python CLI.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::Command;

use serde::Serialize;

/// A command that was run, and what it produced.
///
/// `command` is returned to the caller so the UI can show exactly what was
/// executed. A GUI that hides the command it ran is a GUI whose results cannot
/// be reproduced by hand, which defeats the point of a benchmark.
#[derive(Serialize)]
struct CliResult {
    command: String,
    exit_code: i32,
    stdout: String,
    stderr: String,
}

/// Arguments this shell is willing to pass through.
///
/// An allowlist rather than a free-form string: the GUI runs a subprocess, and
/// a text field wired straight to a shell is an arbitrary-execution hole. The
/// subcommands here are read-only or explicitly benchmark-running, and nothing
/// takes a path from the renderer.
const ALLOWED_SUBCOMMANDS: &[&str] = &[
    "doctor",
    "detect",
    "runtimes",
    "system-info",
    "devices",
    "modalities",
    "zoo",
    "self-test",
    "quality",
    "validate",
];

fn run_cli(args: &[String]) -> CliResult {
    let command = format!("aihwbench {}", args.join(" "));
    match Command::new("aihwbench").args(args).output() {
        Ok(output) => CliResult {
            command,
            exit_code: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).to_string(),
            stderr: String::from_utf8_lossy(&output.stderr).to_string(),
        },
        Err(error) => CliResult {
            command,
            exit_code: -1,
            stdout: String::new(),
            // Reported rather than swallowed: "aihwbench is not on PATH" is the
            // most likely first-run failure and the user can fix it.
            stderr: format!("could not run aihwbench: {error}"),
        },
    }
}

/// Run an allowlisted read-only subcommand and return its output verbatim.
#[tauri::command]
fn cli(subcommand: String, args: Vec<String>) -> Result<CliResult, String> {
    if !ALLOWED_SUBCOMMANDS.contains(&subcommand.as_str()) {
        return Err(format!(
            "{subcommand} is not exposed to the UI. Allowed: {}",
            ALLOWED_SUBCOMMANDS.join(", ")
        ));
    }
    let mut full = vec![subcommand];
    full.extend(args);
    Ok(run_cli(&full))
}

/// Run a benchmark.
///
/// Separated from `cli` because it is the one command that takes time, writes
/// files and loads the machine — so it is worth being explicit that the UI is
/// starting one, rather than hiding it among the read-only calls.
#[tauri::command]
fn benchmark(runtime: String, model: String, workload: Option<String>) -> Result<CliResult, String> {
    if runtime.is_empty() || model.is_empty() {
        return Err("a runtime and a model are required".into());
    }
    let mut args = vec![
        "benchmark".to_string(),
        "--runtime".to_string(),
        runtime,
        "--model".to_string(),
        model,
    ];
    if let Some(workload) = workload {
        args.push("--workload".to_string());
        args.push(workload);
    }
    Ok(run_cli(&args))
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![cli, benchmark])
        .run(tauri::generate_context!())
        .expect("error while running AIHWBench desktop");
}
