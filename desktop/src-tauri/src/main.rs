#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Command, Child};
use std::net::TcpStream;
use std::time::{Duration, Instant};
use std::thread;
use std::sync::Mutex;

struct AppState {
    backend: Mutex<Option<Child>>,
}

fn wait_for_port(port: u16, timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpStream::connect(format!("127.0.0.1:{}", port)).is_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(500));
    }
    false
}

fn start_backend() -> Result<Child, String> {
    let python = if cfg!(windows) { "python" } else { "python3" };
    
    let child = Command::new(python)
        .args(&["-m", "hiveai.app"])
        .current_dir("..")
        .spawn()
        .map_err(|e| format!("Failed to start Python backend: {}", e))?;
    
    if !wait_for_port(5000, Duration::from_secs(30)) {
        return Err("Backend failed to start within 30 seconds".to_string());
    }
    
    Ok(child)
}

fn main() {
    let backend = start_backend().expect("Could not start HiveAI backend");
    
    let state = AppState {
        backend: Mutex::new(Some(backend)),
    };

    tauri::Builder::default()
        .manage(state)
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<AppState>();
                if let Ok(mut guard) = state.backend.lock() {
                    if let Some(ref mut child) = *guard {
                        let _ = child.kill();
                    }
                }
            }
        })
        .setup(|app| {
            let _window = tauri::WebviewWindowBuilder::new(
                app,
                "main",
                tauri::WebviewUrl::External("http://localhost:5000".parse().unwrap()),
            )
            .title("HiveAI Knowledge Refinery")
            .inner_size(1280.0, 800.0)
            .min_inner_size(800.0, 600.0)
            .build()?;
            
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Error running HiveAI Desktop");
}
